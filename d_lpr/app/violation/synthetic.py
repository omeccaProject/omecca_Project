"""합성 검증용 영상·탐지 소스.

실제 영상과 YOLO 없이도 **판정 로직 전체**가 도는지 확인하기 위한 것이다.
차량 네 대를 화면에 그리고, 같은 좌표를 `Detection` 으로도 내보낸다.
`VehicleSource` 와 인터페이스가 같아 `run_uturn.py --fake` 에서 바꿔 끼운다.

    #101 유턴      중앙선을 넘어 방향 반전   → 불법 유턴으로 잡혀야 함
    #102 좌회전    중앙선을 넘지만 반전 아님 → 안 잡혀야 함 (오탐 반례)
    #103 직진      반대 차로, 선 안 넘음     → 안 잡혀야 함
    #104 신호위반  적색에 정지선→진출선 통과 → 신호 위반으로 잡혀야 함

배우마다 **한 가지만** 검증하도록 차로를 분리해 두었다. 정지선·진출선은
#104 가 지나는 차로(x 1080~1270)에만 걸쳐 있어서, 좌회전 차(#102)가
같은 적색 구간을 지나가도 신호위반으로 잡히지 않는다.

즉 **정확히 2건**(유턴 1 + 신호위반 1)이 나와야 정상이다.
신호는 `fake_signal_timeline()` 이 적색으로 고정해 준다.
"""

from __future__ import annotations

import math
from typing import Any, Iterator

from ..core.schemas import BBox, Detection, ObjectClass

W, H = 1280, 720
CENTER_X = 640                       # 중앙선 위치 (draw_roi 없이 쓰는 기본 좌표)
STOP_Y = 300                         # 정지선 (신호위반 판정용)
EXIT_Y = 560                         # 진출선


def default_zone_dict(cam_id: str = "CAM-FAKE") -> dict:
    """합성 영상에 맞는 ROI 설정."""
    return {
        "cameras": [{
            "cam_id": cam_id,
            "name": "합성 검증용",
            "location": [37.5665, 126.9780],
            "lines": [
                {
                    "line_id": "center_fake",
                    "name": "중앙선(합성)",
                    "p1": [CENTER_X, 80], "p2": [CENTER_X, H - 40],
                    "direction": "both",
                    "line_type": "center",
                    "uturn_allowed": False,
                    "signal_id": "SIG-1",
                },
                {
                    "line_id": "stop_fake",
                    "name": "정지선(합성)",
                    "p1": [1080, STOP_Y], "p2": [1270, STOP_Y],
                    "direction": "negative",          # 위 → 아래 통과가 진행 방향
                    "line_type": "stop",
                    "signal_id": "SIG-1",
                },
                {
                    "line_id": "exit_fake",
                    "name": "진출선(합성)",
                    "p1": [1080, EXIT_Y], "p2": [1270, EXIT_Y],
                    "direction": "negative",
                    "line_type": "exit",
                    "signal_id": "SIG-1",
                },
            ],
            "zones": [],
            "intersections": [{
                "intersection_id": "INT-FAKE",
                "stop_line": "stop_fake",
                "exit_line": "exit_fake",
                "signal_id": "SIG-1",
            }],
        }]
    }


# --------------------------------------------------------------------------
def _uturn_xy(t: float) -> tuple[float, float] | None:
    """오른쪽 차로를 내려오다 중앙선을 넘어 반대편으로 되돌아 올라간다."""
    if t < 0 or t > 9.0:
        return None
    if t < 3.5:                                   # 진입 (아래로)
        return (760.0, 120.0 + (520.0 - 120.0) * (t / 3.5))
    if t < 5.5:                                   # 선회 (중앙선 통과)
        th = math.pi * (t - 3.5) / 2.0
        return (640.0 + 120.0 * math.cos(th), 520.0 + 45.0 * math.sin(th))
    return (520.0, 520.0 - (520.0 - 120.0) * ((t - 5.5) / 3.5))   # 진출 (위로)


def _leftturn_xy(t: float) -> tuple[float, float] | None:
    """좌회전. 중앙선을 넘지만 방향 반전은 아니므로 유턴이 아니어야 한다."""
    if t < 1.0 or t > 8.0:
        return None
    u = (t - 1.0) / 7.0
    if u < 0.5:
        return (980.0, 120.0 + 480.0 * (u / 0.5))
    th = math.pi / 2 * ((u - 0.5) / 0.5)
    return (980.0 - 720.0 * math.sin(th), 600.0 - 60.0 * (1 - math.cos(th)))


