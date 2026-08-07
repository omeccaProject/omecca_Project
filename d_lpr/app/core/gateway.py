"""b_gateway 연동 어댑터.

우리 내부 이벤트(`ViolationEvent`)를 팀 공통 규격으로 변환해
장성혁 담당 `b_gateway` 의 `POST /api/events` 로 보낸다.

규격 출처: shared/schemas/이벤트_스키마_규격서.md (장성혁, 2026-08-06)

내부 표현과 전송 규격이 다른 부분
  - 필드명   snake_case  →  camelCase
  - 이벤트명 red_light   →  SIGNAL_VIOLATION (대문자 enum 7종)
  - bbox     [x1,y1,x2,y2] → [x, y, w, h]
  - 시각     유닉스 초    →  ISO 8601 문자열
  - 위치     [위도, 경도]  →  {"lat": .., "lng": ..}
  - 우리 고유 정보(위험도·판정근거 등)는 최상위에 넣지 않고 `meta` 안에 담는다

규격서 4장 "임의로 새 최상위 필드를 추가하지 말 것" 을 따른다.
"""

from __future__ import annotations

import json
import logging
import threading
import urllib.error
import urllib.request
from datetime import datetime
from queue import Empty, Queue
from typing import Any, Optional

from .schemas import BBox, ViolationEvent, ViolationType

log = logging.getLogger("omeca.gateway")

# --------------------------------------------------------------------------
# 규격서 3.2 — eventType 7종. 이 외의 값은 게이트웨이가 400 으로 거부한다.
# 우리 모듈이 만드는 것은 ④ 미등록차량 / ⑦ 신호위반·불법유턴 세 가지다.
# --------------------------------------------------------------------------
EVENT_TYPE = {
    ViolationType.HIGH_RISK_VEHICLE: "UNREGISTERED_VEHICLE",
    ViolationType.RED_LIGHT: "SIGNAL_VIOLATION",
    ViolationType.ILLEGAL_UTURN: "UTURN_VIOLATION",
}

OBJECT_CLASS_VEHICLE = "VEHICLE"      # 규격서 3.3 — 우리는 항상 차량


def to_gateway_payload(
    ev: ViolationEvent,
    bbox: Optional[BBox] = None,
    confidence: Optional[float] = None,
    frame_before: str = "",
    frame_after: str = "",
    matched_db_id: Optional[str] = None,
    target_id: Optional[int] = None,
    is_registered_target: bool = False,
) -> dict[str, Any]:
    """내부 이벤트 → 팀 공통 규격 JSON."""
    event_type = EVENT_TYPE.get(ev.violation_type)
    if event_type is None:                      # 방어: 규격 밖 값은 보내지 않는다
        raise ValueError(f"게이트웨이 규격에 없는 이벤트 유형: {ev.violation_type}")

    # bbox: 내부는 좌상단/우하단, 규격은 좌상단 + 폭/높이
    if bbox is not None:
        box = [int(bbox.x1), int(bbox.y1), int(bbox.width), int(bbox.height)]
    else:
        box = [0, 0, 0, 0]

    lat, lng = (ev.location or (None, None))

    payload: dict[str, Any] = {
        "camId": ev.cam_id,
        # 규격상 trackId 는 문자열이다 (내부는 정수)
        "trackId": f"trk-{ev.track_id}" if ev.track_id is not None else None,
        "eventType": event_type,
        "objectClass": OBJECT_CLASS_VEHICLE,
        "bbox": box,
        "confidence": round(float(confidence if confidence is not None
                                  else ev.plate_confidence), 4),
        "occurredAt": datetime.fromtimestamp(ev.timestamp).strftime("%Y-%m-%dT%H:%M:%S"),
        "location": ({"lat": lat, "lng": lng} if lat is not None else None),
        "isRegisteredTarget": bool(is_registered_target),
        "targetId": target_id,
        # ROI/가상 라인 ID. 우리는 문자열 zone_id 를 쓰므로 meta 에도 원본을 남긴다
        "roiId": _as_long(ev.zone_id),
        "meta": {
            "plateNumber": ev.plate_no or None,
            "matchedDbId": matched_db_id,
            "faceMatchScore": None,
            "stationaryDurationSec": None,
            "trajectoryFeatures": {
                "zigzagCount": None,
                "accelDecelCount": None,
                "speedVarianceKmh": None,
            },
            # --- 우리 모듈 고유 정보 (규격 4장에 따라 meta 안에 담는다) ---
            "eventId": ev.event_id,
            "riskLevel": ev.risk_level.value,
            "vehicleStatus": ev.vehicle_status.value,
            "plateConfidence": round(float(ev.plate_confidence), 4),
            "roiName": ev.zone_id or None,
            "detail": ev.detail or None,
            "evidenceFrames": ev.evidence_frames or None,
            "trajectory": ([[round(x, 1), round(y, 1)] for x, y in ev.trajectory]
                           or None),
        },
        "frameRefBefore": frame_before or None,
        "frameRefAfter": frame_after or None,
    }
    return payload


def _as_long(zone_id: str) -> Optional[int]:
    """'INT-A' 같은 문자열 ROI 식별자에서 숫자만 뽑는다. 없으면 None."""
    if not zone_id:
        return None
    digits = "".join(ch for ch in zone_id if ch.isdigit())
    return int(digits) if digits else None


