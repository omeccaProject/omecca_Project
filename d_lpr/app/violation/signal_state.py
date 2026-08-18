"""신호 상태 제공자.

실제 운영에서는 지자체 교통신호제어기(UTIS/COSMOS) 연동 API를 붙이지만,
연동 전에는 주기 기반 시뮬레이터로 동일한 인터페이스를 제공한다.
영상만으로 판정해야 하는 현장을 위해 신호등 색상 인식 결과를 주입하는
경로(`update`)도 함께 열어둔다.
"""

from __future__ import annotations

import threading
import time
from enum import Enum
from typing import Optional


class SignalPhase(str, Enum):
    RED = "red"
    YELLOW = "yellow"
    GREEN = "green"                 # 직진 녹색
    LEFT_ARROW = "left_arrow"       # 좌회전 화살표 (유턴 허용 신호)
    GREEN_LEFT = "green_left"       # 직진 + 좌회전 동시
    UNKNOWN = "unknown"


class PedPhase(str, Enum):
    """보행 신호. 유턴 허용 조건의 하나로 쓰인다.

    신호제어기 연동 전에는 영상 타임라인으로 입력한다.
    """

    RED = "red"
    GREEN = "green"
    UNKNOWN = "unknown"


# 유턴이 허용되는 차량 신호 (좌회전 화살표가 켜진 상태)
UTURN_ALLOWED_PHASES = {SignalPhase.LEFT_ARROW, SignalPhase.GREEN_LEFT}


class Movement(str, Enum):
    """이동류. 신호는 '교차로 하나에 하나'가 아니라 진입방향별·이동류별로 있다.

    KLID 실시간 신호 API 가 이 여섯 가지를 방향별로 따로 준다. 특히 유턴 신호가
    따로 오기 때문에, 좌회전 화살표를 보고 유턴 허용을 **추론**하지 않고
    유턴 신호를 **직접** 볼 수 있다.
    """

    STRAIGHT = "straight"     # 직진
    LEFT = "left"             # 좌회전
    UTURN = "uturn"           # 유턴
    PED = "ped"               # 보행
    BUS = "bus"               # 버스
    BIKE = "bike"             # 자전거


class SignalProvider:
    """신호 상태 조회 인터페이스.

    실제 신호제어기가 붙으면 이 인터페이스만 구현하면 되고,
    판정 로직(detectors.py)은 손대지 않는다.
    """

    def phase_at(self, signal_id: str, ts: float) -> SignalPhase:  # pragma: no cover
        raise NotImplementedError

    def last_change(self, signal_id: str, ts: float) -> float:  # pragma: no cover
        """해당 시각 기준 직전 신호 전환 시각."""
        raise NotImplementedError

    def ped_phase_at(self, signal_id: str, ts: float) -> PedPhase:
        """보행 신호. 정보가 없으면 UNKNOWN 을 돌려준다.

        UNKNOWN 이면 판정 로직은 보행 신호를 근거로 쓰지 않는다.
        """
        return PedPhase.UNKNOWN

    def movement_at(self, signal_id: str, ts: float, movement: Movement) -> SignalPhase:
        """이동류(직진/좌회전/유턴/보행)별 신호 상태.

        이동류를 구분해 주지 않는 제공자(고정주기·타임라인 등)는 차량 신호를
        그대로 돌려주고, 유턴처럼 근거가 없는 것은 UNKNOWN 을 준다.
        판정 쪽은 UNKNOWN 이면 다른 근거로 넘어가므로 이 기본 구현으로 안전하다.
        """
        if movement is Movement.PED:
            ped = self.ped_phase_at(signal_id, ts)
            if ped is PedPhase.GREEN:
                return SignalPhase.GREEN
            if ped is PedPhase.RED:
                return SignalPhase.RED
            return SignalPhase.UNKNOWN
        if movement in (Movement.STRAIGHT, Movement.LEFT):
            return self.phase_at(signal_id, ts)
        return SignalPhase.UNKNOWN      # 유턴·버스·자전거는 알 수 없음


class FixedCycleSignal(SignalProvider):
    """고정 주기 신호 시뮬레이터.

    green → yellow → red 순환. 신호 전환 직후 유예(grace) 판정을 위해
    직전 전환 시각도 계산해 준다.
    """

    def __init__(
        self,
        green_sec: float = 30.0,
        yellow_sec: float = 4.0,
        red_sec: float = 26.0,
        offset: float = 0.0,
    ) -> None:
        self.green = float(green_sec)
        self.yellow = float(yellow_sec)
        self.red = float(red_sec)
        self.offset = float(offset)

    @property
    def cycle(self) -> float:
        return self.green + self.yellow + self.red

    def _pos(self, ts: float) -> float:
        return (ts - self.offset) % self.cycle

    def phase_at(self, signal_id: str, ts: float) -> SignalPhase:
        t = self._pos(ts)
        if t < self.green:
            return SignalPhase.GREEN
        if t < self.green + self.yellow:
            return SignalPhase.YELLOW
        return SignalPhase.RED

    def last_change(self, signal_id: str, ts: float) -> float:
        t = self._pos(ts)
        base = ts - t
        for boundary in (0.0, self.green, self.green + self.yellow):
            pass
        if t < self.green:
            return base
        if t < self.green + self.yellow:
            return base + self.green
        return base + self.green + self.yellow


