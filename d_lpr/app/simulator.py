"""Mock 궤적 생성기.

CCTV 영상과 YOLO 가중치가 없어도 위반 판정 로직을 끝까지 돌려볼 수 있도록
가상의 차량 궤적(Detection 시퀀스)을 만들어 준다.
데모 실행과 단위 테스트가 같은 생성기를 공유한다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterator, Optional

from .core.schemas import BBox, Detection, ObjectClass

FPS = 10.0
DT = 1.0 / FPS


def _bbox_at(x: float, y: float, w: float = 90.0, h: float = 120.0) -> BBox:
    """접지점(x, y)을 기준으로 차량 bbox 생성."""
    return BBox(x - w / 2, y - h, x + w / 2, y)


@dataclass
class Scenario:
    name: str
    cam_id: str
    track_id: int
    plate_no: Optional[str]
    points: list[tuple[float, float]]
    expect: str = ""     # 기대 결과 설명 (데모 출력용)

    def detections(self, t0: float, frame0: int = 0) -> Iterator[Detection]:
        for i, (x, y) in enumerate(self.points):
            yield Detection(
                cam_id=self.cam_id,
                track_id=self.track_id,
                cls=ObjectClass.CAR,
                bbox=_bbox_at(x, y),
                timestamp=t0 + i * DT,
                confidence=0.9,
                frame_no=frame0 + i,
            )


# --------------------------------------------------------------------------
# 궤적 생성 헬퍼
# --------------------------------------------------------------------------
def straight_down(x: float, y_from: float, y_to: float, step: float = 22.0) -> list[tuple[float, float]]:
    """북 → 남 직진. 정지선/진출선을 순서대로 통과한다."""
    n = max(2, int(abs(y_to - y_from) / step))
    return [(x, y_from + (y_to - y_from) * i / n) for i in range(n + 1)]


def uturn_path(
    x_in: float, x_out: float, y_top: float, y_bottom: float, step: float = 18.0
) -> list[tuple[float, float]]:
    """내려왔다가 반원을 그리며 되돌아 올라가는 유턴 궤적."""
    pts: list[tuple[float, float]] = []

    n_down = max(3, int((y_bottom - y_top) / step))
    for i in range(n_down + 1):
        pts.append((x_in, y_top + (y_bottom - y_top) * i / n_down))

    # 반원 구간 (아래쪽에서 좌측으로 선회)
    cx = (x_in + x_out) / 2.0
    r = abs(x_in - x_out) / 2.0
    for i in range(1, 13):
        th = math.pi * i / 12.0
        pts.append((cx + r * math.cos(th) * (1 if x_in > x_out else -1),
                    y_bottom + r * 0.35 * math.sin(th)))

    n_up = max(3, int((y_bottom - y_top) / step))
    for i in range(1, n_up + 1):
        pts.append((x_out, y_bottom - (y_bottom - y_top) * i / n_up))
    return pts


def left_turn(x: float, y_from: float, y_to: float, x_to: float) -> list[tuple[float, float]]:
    """좌회전 궤적. 유턴 오탐이 나지 않아야 하는 반례."""
    pts = straight_down(x, y_from, y_to, step=22.0)
    n = 10
    for i in range(1, n + 1):
        th = math.pi / 2 * i / n
        pts.append((x - (x - x_to) * math.sin(th), y_to - (x - x_to) * (1 - math.cos(th)) * 0.25))
    return pts


# --------------------------------------------------------------------------
# 시연 시나리오
# --------------------------------------------------------------------------
def demo_scenarios() -> list[Scenario]:
    return [
        Scenario(
            name="적색 신호 직진 통과",
            cam_id="CAM-001", track_id=101, plate_no="12가3456",
            points=straight_down(760, 480, 1030),
            expect="신호 위반 1건",
        ),
        Scenario(
            name="수배 차량 통과(녹색)",
            cam_id="CAM-001", track_id=102, plate_no="33아3333",
            points=straight_down(880, 480, 1030),
            expect="고위험 차량 경보 1건 (위반 아님)",
        ),
        Scenario(
            name="유턴 금지 구간 유턴(녹색)",
            cam_id="CAM-001", track_id=103, plate_no="44자4444",
            points=uturn_path(900, 700, 640, 960),
            expect="불법 유턴 1건",
        ),
        Scenario(
            name="DB 미등록 차량",
            cam_id="CAM-001", track_id=104, plate_no="99하9999",
            points=straight_down(1020, 480, 1030),
            expect="미등록 고위험 경보 1건",
        ),
        Scenario(
            name="정상 직진(녹색)",
            cam_id="CAM-001", track_id=105, plate_no="34나5678",
            points=straight_down(1150, 480, 1030),
            expect="이벤트 없음",
        ),
        Scenario(
            name="좌회전(유턴 오탐 반례)",
            cam_id="CAM-001", track_id=106, plate_no="56다7890",
            points=left_turn(1300, 480, 900, 500),
            expect="이벤트 없음",
        ),
    ]
