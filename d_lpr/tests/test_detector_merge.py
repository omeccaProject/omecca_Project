"""번호판 검출 — 끊어진 글자 조각 잇기.

EasyOCR 의 글자 검출은 번호판을 통째로 잡지 않고 '100라' + '7873' 처럼
조각으로 내놓는 일이 흔하다. 그 조각을 다시 이어야 번호 전체를 읽는다.

여기 좌표는 **실제 사진에서 측정한 값**이다 (`bench_lpr.py --debug-fail`).
"""

from __future__ import annotations

from app.core.schemas import BBox
from app.lpr.detector import _merge_text_boxes


def widths(merged):
    return [(b.x2 - b.x1, t) for b, t, _ in merged]


class TestMergeAcrossInterloper:
    """다른 줄 글자가 사이에 끼어도 이어야 한다.

    x 좌표 순으로 늘어놓으면 차 로고·차종 표기 같은 **다른 줄** 글자가
    번호판 조각 사이에 끼어든다. 바로 앞 조각하고만 비교하면 거기서
    연결이 끊겨 번호판이 영영 반쪽만 남는다. 실제로 `100라7873` 이
    `100라` 로 잘렸고, 사이에 낀 것은 KIA 로고였다.
    """

    def test_kia_logo_between_plate_halves(self):
        items = [
            (BBox(226, 307, 696, 610), "100라", 0.71),
            (BBox(629, 373, 1138, 694), "7873", 0.68),
            (BBox(386, 78, 611, 232), "KIA", 0.40),      # 위쪽 다른 줄
        ]
        merged = _merge_text_boxes(items)
        texts = {t for _, t, _ in merged}
        assert "100라7873" in texts, widths(merged)
        assert "KIA" in texts                            # 로고는 따로 남아야

    def test_logo_below_plate(self):
        items = [
            (BBox(223, 266, 471, 412), "46오", 0.53),
            (BBox(487, 194, 786, 374), "4695", 0.68),
            (BBox(423, 0, 559, 59), "logo", 0.30),
        ]
        texts = {t for _, t, _ in _merge_text_boxes(items)}
        assert "46오4695" in texts


class TestOverlappingFragments:
    """조각이 가로로 **겹칠** 때도 이어야 한다.

    번호판이 크게 찍히면 검출 상자가 서로 겹친다. 간격을 한 방향으로만
    (`뒤.x1 - 앞.x2`) 재면 겹칠 때 음수가 나오는데, 조각 순서가 뒤바뀌면
    엉뚱하게 큰 양수가 되어 '멀다'고 판단해 버린다.
    """

    def test_overlapping_halves(self):
        items = [
            (BBox(228, 274, 719, 659), "155주", 0.59),
            (BBox(497, 396, 1282, 829), "2646", 0.55),   # x 가 앞 조각과 겹침
        ]
        merged = _merge_text_boxes(items)
        assert len(merged) == 1, widths(merged)
        assert merged[0][1] == "155주2646"

    def test_reversed_input_order(self):
        """입력 순서가 달라도 결과가 같아야 한다."""
        a = (BBox(228, 274, 719, 659), "155주", 0.59)
        b = (BBox(497, 396, 1282, 829), "2646", 0.55)
        assert _merge_text_boxes([a, b])[0][1] == _merge_text_boxes([b, a])[0][1]


class TestDoesNotOverMerge:
    """합치지 말아야 할 것은 합치지 않는다 — 오탐 방지."""

    def test_different_lines_stay_apart(self):
        items = [
            (BBox(0, 0, 100, 50), "AAA", 0.9),
            (BBox(0, 200, 100, 250), "BBB", 0.9),        # 세로로 멀다
        ]
        assert len(_merge_text_boxes(items)) == 2

    def test_same_line_but_far_stays_apart(self):
        items = [
            (BBox(0, 0, 100, 50), "AAA", 0.9),
            (BBox(900, 0, 1000, 50), "BBB", 0.9),        # 가로로 멀다 (다른 차)
        ]
        assert len(_merge_text_boxes(items)) == 2

    def test_empty(self):
        assert _merge_text_boxes([]) == []


class TestTextOrder:
    def test_text_joined_left_to_right(self):
        """입력이 뒤섞여 와도 왼→오 순서로 이어야 한다."""
        items = [
            (BBox(300, 0, 400, 50), "3456", 0.9),
            (BBox(0, 0, 100, 50), "12", 0.9),
            (BBox(150, 0, 250, 50), "가", 0.9),
        ]
        merged = _merge_text_boxes(items)
        assert len(merged) == 1
        assert merged[0][1] == "12가3456"
