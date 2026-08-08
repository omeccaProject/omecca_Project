"""위반 판정에 쓰이는 기하 유틸.

가상 라인 통과 방향 판정, 다각형 ROI 포함 판정, 진행 방향 각도 계산 등
violation/ 모듈이 공통으로 쓰는 순수 함수 모음. 외부 의존성 없음.
"""

from __future__ import annotations

import math
from typing import Iterable, Optional, Sequence

Point = Sequence[float]


def cross_sign(a: Point, b: Point, p: Point) -> float:
    """선분 a→b 기준 점 p의 부호 있는 외적.

    > 0 : 왼쪽,  < 0 : 오른쪽,  == 0 : 선 위
    """
    return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])


def side_of(a: Point, b: Point, p: Point, eps: float = 1e-9) -> int:
    v = cross_sign(a, b, p)
    if v > eps:
        return 1
    if v < -eps:
        return -1
    return 0


def segments_intersect(p1: Point, p2: Point, q1: Point, q2: Point) -> bool:
    """선분 p1p2 와 q1q2 의 교차 여부 (일반 위치 가정)."""
    d1 = side_of(q1, q2, p1)
    d2 = side_of(q1, q2, p2)
    d3 = side_of(p1, p2, q1)
    d4 = side_of(p1, p2, q2)
    if d1 * d2 < 0 and d3 * d4 < 0:
        return True
    # 공선 상의 접촉 케이스
    for a, b, c in ((q1, q2, p1), (q1, q2, p2), (p1, p2, q1), (p1, p2, q2)):
        if side_of(a, b, c) == 0 and _on_segment(a, b, c):
            return True
    return False


def _on_segment(a: Point, b: Point, p: Point) -> bool:
    return (
        min(a[0], b[0]) - 1e-9 <= p[0] <= max(a[0], b[0]) + 1e-9
        and min(a[1], b[1]) - 1e-9 <= p[1] <= max(a[1], b[1]) + 1e-9
    )


def point_in_polygon(point: Point, polygon: Sequence[Point]) -> bool:
    """Ray casting. polygon은 닫히지 않은 정점 리스트."""
    if len(polygon) < 3:
        return False
    x, y = point[0], point[1]
    inside = False
    n = len(polygon)
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i][0], polygon[i][1]
        xj, yj = polygon[j][0], polygon[j][1]
        if (yi > y) != (yj > y):
            x_cross = (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi
            if x_cross > x:
                inside = not inside
        j = i
    return inside


def heading_deg(p_from: Point, p_to: Point) -> float:
    """두 점의 진행 방향(도). 화면 좌표계 기준, 0도 = +x, 반시계 양수."""
    dx = p_to[0] - p_from[0]
    dy = p_to[1] - p_from[1]
    return math.degrees(math.atan2(-dy, dx))  # y축 뒤집어 직관적인 방향으로


def angle_diff(a_deg: float, b_deg: float) -> float:
    """두 각도의 최소 차이 (0 ~ 180)."""
    d = abs((a_deg - b_deg) % 360.0)
    return d if d <= 180.0 else 360.0 - d


def path_length(points: Sequence[Point]) -> float:
    return sum(dist(points[i - 1], points[i]) for i in range(1, len(points)))


def dist(a: Point, b: Point) -> float:
    return math.hypot(b[0] - a[0], b[1] - a[1])


def mean_heading(points: Sequence[Point]) -> Optional[float]:
    """구간 전체의 평균 진행 방향. 벡터 평균으로 각도 wrap 문제를 피한다."""
    if len(points) < 2:
        return None
    sx = sy = 0.0
    for i in range(1, len(points)):
        d = dist(points[i - 1], points[i])
        if d < 1e-6:
            continue
        h = math.radians(heading_deg(points[i - 1], points[i]))
        sx += math.cos(h) * d
        sy += math.sin(h) * d
    if abs(sx) < 1e-9 and abs(sy) < 1e-9:
        return None
    return math.degrees(math.atan2(sy, sx))


def smooth(points: Sequence[Point], window: int = 3) -> list[tuple[float, float]]:
    """이동 평균 스무딩. 탐지 지터로 인한 방향 튐을 줄인다."""
    if window <= 1 or len(points) < window:
        return [(float(p[0]), float(p[1])) for p in points]
    out: list[tuple[float, float]] = []
    half = window // 2
    n = len(points)
    for i in range(n):
        lo, hi = max(0, i - half), min(n, i + half + 1)
        seg = points[lo:hi]
        out.append((sum(p[0] for p in seg) / len(seg), sum(p[1] for p in seg) / len(seg)))
    return out


def bbox_polygon_overlap(bbox_xyxy: Sequence[float], polygon: Sequence[Point]) -> bool:
    """bbox 바닥 중심 또는 꼭짓점 중 하나라도 ROI 안에 있으면 겹침으로 본다."""
    x1, y1, x2, y2 = bbox_xyxy
    candidates: Iterable[Point] = (
        ((x1 + x2) / 2, y2),
        (x1, y1), (x2, y1), (x1, y2), (x2, y2),
        ((x1 + x2) / 2, (y1 + y2) / 2),
    )
    return any(point_in_polygon(c, polygon) for c in candidates)
