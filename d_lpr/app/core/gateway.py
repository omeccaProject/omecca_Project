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
import os
import logging
import threading
import time
import urllib.error
import urllib.parse
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

# --------------------------------------------------------------------------
# 대시보드 그룹핑 힌트 (meta.riskCategory)
#
# 관제 화면에서 "이상운전" 한 묶음으로 보여 주기 위한 **표시용 분류**다.
# eventType 은 규격 7종 그대로 두고 meta 에만 힌트를 얹는다. 이유:
#
#   · 불법 유턴을 DUI_PATTERN(음주운전 의심)으로 보내면 "이 차 음주 의심"이라는
#     틀린 근거가 관제 요원에게 전달된다. 유턴은 음주와 무관하다.
#   · 같은 사건이 두 eventType 으로 두 번 나가면 b_report 통계가 부풀려진다.
#   · ⑥ 음주운전 패턴은 다른 담당 영역이라 그쪽 정확도 지표가 오염된다.
#
# 규격서 4장은 "임의로 새 **최상위** 필드를 추가하지 말 것"이므로 meta 는 자유다.
# b_dashboard 는 meta.riskCategory 로 묶기만 하면 된다.
# --------------------------------------------------------------------------
RISK_CATEGORY = {
    ViolationType.RED_LIGHT: "abnormal_driving",       # 이상운전
    ViolationType.ILLEGAL_UTURN: "abnormal_driving",   # 이상운전
    ViolationType.HIGH_RISK_VEHICLE: "vehicle_alert",  # 차량 조회 경보
}
RISK_CATEGORY_KO = {
    "abnormal_driving": "이상운전",
    "vehicle_alert": "차량 경보",
}


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
                            else ev.plate_confidence), 3),
        # ev.timestamp는 실시각이 아니라 영상 재생 경과 초(frame_no/fps)라서 그대로 쓰면
        # 1970년대로 계산된다. 게이트웨이에 보내는 시점의 실제 시각을 대신 쓴다
        # (a_core의 debris 이벤트도 동일하게 "전송 시점 = 발생 시점"으로 처리한다).
        "occurredAt": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "location": ({"lat": lat, "lng": lng} if lat is not None else None),
        "isRegisteredTarget": bool(is_registered_target),
        "targetId": target_id,
        # ROI/가상 라인 ID. 우리는 문자열 zone_id 를 쓰므로 meta 에도 원본을 남긴다
        "roiId": None,
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
            # 대시보드에서 "이상운전"으로 묶기 위한 표시용 분류
            "riskCategory": RISK_CATEGORY.get(ev.violation_type),
            "riskCategoryLabel": RISK_CATEGORY_KO.get(
                RISK_CATEGORY.get(ev.violation_type, ""), None),
            "violationSubtype": ev.subtype or None,
            "detail": ev.detail or None,
            "evidenceFrames": ev.evidence_frames or None,
            "trajectory": ([[round(x, 1), round(y, 1)] for x, y in ev.trajectory]
                           or None),
        },
        "frameRefBefore": frame_before or None,
        "frameRefAfter": frame_after or None,
    }
    return payload


