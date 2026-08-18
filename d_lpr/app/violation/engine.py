"""위반 감지 엔진.

탐지 → 궤적 갱신 → LPR 연동 → 위반 판정 → 이벤트 발행/저장까지의
흐름을 한 곳에서 조립한다. 상위(파이프라인 러너)는 detection 만 밀어 넣으면 된다.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from ..core.bus import TOPIC_VIOLATION, bus
from ..core.config import settings
from ..core.schemas import (
    Detection,
    RiskLevel,
    ViolationEvent,
    ViolationType,
)
from ..lpr.pipeline import LPRPipeline
from ..vehicle.matcher import VehicleMatcher
from ..vehicle.repository import VehicleRepository, get_repository
from .detectors import RedLightDetector, UTurnDetector, Verdict
from .roi import ZoneRegistry, default_registry
from .signal_state import FixedCycleSignal, SignalProvider
from .trajectory import TrackStore

log = logging.getLogger("omeca.violation.engine")


class ViolationEngine:
    def __init__(
        self,
        zones: Optional[ZoneRegistry] = None,
        signal_provider: Optional[SignalProvider] = None,
        lpr: Optional[LPRPipeline] = None,
        matcher: Optional[VehicleMatcher] = None,
        repo: Optional[VehicleRepository] = None,
        cooldown_sec: Optional[float] = None,
    ) -> None:
        cfg = settings.violation
        self.zones = zones or ZoneRegistry.load(cfg.zones_path)
        if len(self.zones) == 0:
            self.zones = default_registry()
        self.signal = signal_provider or FixedCycleSignal()
        self.lpr = lpr or LPRPipeline()
        self.repo = repo or get_repository()
        self.matcher = matcher or VehicleMatcher(repo=self.repo)
        self.tracks = TrackStore(history=cfg.track_history)
        self.cooldown_sec = cfg.cooldown_sec if cooldown_sec is None else cooldown_sec

        self.red_light = RedLightDetector(self.signal)
        # 유턴 판정도 신호를 본다 (유턴 허용 구간에서 좌회전 화살표 확인용)
        self.uturn = UTurnDetector(self.signal)
        self.stats = {"detections": 0, "violations": 0, "red_light": 0, "illegal_uturn": 0}

    # ------------------------------------------------------------------
    def process(
        self,
        det: Detection,
        frame: Any = None,
        plate_hint: Optional[str] = None,
    ) -> list[ViolationEvent]:
        """탐지 1건 처리. 발생한 위반 이벤트 목록을 반환한다."""
        events: list[ViolationEvent] = []
        if not det.is_vehicle():
            return events

        self.stats["detections"] += 1
        track = self.tracks.update(det)

        # 1) 번호판 인식 및 고위험 차량 대조
        plate = self.lpr.process(det, frame=frame, hint=plate_hint)
        if plate is not None:
            self.tracks.attach_plate(det.cam_id, det.track_id, plate.plate_no, plate.confidence)
            alert = self.matcher.check_and_alert(plate)
            if alert is not None:
                events.append(alert)

        # 2) 위반 판정
        cz = self.zones.get(det.cam_id)
        if cz is None:
            return events

        for verdict in self._run_detectors(track, cz):
            ev = self._emit(track, verdict, cz)
            if ev is not None:
                events.append(ev)
        return events

    # ------------------------------------------------------------------
    def _run_detectors(self, track, cz) -> list[Verdict]:
        out: list[Verdict] = []
        for detector in (self.red_light, self.uturn):
            try:
                v = detector.check(track, cz)
            except Exception:
                log.exception("판정 로직 오류: %s", type(detector).__name__)
                continue
            if v is not None and v.violated:
                out.append(v)
        return out

    # ------------------------------------------------------------------
    def _emit(self, track, verdict: Verdict, cz) -> Optional[ViolationEvent]:
        vtype = verdict.violation_type
        assert vtype is not None
        now = track.last.ts if track.last else 0.0

        # 동일 track의 같은 위반이 연속 발행되지 않도록 쿨다운
        last = track.last_emitted.get(vtype.value)
        if last is not None and now - last < self.cooldown_sec:
            return None
        track.last_emitted[vtype.value] = now

        plate_no = track.plate_no or self.lpr.confirmed_plate(track.cam_id, track.track_id) or ""
        conf = track.plate_confidence or self.lpr.confidence_of(track.cam_id, track.track_id)

        # 경보 경로(`VehicleMatcher.check_and_alert`)와 **같은 함수**로 대조한다.
        # 예전에는 여기만 `status_of()` 였고 그 안에 유사 매칭이 빠져 있어서,
        # OCR 이 한 글자를 틀리면 같은 차량이 경보에서는 '등록', 위반 기록에는
        # '미등록' 으로 갈려 저장됐다. count=False 는 경보 쪽에서 이미 센 건을
        # 두 번 세지 않기 위함이다.
        vm = self.matcher.resolve(plate_no, count=False) if plate_no else None
        status = vm.status if vm is not None else None
        risk = vm.risk_level if vm is not None else RiskLevel.NORMAL

        detail = verdict.detail
        if vm is not None and vm.fuzzy:
            # 어떤 번호를 읽어 어떤 번호로 붙였는지 남긴다. 나중에 이의가
            # 제기됐을 때 이 기록이 없으면 오검거인지 확인할 방법이 없다.
            detail = f"{detail} | 유사매칭(OCR:{vm.plate_no}→DB:{vm.matched_plate})"
            plate_no = vm.matched_plate or plate_no

        ev = ViolationEvent(
            violation_type=vtype,
            cam_id=track.cam_id,
            track_id=track.track_id,
            timestamp=now,
            plate_no=plate_no,
            plate_confidence=conf,
            risk_level=risk,
            vehicle_status=status if status is not None else None,  # type: ignore[arg-type]
            zone_id=verdict.zone_id,
            subtype=verdict.subtype,
            detail=detail,
            evidence_frames=verdict.frames,
            trajectory=track.recent_xy(30),
            location=cz.location,
        )
        if ev.vehicle_status is None:  # 번호판 미확보 시 기본값
            from ..core.schemas import VehicleStatus
            ev.vehicle_status = VehicleStatus.REGISTERED

        self.stats["violations"] += 1
        self.stats[vtype.value] = self.stats.get(vtype.value, 0) + 1

        try:
            self.repo.save_violation(ev)
        except Exception:
            log.exception("위반 저장 실패: %s", ev.event_id)

        bus.publish(TOPIC_VIOLATION, ev.to_payload())
        log.info("[위반] %s cam=%s plate=%s %s", ev.label, ev.cam_id, ev.plate_no or "-", ev.detail)
        return ev

    # ------------------------------------------------------------------
    def prune(self, now: float) -> None:
        self.tracks.prune(now)
        self.lpr.prune(now=now)

    def reset(self) -> None:
        self.tracks.clear()
        self.lpr.reset()
        self.matcher.reset()
        self.red_light.reset()
        for k in self.stats:
            self.stats[k] = 0
