"""이벤트 버스.

LPR / 위반 감지 모듈은 이 버스로만 이벤트를 흘려보내고,
실제 전달(WebSocket, Spring Boot 게이트웨이 POST)은 구독자가 담당한다.
모듈 간 결합을 끊어 테스트에서 구독자만 갈아끼우면 검증이 된다.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from typing import Any, Callable, Deque

log = logging.getLogger("omeca.bus")

Subscriber = Callable[[str, dict[str, Any]], None]


class EventBus:
    def __init__(self, history: int = 500) -> None:
        self._subs: list[Subscriber] = []
        self._lock = threading.Lock()
        self.history: Deque[tuple[str, dict[str, Any]]] = deque(maxlen=history)

    def subscribe(self, fn: Subscriber) -> Subscriber:
        with self._lock:
            self._subs.append(fn)
        return fn

    def unsubscribe(self, fn: Subscriber) -> None:
        with self._lock:
            if fn in self._subs:
                self._subs.remove(fn)

    def publish(self, topic: str, payload: dict[str, Any]) -> None:
        with self._lock:
            subs = list(self._subs)
            self.history.append((topic, payload))
        for fn in subs:
            try:
                fn(topic, payload)
            except Exception:  # 구독자 하나가 죽어도 파이프라인은 계속 돈다
                log.exception("subscriber failed: topic=%s", topic)

    def recent(self, topic: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        items = [p for t, p in self.history if topic is None or t == topic]
        return items[-limit:]

    def clear(self) -> None:
        with self._lock:
            self.history.clear()


# 토픽 상수
TOPIC_PLATE = "lpr.plate"
TOPIC_ALERT = "vehicle.alert"        # 고위험 차량 경보
TOPIC_VIOLATION = "violation.event"  # 신호위반 / 불법유턴

bus = EventBus()
