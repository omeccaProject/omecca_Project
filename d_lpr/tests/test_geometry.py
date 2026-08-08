"""기하 유틸 및 가상 라인 통과 판정 테스트."""

import pytest

from app.core.geometry import (
    angle_diff, heading_deg, mean_heading, point_in_polygon, segments_intersect, side_of,
)
from app.violation.roi import VirtualLine, Zone


class TestSide:
    def test_above_below(self):
        a, b = (0, 100), (200, 100)
        assert side_of(a, b, (100, 50)) == -1     # 위쪽
        assert side_of(a, b, (100, 150)) == 1     # 아래쪽
        assert side_of(a, b, (100, 100)) == 0     # 선 위


class TestIntersect:
    def test_crossing(self):
        assert segments_intersect((0, 0), (10, 10), (0, 10), (10, 0))

    def test_parallel(self):
        assert not segments_intersect((0, 0), (10, 0), (0, 5), (10, 5))

    def test_beyond_segment_end(self):
        # 라인 연장선 상에서만 만나는 경우는 통과로 보지 않는다
        assert not segments_intersect((100, 0), (100, 20), (0, 10), (50, 10))


class TestVirtualLine:
    @pytest.fixture
    def line(self):
        return VirtualLine("L1", (300, 700), (1600, 700), direction="negative")

    def test_forward_cross(self, line):
        d = line.crossed((800, 650), (800, 750))
        assert d == -1 and line.is_forward(d)

    def test_reverse_cross(self, line):
        d = line.crossed((800, 750), (800, 650))
        assert d == 1 and not line.is_forward(d)

    def test_no_cross(self, line):
        assert line.crossed((800, 600), (800, 650)) is None

    def test_outside_segment_not_counted(self, line):
        # x=2000 은 라인 구간(300~1600) 밖 → 통과 아님
        assert line.crossed((2000, 650), (2000, 750)) is None

    def test_point_exactly_on_line(self, line):
        """좌표가 라인 위에 정확히 놓이면 단순 비교로는 통과를 놓친다."""
        assert line.crossed((800, 650), (800, 700)) is None
        # 마지막 비영 부호 기준 판정으로는 잡힌다
        assert line.crossed_from((800, 650), -1, (800, 750)) == -1

    def test_both_direction(self):
        ln = VirtualLine("L2", (0, 100), (200, 100), direction="both")
        assert ln.is_forward(1) and ln.is_forward(-1)


class TestZone:
    def test_contains(self):
        z = Zone("Z", [(0, 0), (100, 0), (100, 100), (0, 100)])
        assert z.contains((50, 50))
        assert not z.contains((150, 50))

    def test_polygon_edge_case(self):
        assert not point_in_polygon((5, 5), [(0, 0), (10, 0)])   # 정점 부족


class TestHeading:
    def test_direction_down_is_negative_90(self):
        # 화면 좌표에서 아래로 이동 = -90도
        assert heading_deg((0, 0), (0, 100)) == pytest.approx(-90, abs=1)

    def test_direction_right_is_zero(self):
        assert heading_deg((0, 0), (100, 0)) == pytest.approx(0, abs=1)

    def test_uturn_angle_is_180(self):
        down = mean_heading([(0, 0), (0, 50), (0, 100)])
        up = mean_heading([(0, 100), (0, 50), (0, 0)])
        assert angle_diff(down, up) == pytest.approx(180, abs=1)

    def test_left_turn_angle_is_90(self):
        down = mean_heading([(0, 0), (0, 50), (0, 100)])
        left = mean_heading([(0, 100), (-50, 100), (-100, 100)])
        assert angle_diff(down, left) == pytest.approx(90, abs=1)

    def test_wrap_around(self):
        assert angle_diff(179, -179) == pytest.approx(2, abs=0.1)