def _risk_category(type_value: str) -> Optional[str]:
    """버스 payload 의 문자열 type("illegal_uturn" 등) → 위험 카테고리."""
    try:
        return RISK_CATEGORY.get(ViolationType(type_value))
    except ValueError:
        return None


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
        api_key: str = os.environ.get("GATEWAY_API_KEY", "omecca-dev-key-2026"),
    ) -> None:
        self.url = base_url.rstrip("/") + path
        self.timeout = timeout
        self.enabled = enabled
        self.api_key = api_key
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

    # ------------------------------------------------------------------
    # [신규] 사건 전/후 캡처 이미지 반영.
    #
    # 이벤트 자체(POST /api/events)는 `_emit()`이 위반을 확정한 그 순간 버스로
    # 이미 나가버린다(위 `subscribe_to_bus`/`send` 참고) - 그 시점엔 아직 "사건
    # 전/후" 캡처 이미지를 만들 수 없다(전 프레임은 버퍼에서, 후 프레임은 바로
    # 이 프레임에서 떠야 하는데, 이벤트 발행 자체가 그 계산보다 먼저 끝난다).
    #
    # 그래서 e_tracking(SmartCCTV)의 server/gatewayForward.js가 이미 쓰고 있는
    # 것과 똑같은 2단계 패턴을 따른다:
    #   1) 위반이 잡히면 이벤트를 먼저 보낸다(캡처 없이, 지금처럼)
    #   2) run_uturn.py가 그 직후 전/후 프레임을 JPEG로 저장하고, 이 메서드로
    #      PATCH /api/events/by-track/{trackId}/captures 를 호출해 방금 만든
    #      이벤트에 frameRefBefore/frameRefAfter만 채워 넣는다.
    #
    # 실패해도(게이트웨이가 꺼져 있거나 아직 그 trackId 이벤트가 없어도) 조용히
    # 넘어간다 - 캡처 반영 실패가 위반 감지 자체를 막으면 안 된다. 프레임 처리
    # 루프를 절대 막지 않도록 별도 스레드에서 fire-and-forget으로 보낸다.
    def update_captures(self, track_id: str, frame_before: Optional[str],
                         frame_after: Optional[str], delay_sec: float = 0.0) -> None:
        if not self.enabled or (not frame_before and not frame_after):
            return

        def _worker() -> None:
            # [신규] --plate-hold로 이벤트 POST 자체가 지연될 수 있어서, 그 이벤트가
            # 실제로 게이트웨이에 생기기 전에 PATCH가 먼저 도착하면 "그 trackId
            # 이벤트가 아직 없음"으로 조용히 무시된다. 호출자가 넘긴 만큼 먼저 기다린다.
            if delay_sec > 0:
                time.sleep(delay_sec)
            url = self.url.rsplit("/api/events", 1)[0] + \
                f"/api/events/by-track/{urllib.parse.quote(track_id, safe='')}/captures"
            data = json.dumps(
                {"frameRefBefore": frame_before, "frameRefAfter": frame_after},
                ensure_ascii=False,
            ).encode("utf-8")
            req = urllib.request.Request(
                url, data=data, method="PATCH",
                headers={
                    "Content-Type": "application/json; charset=utf-8",
                    "X-API-Key": self.api_key,
                },
            )
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    if not (200 <= r.status < 300):
                        log.warning("캡처 이미지 반영 실패 (HTTP %s): %s", r.status, track_id)
            except Exception as e:
                log.warning("캡처 이미지 반영 중 오류(%s): %s", track_id, e)

        threading.Thread(target=_worker, daemon=True, name="gateway-captures").start()

    # ------------------------------------------------------------------
    def enqueue(self, payload: dict[str, Any]) -> bool:
        """이미 규격 변환이 끝난 payload 를 전송 큐에 넣는다.

        `send()` 는 `ViolationEvent` 를 받아 여기서 변환하지만, 번호판 확정을
        기다렸다 보내는 중계기(`plate_hold.PlateHoldForwarder`)는 버스에서 온
        dict 를 이미 `payload_from_bus()` 로 변환해 두고 넘긴다. 그 경로가
        큐 내부(`_q`)를 직접 만지지 않도록 열어 둔 입구다.
        """
        if not self.enabled:
            return False
        try:
            self._q.put_nowait(payload)
            return True
        except Exception:
            self.stats["dropped"] += 1
            log.warning("게이트웨이 큐가 가득 참 — 이벤트 폐기")
            return False

    def send_now(self, payload: dict[str, Any]) -> bool:
        """즉시 전송 (테스트·수동 재전송용)."""
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            self.url, data=data, method="POST",
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "X-API-Key": self.api_key,
            },
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
    return {
        "camId": p.get("cam_id"),
        "trackId": f"trk-{p.get('track_id')}" if p.get("track_id") is not None else None,
        "eventType": type_map.get(p.get("type", ""), "UNREGISTERED_VEHICLE"),
        "objectClass": OBJECT_CLASS_VEHICLE,
        "bbox": [0, 0, 0, 0],
        "confidence": p.get("plate_confidence", 0.0),
        # p["timestamp"]는 영상 경과 초라 그대로 쓰면 1970년대로 찍힌다 — 전송 시점 실제 시각 사용
        "occurredAt": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "location": ({"lat": loc[0], "lng": loc[1]} if loc else None),
        "isRegisteredTarget": False,
        "targetId": None,
        "roiId": None,
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
            "riskCategory": _risk_category(p.get("type", "")),
            "riskCategoryLabel": RISK_CATEGORY_KO.get(
                _risk_category(p.get("type", "")) or "", None),
            "violationSubtype": p.get("subtype") or None,
            "detail": p.get("detail") or None,
            "evidenceFrames": p.get("evidence_frames") or None,
            "trajectory": p.get("trajectory") or None,
        },
        "frameRefBefore": None,
        "frameRefAfter": None,
    }


def payload_from_bus(p: dict[str, Any]) -> dict[str, Any]:
    """`_payload_from_bus` 의 공개 이름.

    버스 payload 를 게이트웨이 규격으로 바꾸는 변환은 이 파일 한 곳에만 둔다.
    다른 모듈(예: `plate_hold`)이 밑줄 붙은 내부 함수를 직접 부르지 않도록
    이름만 열어 준 것이고, 동작은 완전히 같다.
    """
    return _payload_from_bus(p)
