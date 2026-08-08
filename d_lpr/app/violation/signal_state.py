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
    GREEN = "green"
    UNKNOWN = "unknown"


class SignalProvider:
    """신호 상태 조회 인터페이스."""

    def phase_at(self, signal_id: str, ts: float) -> SignalPhase:  # pragma: no cover
        raise NotImplementedError

    def last_change(self, signal_id: str, ts: float) -> float:  # pragma: no cover
        """해당 시각 기준 직전 신호 전환 시각."""
        raise NotImplementedError


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

    def last_change(self, signal_id: str, ts: float) -> float:
        with self._lock:
            cur = self._state.get(signal_id)
        return cur[1] if cur else 0.0