class ManualSignal(SignalProvider):
    """외부에서 상태를 밀어 넣는 방식 (신호기 연동 / 영상 색상 인식용)."""

    def __init__(self, default: SignalPhase = SignalPhase.UNKNOWN) -> None:
        self.default = default
        self._state: dict[str, tuple[SignalPhase, float]] = {}
        self._ped: dict[str, PedPhase] = {}
        self._lock = threading.Lock()

    def update(self, signal_id: str, phase: SignalPhase, ts: Optional[float] = None) -> None:
        with self._lock:
            cur = self._state.get(signal_id)
            now = ts if ts is not None else time.time()
            if cur is None or cur[0] != phase:
                self._state[signal_id] = (phase, now)

    def phase_at(self, signal_id: str, ts: float) -> SignalPhase:
        with self._lock:
            cur = self._state.get(signal_id)
        return cur[0] if cur else self.default

    def update_ped(self, signal_id: str, phase: PedPhase) -> None:
        """보행 신호를 밀어 넣는다 (연동 가정 / 수동 입력용)."""
        with self._lock:
            self._ped[signal_id] = phase

    def ped_phase_at(self, signal_id: str, ts: float) -> PedPhase:
        with self._lock:
            return self._ped.get(signal_id, PedPhase.UNKNOWN)

    def last_change(self, signal_id: str, ts: float) -> float:
        with self._lock:
            cur = self._state.get(signal_id)
        return cur[1] if cur else 0.0


class TimelineSignal(SignalProvider):
    """영상의 실제 신호 변화를 그대로 재생하는 제공자.

    신호제어기 연동 전 단계에서, 촬영한 영상을 보며 신호가 바뀌는 시각을
    적어두면 판정에 그대로 쓸 수 있다. 값이 **실제 영상의 진짜 신호**이므로
    판정 결과도 진짜다. 자동으로 못 읽을 뿐이다.

    타임라인 JSON 형식 (초 단위는 영상 시작 기준)

        {
          "SIG-A": [
            {"at": 0,  "phase": "green"},
            {"at": 32, "phase": "yellow"},
            {"at": 36, "phase": "red"},
            {"at": 62, "phase": "left_arrow"},
            {"at": 70, "phase": "green"}
          ],
          "SIG-A-PED": [
            {"at": 0,  "ped": "red"},
            {"at": 62, "ped": "green"},
            {"at": 78, "ped": "red"}
          ]
        }

    보행 신호는 `signal_id + "-PED"` 키에 넣거나 같은 항목에 `ped` 를 함께 쓴다.
    """

    PED_SUFFIX = "-PED"

    def __init__(self, timeline: Optional[dict] = None, start_ts: float = 0.0) -> None:
        self.start_ts = start_ts
        self._veh: dict[str, list[tuple[float, SignalPhase]]] = {}
        self._ped: dict[str, list[tuple[float, PedPhase]]] = {}
        if timeline:
            self.load(timeline)

    # ------------------------------------------------------------------
    def load(self, timeline: dict) -> "TimelineSignal":
        for sig_id, entries in timeline.items():
            # "_comment" 같은 주석 키와 리스트가 아닌 값은 건너뛴다
            if sig_id.startswith("_") or not isinstance(entries, list):
                continue
            base = sig_id[: -len(self.PED_SUFFIX)] if sig_id.endswith(self.PED_SUFFIX) else sig_id
            veh: list[tuple[float, SignalPhase]] = []
            ped: list[tuple[float, PedPhase]] = []
            for e in entries or []:
                if not isinstance(e, dict):
                    continue
                at = float(e.get("at", 0))
                if "phase" in e:
                    veh.append((at, _to_phase(e["phase"])))
                if "ped" in e:
                    ped.append((at, _to_ped(e["ped"])))
            if veh:
                self._veh.setdefault(base, []).extend(veh)
            if ped:
                self._ped.setdefault(base, []).extend(ped)
        for d in (self._veh, self._ped):
            for k in d:
                d[k].sort(key=lambda t: t[0])
        return self

    @classmethod
    def from_file(cls, path, start_ts: float = 0.0) -> "TimelineSignal":
        import json
        from pathlib import Path

        p = Path(path)
        if not p.exists():
            return cls(start_ts=start_ts)
        return cls(json.loads(p.read_text(encoding="utf-8")), start_ts=start_ts)

    def set_start(self, ts: float) -> None:
        """영상 첫 프레임의 실제 시각. 이후 조회는 이 값 기준 상대 초로 계산한다."""
        self.start_ts = ts

    # ------------------------------------------------------------------
    def _lookup(self, entries, ts: float):
        """ts 이전의 마지막 항목을 찾는다."""
        rel = ts - self.start_ts
        found = None
        for at, val in entries:
            if at <= rel:
                found = (at, val)
            else:
                break
        return found

    def phase_at(self, signal_id: str, ts: float) -> SignalPhase:
        hit = self._lookup(self._veh.get(signal_id, []), ts)
        return hit[1] if hit else SignalPhase.UNKNOWN

    def last_change(self, signal_id: str, ts: float) -> float:
        hit = self._lookup(self._veh.get(signal_id, []), ts)
        return (self.start_ts + hit[0]) if hit else 0.0

    def ped_phase_at(self, signal_id: str, ts: float) -> PedPhase:
        hit = self._lookup(self._ped.get(signal_id, []), ts)
        return hit[1] if hit else PedPhase.UNKNOWN


def _to_phase(v) -> SignalPhase:
    try:
        return SignalPhase(str(v).strip().lower())
    except ValueError:
        return SignalPhase.UNKNOWN


def _to_ped(v) -> PedPhase:
    try:
        return PedPhase(str(v).strip().lower())
    except ValueError:
        return PedPhase.UNKNOWN
