"""track별 궤적 버퍼.

ByteTrack(김준호 담당)이 부여한 track_id 기준으로 차량 접지점 좌표를 쌓아
위반 판정 모듈에 넘긴다. 프레임 번호와 시각을 함께 보관해야
증거 리포트(장성혁 담당)에서 캡처 구간을 특정할 수 있다.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Iterator, Optional

from ..core.geometry import dist, mean_heading, path_length, smooth
from ..core.schemas import Detection


@dataclass
class TrackPoint:
    x: float
    y: float
    ts: float
    frame_no: int = 0
    # 그 시점 차량 박스의 높이(px). 화면상 차량 크기를 길이의 기준자로 쓴다.
    # 4K든 720p든, 멀든 가깝든 "차 1대 길이" 로 환산할 수 있다.
    car_h: float = 0.0

    def as_xy(self) -> tuple[float, float]:
        return (self.x, self.y)


@dataclass
class Track:
    cam_id: str
    track_id: int
    points: Deque[TrackPoint] = field(default_factory=lambda: deque(maxlen=120))
    plate_no: str = ""
    plate_confidence: float = 0.0
    # 라인별 마지막 통과 정보: line_id -> (방향, 시각, frame_no)
    crossings: dict[str, tuple[int, float, int]] = field(default_factory=dict)
    # 라인별 마지막 비영 부호와 그 지점: line_id -> (side, (x, y))
    line_state: dict[str, tuple[int, tuple[float, float]]] = field(default_factory=dict)
    # 위반 유형별 마지막 발행 시각 (쿨다운)
    last_emitted: dict[str, float] = field(default_factory=dict)
    zone_entered: dict[str, int] = field(default_factory=dict)  # zone_id -> 진입 시점 index

    def add(self, p: TrackPoint) -> None:
        self.points.append(p)

    @property
    def last(self) -> Optional[TrackPoint]:
        return self.points[-1] if self.points else None

    @property
    def prev(self) -> Optional[TrackPoint]:
        return self.points[-2] if len(self.points) >= 2 else None

    def xy_list(self) -> list[tuple[float, float]]:
        return [p.as_xy() for p in self.points]

    def recent_xy(self, n: int) -> list[tuple[float, float]]:
        pts = list(self.points)[-n:]
        return [p.as_xy() for p in pts]

    def speed(self, n: int = 5) -> float:
        """최근 n포인트 평균 이동량(px/frame). 정지 차량 오탐 방지에 쓴다."""
        pts = list(self.points)[-n:]
        if len(pts) < 2:
            return 0.0
        total = sum(dist(pts[i - 1].as_xy(), pts[i].as_xy()) for i in range(1, len(pts)))
        return total / (len(pts) - 1)

    def total_length(self) -> float:
        return path_length(self.xy_list())

    def heading(self, lo: int = 0, hi: Optional[int] = None) -> Optional[float]:
        pts = self.xy_list()[lo:hi]
        return mean_heading(smooth(pts, 3))

    def car_size(self, n: int = 10) -> float:
        """최근 n포인트의 차량 박스 높이 중앙값. 0이면 정보 없음."""
        vals = sorted(p.car_h for p in list(self.points)[-n:] if p.car_h > 0)
        return vals[len(vals) // 2] if vals else 0.0

    def frames(self) -> list[int]:
        return [p.frame_no for p in self.points]

    def __len__(self) -> int:
        return len(self.points)


class TrackStore:
    """cam_id + track_id 별 Track 관리."""

    def __init__(self, history: int = 120) -> None:
        self.history = history
        self._tracks: dict[tuple[str, int], Track] = {}

    def update(self, det: Detection) -> Track:
        key = (det.cam_id, det.track_id)
        t = self._tracks.get(key)
        if t is None:
            t = Track(det.cam_id, det.track_id, deque(maxlen=self.history))
            self._tracks[key] = t
        x, y = det.bbox.bottom_center
        t.add(TrackPoint(x, y, det.timestamp, det.frame_no, det.bbox.height))
        return t

    def get(self, cam_id: str, track_id: int) -> Optional[Track]:
        return self._tracks.get((cam_id, track_id))

    def attach_plate(self, cam_id: str, track_id: int, plate_no: str, conf: float) -> None:
        t = self._tracks.get((cam_id, track_id))
        if t is not None:
            t.plate_no = plate_no
            t.plate_confidence = conf

    def prune(self, now: float, ttl_sec: float = 60.0) -> int:
        stale = [
            k for k, t in self._tracks.items()
            if t.last is not None and now - t.last.ts > ttl_sec
        ]
        for k in stale:
            del self._tracks[k]
        return len(stale)

    def __iter__(self) -> Iterator[Track]:
        return iter(self._tracks.values())

    def __len__(self) -> int:
        return len(self._tracks)

    def clear(self) -> None:
        self._tracks.clear()