# ==========================================================================
class GatewayClient:
    """게이트웨이 전송기.

    관제 파이프라인이 프레임 처리 중에 멈추면 안 되므로 **백그라운드 큐**로 보낸다.
    게이트웨이가 죽어 있어도 우리 쪽 탐지는 계속 돈다.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8080",
        path: str = "/api/events",
        timeout: float = 3.0,
        enabled: bool = True,
        queue_size: int = 500,
    ) -> None:
        self.url = base_url.rstrip("/") + path
        self.timeout = timeout
        self.enabled = enabled
        self._q: Queue = Queue(maxsize=queue_size)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.stats = {"sent": 0, "failed": 0, "dropped": 0}

    # ------------------------------------------------------------------
    def start(self) -> "GatewayClient":
        if not self.enabled or self._thread is not None:
            return self
        self._thread = threading.Thread(target=self._worker, daemon=True,
                                        name="gateway-sender")
        self._thread.start()
        log.info("게이트웨이 전송 시작: %s", self.url)
        return self

    def stop(self, drain: bool = True) -> None:
        if drain:
            self._q.join()
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    # ------------------------------------------------------------------
    def send(self, ev: ViolationEvent, **kwargs) -> bool:
        """이벤트를 큐에 넣는다. 큐가 차 있으면 버리고 False."""
        if not self.enabled:
            return False
        try:
            payload = to_gateway_payload(ev, **kwargs)
        except ValueError:
            log.exception("페이로드 변환 실패")
            return False
        try:
            self._q.put_nowait(payload)
            return True
        except Exception:
            self.stats["dropped"] += 1
            log.warning("게이트웨이 큐가 가득 참 — 이벤트 폐기 (%s)", ev.event_id)
            return False

    def send_now(self, payload: dict[str, Any]) -> bool:
        """즉시 전송 (테스트·수동 재전송용)."""
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            self.url, data=data, method="POST",
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                ok = 200 <= r.status < 300
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:200]
            log.error("게이트웨이 %s 응답: %s", e.code, body)
            ok = False
        except Exception as e:
            log.warning("게이트웨이 전송 실패: %s", e)
            ok = False
        self.stats["sent" if ok else "failed"] += 1
        return ok

    # ------------------------------------------------------------------
    def _worker(self) -> None:
        while not self._stop.is_set():
            try:
                payload = self._q.get(timeout=0.5)
            except Empty:
                continue
            try:
                self.send_now(payload)
            finally:
                self._q.task_done()

    # ------------------------------------------------------------------
    def subscribe_to_bus(self) -> None:
        """이벤트 버스에 붙여 위반 이벤트를 자동 전송한다.

        엔진이 이벤트를 낼 때마다 게이트웨이로 흘러간다.
        """
        from .bus import TOPIC_VIOLATION, bus

        def _on(topic: str, payload: dict) -> None:
            if topic != TOPIC_VIOLATION:
                return
            # 버스에는 이미 직렬화된 dict 가 오므로 최소 변환만 한다
            try:
                self._q.put_nowait(_payload_from_bus(payload))
            except Exception:
                self.stats["dropped"] += 1

        bus.subscribe(_on)


def _payload_from_bus(p: dict[str, Any]) -> dict[str, Any]:
    """버스 payload(dict) → 게이트웨이 규격. `to_gateway_payload` 와 결과가 같다."""
    type_map = {
        "high_risk_vehicle": "UNREGISTERED_VEHICLE",
        "red_light": "SIGNAL_VIOLATION",
        "illegal_uturn": "UTURN_VIOLATION",
    }
    loc = p.get("location")
    ts = p.get("timestamp") or 0
    return {
        "camId": p.get("cam_id"),
        "trackId": f"trk-{p.get('track_id')}" if p.get("track_id") is not None else None,
        "eventType": type_map.get(p.get("type", ""), "UNREGISTERED_VEHICLE"),
        "objectClass": OBJECT_CLASS_VEHICLE,
        "bbox": [0, 0, 0, 0],
        "confidence": p.get("plate_confidence", 0.0),
        "occurredAt": datetime.fromtimestamp(ts).strftime("%Y-%m-%dT%H:%M:%S"),
        "location": ({"lat": loc[0], "lng": loc[1]} if loc else None),
        "isRegisteredTarget": False,
        "targetId": None,
        "roiId": _as_long(p.get("zone_id", "")),
        "meta": {
            "plateNumber": p.get("plate_no") or None,
            "matchedDbId": None,
            "faceMatchScore": None,
            "stationaryDurationSec": None,
            "trajectoryFeatures": {
                "zigzagCount": None, "accelDecelCount": None, "speedVarianceKmh": None,
            },
            "eventId": p.get("event_id"),
            "riskLevel": p.get("risk_level"),
            "vehicleStatus": p.get("vehicle_status"),
            "plateConfidence": p.get("plate_confidence"),
            "roiName": p.get("zone_id") or None,
            "detail": p.get("detail") or None,
            "evidenceFrames": p.get("evidence_frames") or None,
            "trajectory": p.get("trajectory") or None,
        },
        "frameRefBefore": None,
        "frameRefAfter": None,
    }
