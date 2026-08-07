"""번호판 ↔ 차량 DB 실시간 대조 및 고위험 차량 경보 발행.

정확 매칭 → (실패 시) 1글자 오차 유사 매칭 → 미등록 판정 순으로 진행한다.
고위험(대포차·수배·도난·미등록)으로 판별되면 이벤트 버스에 경보를 올리고,
장성혁 담당 WebSocket 허브가 관제 화면으로 밀어 넣는다.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from ..core.bus import TOPIC_ALERT, TOPIC_VIOLATION, bus
from ..core.config import settings
from ..core.schemas import (
    HIGH_RISK_STATUS,
    PlateResult,
    RiskLevel,
    VehicleMatch,
    VehicleRecord,
    VehicleStatus,
    ViolationEvent,
    ViolationType,
)
from ..lpr import plate_format as pf
from .repository import VehicleRepository, get_repository

log = logging.getLogger("omeca.vehicle.matcher")

RISK_MESSAGE = {
    VehicleStatus.FAKE_PLATE: "대포차 의심 차량 감지",
    VehicleStatus.STOLEN: "도난 신고 차량 감지",
    VehicleStatus.WANTED: "수배 차량 감지",
    VehicleStatus.UNREGISTERED: "DB 미등록 차량 감지",
    VehicleStatus.IMPOUND: "과태료 체납 영치 대상 차량",
    VehicleStatus.INSURANCE_EXPIRED: "책임보험 만료 차량",
}


class VehicleMatcher:
    def __init__(
        self,
        repo: Optional[VehicleRepository] = None,
        fuzzy: Optional[bool] = None,
        min_conf_for_alert: float = 0.55,
        alert_cooldown_sec: float = 30.0,
        log_reads: bool = True,
    ) -> None:
        self.repo = repo or get_repository()
        self.fuzzy = settings.lpr.fuzzy_match if fuzzy is None else fuzzy
        self.min_conf_for_alert = min_conf_for_alert
        self.alert_cooldown_sec = alert_cooldown_sec
        self.log_reads = log_reads
        self._last_alert: dict[tuple[str, str], float] = {}
        self.stats = {"matched": 0, "fuzzy": 0, "unregistered": 0, "alerts": 0}

    # ------------------------------------------------------------------
    def match(self, plate: PlateResult) -> VehicleMatch:
        """번호판 1건을 DB와 대조한다."""
        key = pf.canonical(plate.plate_no)

        if self.log_reads:
            try:
                self.repo.log_plate_read(
                    plate.cam_id, plate.track_id, key, plate.raw_text,
                    plate.confidence, plate.valid_format, plate.engine, plate.timestamp,
                )
            except Exception:
                log.exception("plate_read_log 기록 실패")

        rec = self.repo.find(key)
        if rec is not None:
            self.stats["matched"] += 1
            return VehicleMatch(
                plate_no=key, matched=True, record=rec, status=rec.status,
                risk_level=rec.risk_level, matched_plate=rec.plate_no,
                cam_id=plate.cam_id, track_id=plate.track_id, timestamp=plate.timestamp,
            )

        # 유사 매칭은 포맷이 유효할 때만 시도한다 (엉뚱한 문자열의 오검거 방지)
        if self.fuzzy and plate.valid_format:
            hit = self.repo.find_similar(key, max_diff=1)
            if hit is not None:
                rec, diff = hit
                self.stats["fuzzy"] += 1
                log.info("유사 매칭: OCR=%s → DB=%s (오차 %d자)", key, rec.plate_no, diff)
                return VehicleMatch(
                    plate_no=key, matched=True, record=rec, status=rec.status,
                    risk_level=rec.risk_level, fuzzy=True, matched_plate=rec.plate_no,
                    cam_id=plate.cam_id, track_id=plate.track_id, timestamp=plate.timestamp,
                )

        self.stats["unregistered"] += 1
        return VehicleMatch(
            plate_no=key, matched=False, record=None,
            status=VehicleStatus.UNREGISTERED, risk_level=RiskLevel.HIGH,
            cam_id=plate.cam_id, track_id=plate.track_id, timestamp=plate.timestamp,
        )

    # ------------------------------------------------------------------
    def check_and_alert(self, plate: PlateResult) -> Optional[ViolationEvent]:
        """대조 후 고위험이면 경보 이벤트를 생성·발행한다."""
        m = self.match(plate)

        if m.status not in HIGH_RISK_STATUS:
            return None

        # 인식 신뢰도가 낮으면 경보를 내지 않는다.
        # 미등록 판정은 오인식이 곧바로 오경보로 이어지므로 기준을 더 높인다.
        threshold = self.min_conf_for_alert + (0.15 if not m.matched else 0.0)
        if plate.confidence < threshold:
            log.debug("신뢰도 부족으로 경보 보류: %s (%.2f < %.2f)",
                      m.plate_no, plate.confidence, threshold)
            return None

        if not self._cooldown_ok(m):
            return None

        detail = RISK_MESSAGE.get(m.status, "고위험 차량 감지")
        if m.record and m.record.memo:
            detail += f" | {m.record.memo}"
        if m.fuzzy:
            detail += f" | 유사매칭(OCR:{m.plate_no}→DB:{m.matched_plate})"

        ev = ViolationEvent(
            violation_type=ViolationType.HIGH_RISK_VEHICLE,
            cam_id=m.cam_id,
            track_id=m.track_id,
            timestamp=m.timestamp,
            plate_no=m.matched_plate or m.plate_no,
            plate_confidence=plate.confidence,
            risk_level=RiskLevel.HIGH,
            vehicle_status=m.status,
            detail=detail,
        )

        self.stats["alerts"] += 1
        try:
            self.repo.save_violation(ev)
        except Exception:
            log.exception("위반 이벤트 저장 실패: %s", ev.event_id)

        payload = ev.to_payload()
        bus.publish(TOPIC_ALERT, payload)
        bus.publish(TOPIC_VIOLATION, payload)
        return ev

    # ------------------------------------------------------------------
    def _cooldown_ok(self, m: VehicleMatch) -> bool:
        """같은 카메라에서 같은 차량이 연속 감지될 때 경보 폭주를 막는다."""
        key = (m.cam_id, m.matched_plate or m.plate_no)
        now = m.timestamp or time.time()
        last = self._last_alert.get(key)
        if last is not None and now - last < self.alert_cooldown_sec:
            return False
        self._last_alert[key] = now
        return True

    # ------------------------------------------------------------------
    def status_of(self, plate_no: str) -> tuple[VehicleStatus, RiskLevel]:
        """위반 감지 모듈이 위반 차량의 위험도를 함께 표기할 때 사용."""
        rec = self.repo.find(plate_no)
        if rec is None:
            return VehicleStatus.UNREGISTERED, RiskLevel.HIGH
        return rec.status, rec.risk_level

    def reset(self) -> None:
        self._last_alert.clear()
        for k in self.stats:
            self.stats[k] = 0