def _straight_xy(t: float) -> tuple[float, float] | None:
    """반대 차로 직진. 중앙선을 넘지 않는다."""
    if t < 0.5 or t > 8.0:
        return None
    u = (t - 0.5) / 7.5
    return (430.0, 660.0 - 560.0 * u)


def _uturn_after_wait_xy(t: float) -> tuple[float, float] | None:
    """**신호 대기 후** 유턴. 실제 교차로에서 가장 흔한 형태다.

    진입 → 정지선에서 4초 정차 → 유턴. 진입 방향을 '몇 초 전'으로 되돌아가서
    재면 정차 구간에 떨어져 방향이 엉뚱하게 나온다. 이동 거리 기준으로 되돌아가야
    한다. `_approach_heading()` 의 회귀 시나리오.
    """
    if t < 0 or t > 13.0:
        return None
    if t < 2.5:                                   # 진입
        return (760.0, 120.0 + (520.0 - 120.0) * (t / 2.5))
    if t < 7.5:                                   # 신호 대기 (5초 정차)
        return (760.0, 520.0)
    if t < 9.5:                                   # 선회 (중앙선 통과)
        th = math.pi * (t - 7.5) / 2.0
        return (640.0 + 120.0 * math.cos(th), 520.0 + 45.0 * math.sin(th))
    return (520.0, 520.0 - (520.0 - 120.0) * ((t - 9.5) / 3.5))   # 진출


def _redlight_xy(t: float) -> tuple[float, float] | None:
    """적색인데 정지선을 넘어 진출선까지 통과. 신호 위반으로 잡혀야 한다."""
    if t < 1.0 or t > 7.0:
        return None
    u = (t - 1.0) / 6.0
    return (1170.0, 140.0 + (660.0 - 140.0) * u)   # 정지선·진출선을 차례로 통과


ACTORS = [
    (101, _uturn_xy, (60, 120, 240)),        # 유턴 (BGR)
    (102, _leftturn_xy, (240, 180, 60)),     # 좌회전 (반례)
    (103, _straight_xy, (120, 220, 120)),    # 직진 (반례)
    (104, _redlight_xy, (60, 60, 220)),      # 신호 위반
]


def fake_signal_timeline() -> dict:
    """합성 장면용 신호. 처음부터 끝까지 적색이라 #104 는 위반이 된다."""
    return {"SIG-1": [{"at": -100, "phase": "red"}]}


# --------------------------------------------------------------------------
class SyntheticSource:
    """`VehicleSource` 와 동일한 인터페이스의 합성 소스."""

    def __init__(self, cam_id: str = "CAM-FAKE", seconds: float = 10.0,
                 fps: float = 15.0, stride: int = 1) -> None:
        self.cam_id = cam_id
        self.fps = fps
        self.stride = max(1, stride)
        self.size = (W, H)
        self.total = int(seconds * fps)
        self.tracker_name = "synthetic"

    # ------------------------------------------------------------------
    def frames(self) -> Iterator[tuple[int, float, Any, list[Detection]]]:
        import cv2
        import numpy as np

        for frame_no in range(self.total):
            if frame_no % self.stride:
                continue
            ts = frame_no / self.fps
            img = np.full((H, W, 3), 45, dtype=np.uint8)
            cv2.line(img, (CENTER_X, 0), (CENTER_X, H), (0, 200, 220), 2)

            dets: list[Detection] = []
            for tid, fn, color in ACTORS:
                xy = fn(ts)
                if xy is None:
                    continue
                x, y = xy
                bb = BBox(x - 42, y - 105, x + 42, y)
                cv2.rectangle(img, *(_ints(bb)), color, -1)
                cv2.putText(img, f"#{tid}", (int(x) - 20, int(y) - 112),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
                dets.append(Detection(cam_id=self.cam_id, track_id=tid,
                                      cls=ObjectClass.CAR, bbox=bb, timestamp=ts,
                                      confidence=0.9, frame_no=frame_no))
            yield frame_no, ts, img, dets


def _ints(bb: BBox):
    x1, y1, x2, y2 = bb.to_xyxy()
    return (x1, y1), (x2, y2)
