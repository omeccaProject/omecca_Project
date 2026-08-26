"""번호판이 확정될 때까지 잠깐 쥐고 있다가 게이트웨이로 보내는 중계기.

왜 필요한가
------------------------------------------------------------------
위반 판정은 차량이 중앙선/정지선을 넘는 **그 순간** 확정된다.
반면 번호판은 같은 track 의 여러 프레임을 모아 가중 다수결로 확정한다
(`LPRPipeline.TrackVote` — 단일 프레임 OCR 이 흔들려서 이렇게 한다).

그래서 순서가 이렇게 어긋나는 경우가 흔하다.

    t=12.3s  중앙선 통과 → 불법유턴 확정 → 이벤트 발행 (번호판 아직 미확정)
    t=12.8s  번호판 "12가3456" 확정

이벤트를 발행 즉시 보내면 대시보드 이벤트 리포트의 "차량 번호판" 칸이
빈 채로("-") 굳어 버린다. 나중에 번호판이 확정돼도 그 이벤트에는 못 실린다.

이 모듈은 **번호판이 비어 있는 위반 이벤트만** 짧게 보류했다가,
그 사이 같은 track 의 번호판이 확정되면 실어서 보낸다.
보류 시간을 넘기면 있는 그대로(번호판 없이) 보낸다 — 이벤트 자체가
사라지는 일은 없다.

건드리지 않는 것
------------------------------------------------------------------
- 위반 판정 로직(`ViolationEngine` / `detectors.py`) — 그대로다.
- 전송 규격 변환(`gateway._payload_from_bus`) — 그대로 재사용한다.
- DB 대조는 `VehicleMatcher.resolve()` 한 곳에서만 한다
  (INTEGRATION.md 2-4 — 대조 논리를 복제하면 경보와 위반 기록이 갈린다).

이 모듈이 정하는 것은 오직 **"언제 보낼지"** 하나뿐이다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from .bus import TOPIC_VIOLATION, bus
from .gateway import GatewayClient, payload_from_bus

log = logging.getLogger("omeca.plate_hold")


@dataclass
class _Pending:
    payload: dict[str, Any]
    deadline: float
    cam_id: str
    track_id: Optional[int]


@dataclass
class PlateHoldForwarder:
    """번호판 확정을 기다렸다가 위반 이벤트를 게이트웨이로 넘긴다.

    사용법::

        fwd = PlateHoldForwarder(gateway=gw, lpr=engine.lpr, matcher=engine.matcher)
        fwd.attach()
        for frame_no, ts, frame, dets in src.frames():
            ...
            fwd.tick(ts)        # 매 프레임 - 확정된 것부터 흘려보낸다
        fwd.flush()             # 종료 직전 - 남은 것은 있는 그대로 보낸다

    `tick()` / `flush()` 를 부르지 않으면 보류된 이벤트는 나가지 않는다.
    반드시 루프 안과 종료 직전에 한 번씩 부른다.
    """

    gateway: GatewayClient
    lpr: Any                       # LPRPipeline (confirmed_plate/confidence_of 만 쓴다)
    matcher: Any = None            # VehicleMatcher (선택) — 뒤늦게 붙은 번호판의 DB 대조용
    hold_sec: float = 2.0          # 영상 시각 기준 보류 시간(초)

    # [버그 수정: "유턴+신호위반 ROI가 둘 다 있는 카메라에서 같은 위반이 이벤트에
    # 두 번(중복) 뜬다"] camera_watcher.py는 이런 카메라에 대해 --mode uturn과
    # --mode signal, 두 개의 run_uturn.py 프로세스를 동시에 켠다. 그런데 각 프로세스의
    # ViolationEngine은 --zones에 있는 설정을 전부 로드하므로, 두 프로세스 모두 같은
    # 영상에서 같은 위반(예: 유턴)을 각자 독립적으로 감지해서 버스에 publish한다
    # (engine.py의 bus.publish는 --mode와 무관하게 항상 실행됨). 지금까지는 여기서
    # 그걸 걸러주는 게 하나도 없어서 두 프로세스 모두 게이트웨이로 전송 → 이벤트 중복
    # + 그 중 한쪽만 사건 전/후 캡처(PATCH)를 붙이는 경로를 타서, PATCH가 엉뚱한
    # (사진 없는) 중복 이벤트에 붙어 "사건 발생 전" 사진이 검게 나오는 문제까지 이어졌다.
    # run_uturn.py가 자기 프로세스가 담당하지 않는 위반 유형(반대쪽 --mode가 담당하는
    # 유형)의 값을 넘겨주면, 그 유형은 여기서 조용히 무시한다. high_risk_vehicle처럼
    # 어느 --mode에도 안 걸리는 유형은 그대로 다 통과시킨다(빈 집합이면 필터 없음).
    excluded_types: frozenset = field(default_factory=frozenset)

    _pending: list[_Pending] = field(default_factory=list, init=False)
    _attached: bool = field(default=False, init=False)
    stats: dict[str, int] = field(
        default_factory=lambda: {
            "immediate": 0,   # 발행 시점에 이미 번호판이 있던 건
            "resolved": 0,    # 보류 중 번호판이 확정돼 채워 보낸 건
            "timeout": 0,     # 보류 시간을 넘겨 번호판 없이 보낸 건
        },
        init=False,
    )
    _sent_tracks: set[tuple[str, Optional[int]]] = field(default_factory=set, init=False)

    # ------------------------------------------------------------------
    def attach(self) -> "PlateHoldForwarder":
        """이벤트 버스 구독 시작.

        `GatewayClient.subscribe_to_bus()` 대신 쓴다. 둘 다 붙이면 같은
        이벤트가 두 번 전송되므로 **하나만** 붙여야 한다.
        """
        if not self._attached:
            bus.subscribe(self._on_event)
            self._attached = True
        return self

    def detach(self) -> None:
        if self._attached:
            bus.unsubscribe(self._on_event)
            self._attached = False

    # ------------------------------------------------------------------
    def _on_event(self, topic: str, payload: dict[str, Any]) -> None:
        if topic != TOPIC_VIOLATION:
            return

        # 이 프로세스(--mode)가 담당하지 않는 위반 유형이면 아예 받지 않는다
        # (위 excluded_types 주석 참고 - 중복 이벤트 방지).
        if self.excluded_types and payload.get("type") in self.excluded_types:
            return

        # Deduplicate by cam_id+track_id: if already sent, ignore
        track_id = _as_int(payload.get("track_id"))
        cam_id = str(payload.get("cam_id") or "")
        if (cam_id, track_id) in self._sent_tracks:
            return

        if payload.get("plate_no"):
            # 이미 번호판이 붙어 있다 — 기다릴 이유가 없다.
            self.stats["immediate"] += 1
            self._send(payload)
            return

        ts = _as_float(payload.get("timestamp"), 0.0)
        self._pending.append(
            _Pending(
                payload=payload,
                deadline=ts + self.hold_sec,
                cam_id=str(payload.get("cam_id") or ""),
                track_id=_as_int(payload.get("track_id")),
            )
        )

    # ------------------------------------------------------------------
    def tick(self, now: float) -> None:
        """프레임마다 호출. 번호판이 붙었거나 보류 시간을 넘긴 건을 내보낸다.

        `now` 는 이벤트 payload 의 `timestamp` 와 같은 축(영상 재생 경과 초)을
        쓴다. 처리 속도가 빨라도 느려도 "영상 기준 몇 초 분량의 프레임을
        더 봤는가" 로 판단되므로 결과가 실행 환경에 흔들리지 않는다.
        """
        if not self._pending:
            return

        still: list[_Pending] = []
        for item in self._pending:
            plate = self._lookup_plate(item)
            if plate:
                self._fill_plate(item.payload, plate)
                self.stats["resolved"] += 1
                self._send(item.payload)
            elif now >= item.deadline:
                self.stats["timeout"] += 1
                self._send(item.payload)
            else:
                still.append(item)
        self._pending = still

    def flush(self) -> None:
        """남은 보류 건을 전부 내보낸다(영상 종료·프로세스 종료 시)."""
        for item in self._pending:
            plate = self._lookup_plate(item)
            if plate:
                self._fill_plate(item.payload, plate)
                self.stats["resolved"] += 1
            else:
                self.stats["timeout"] += 1
            self._send(item.payload)
        self._pending = []

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    # ------------------------------------------------------------------
    def _lookup_plate(self, item: _Pending) -> str:
        if item.track_id is None or self.lpr is None:
            return ""
        try:
            # Prefer confirmed plate from the LPR pipeline only.
            confirmed = self.lpr.confirmed_plate(item.cam_id, item.track_id)
            return confirmed or ""
        except Exception:  # 조회 실패가 전송 자체를 막으면 안 된다
            log.debug("확정 번호판 조회 실패", exc_info=True)
            return ""

    def _fill_plate(self, payload: dict[str, Any], plate_no: str) -> None:
        """뒤늦게 확정된 번호판을 payload 에 채운다.

        DB 대조는 반드시 `VehicleMatcher.resolve()` 를 탄다. 경보 경로와
        같은 함수를 써야 OCR 이 한 글자를 틀렸을 때 같은 차량이 '등록'/'미등록'
        으로 갈려 기록되지 않는다(INTEGRATION.md 2-4).
        """
        conf = 0.0
        try:
            conf = float(self.lpr.confidence_of(payload.get("cam_id") or "",
                                                _as_int(payload.get("track_id")) or -1))
        except Exception:
            log.debug("번호판 신뢰도 조회 실패", exc_info=True)

        if self.matcher is not None:
            try:
                vm = self.matcher.resolve(plate_no, count=False)
            except Exception:
                log.debug("번호판 DB 대조 실패", exc_info=True)
                vm = None
            if vm is not None:
                if getattr(vm, "fuzzy", False) and getattr(vm, "matched_plate", ""):
                    detail = payload.get("detail") or ""
                    payload["detail"] = (
                        f"{detail} | 유사매칭(OCR:{vm.plate_no}→DB:{vm.matched_plate})"
                    ).strip(" |")
                    plate_no = vm.matched_plate or plate_no
                if getattr(vm, "status", None) is not None:
                    payload["vehicle_status"] = vm.status.value
                if getattr(vm, "risk_level", None) is not None:
                    payload["risk_level"] = vm.risk_level.value

        payload["plate_no"] = plate_no
        if conf > 0:
            payload["plate_confidence"] = round(conf, 4)

    def _send(self, payload: dict[str, Any]) -> None:
        try:
            track_id = _as_int(payload.get("track_id"))
            cam_id = str(payload.get("cam_id") or "")
            # Avoid sending duplicates for the same cam+track within this forwarder
            if (cam_id, track_id) in self._sent_tracks:
                return
            sent = self.gateway.enqueue(payload_from_bus(payload))
            if sent:
                self._sent_tracks.add((cam_id, track_id))
        except Exception:
            log.exception("게이트웨이 전송 큐 적재 실패")


# --------------------------------------------------------------------------
def _as_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
