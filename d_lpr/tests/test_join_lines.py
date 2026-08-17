"""OCR 조각을 읽는 순서대로 잇기 — 2줄 번호판 포함.

번호판이 항상 한 줄인 것은 아니다. 지역명이 붙은 판은 두 줄이다.

    경기 70        ← 윗줄
    바  1332       ← 아랫줄

x 좌표로만 정렬하면 두 줄이 뒤섞인다. 실측(사진 100장)에서 이렇게 나왔다.

    정답 경기70바1332  →  '천8바1332경가70'
    정답 경기76자3500  →  '8자3500경가76'

번호판 **검출기**를 붙이고 나서야 드러난 문제다. 그전에는 글자 검출이
번호판 일부만 잡아서 두 줄이 함께 들어오는 일 자체가 드물었다.
"""

from __future__ import annotations

from app.lpr import plate_format as pf
from app.lpr.recognizer import PlateRecognizer

join = PlateRecognizer._join


def poly(x1, y1, x2, y2):
    """EasyOCR 이 돌려주는 네 꼭짓점 형식."""
    return [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]


class TestTwoLinePlate:
    def test_region_plate_reads_top_line_first(self):
        frags = [
            (poly(140, 120, 300, 210), "바", 0.5),      # 아랫줄이 먼저 들어와도
            (poly(310, 120, 600, 210), "1332", 0.5),
            (poly(150, 10, 260, 90), "경기", 0.5),      # 윗줄
            (poly(280, 10, 400, 90), "70", 0.5),
        ]
        text, _ = join(frags)
        assert text == "경기70바1332"
        assert pf.canonical(text) == "70바1332"

    def test_two_line_without_region(self):
        """윗줄에 숫자만 있는 판도 있다."""
        frags = [
            (poly(100, 120, 400, 210), "자3500", 0.5),
            (poly(120, 10, 300, 90), "76", 0.5),
        ]
        assert join(frags)[0] == "76자3500"

    def test_region_smaller_and_higher_than_digits(self):
        """실제 배치 — 지역명은 숫자보다 **작고 위로 치우쳐** 있다.

        중심 y 거리로 줄을 나누면 '인천' 과 '70' 이 갈라져
        '70인천8바1670' 처럼 순서가 뒤집힌다 (실측). 세로 '겹침'으로
        판단해야 한 줄로 묶인다.
        """
        frags = [
            (poly(300, 120, 400, 210), "바", 0.5),        # 아랫줄
            (poly(410, 120, 700, 210), "1670", 0.5),
            (poly(300, 20, 380, 70), "인천", 0.5),        # 윗줄 — 작고 위쪽
            (poly(400, 10, 520, 90), "70", 0.5),          # 윗줄 — 크다
        ]
        text, _ = join(frags)
        assert text == "인천70바1670"
        assert pf.canonical(text) == "70바1670"

    def test_mixed_glyph_sizes_stay_one_line(self):
        """한 줄인데 글자 크기가 제각각이어도 갈리면 안 된다."""
        frags = [
            (poly(0, 20, 60, 70), "12", 0.9),
            (poly(90, 5, 200, 95), "가", 0.9),
            (poly(230, 15, 400, 85), "3456", 0.9),
        ]
        assert join(frags)[0] == "12가3456"


class TestSingleLineUnchanged:
    """한 줄 판은 예전과 결과가 같아야 한다 (회귀 방지)."""

    def test_fragments_sorted_left_to_right(self):
        frags = [
            (poly(300, 10, 400, 90), "3456", 0.9),
            (poly(0, 10, 100, 90), "12", 0.9),
            (poly(150, 10, 250, 90), "가", 0.9),
        ]
        assert join(frags)[0] == "12가3456"

    def test_slightly_skewed_stays_one_line(self):
        """조금 기울어 y 가 어긋나도 한 줄로 봐야 한다."""
        frags = [
            (poly(0, 10, 100, 90), "12", 0.9),
            (poly(150, 22, 250, 102), "가", 0.9),
            (poly(300, 16, 400, 96), "3456", 0.9),
        ]
        assert join(frags)[0] == "12가3456"

    def test_single_fragment(self):
        text, conf = join([(poly(0, 0, 100, 50), "12가3456", 0.88)])
        assert text == "12가3456"
        assert conf == 0.88

    def test_confidence_is_averaged(self):
        frags = [
            (poly(0, 0, 100, 50), "12", 0.90),
            (poly(150, 0, 250, 50), "가", 0.70),
            (poly(300, 0, 400, 50), "3456", 0.80),
        ]
        assert abs(join(frags)[1] - 0.80) < 1e-6


class TestEdgeCases:
    def test_empty(self):
        assert join([]) == ("", 0.0)

    def test_zero_height_fragment(self):
        """높이가 0인 조각이 와도 0 으로 나누지 않아야 한다."""
        assert join([(poly(0, 5, 100, 5), "12가3456", 0.5)])[0] == "12가3456"
