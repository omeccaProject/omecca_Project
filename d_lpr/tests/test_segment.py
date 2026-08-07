"""번호판 문자 분할 및 배치 해석 테스트."""

from __future__ import annotations

import pytest

cv2 = pytest.importorskip("cv2", reason="OpenCV 미설치 - 분할 검증 생략")

import numpy as np  # noqa: E402

from app.lpr import preprocess, segment  # noqa: E402

from .plate_synth import PlateCondition, apply_condition, render_plate  # noqa: E402

PLATES_7 = ["12가3456", "34나5678", "78라1234", "90마2345", "67바8901",
            "33아3333", "11바1111", "22사2222", "56다7890", "44자4444"]
PLATES_8 = ["123허4567"]

CONDITIONS = [
    PlateCondition("이상적", height=110),
    PlateCondition("기울기+12", height=110, angle=12),
    PlateCondition("기울기-9", height=110, angle=-9),
    PlateCondition("야간", height=110, brightness=0.35, contrast=0.55, noise=8),
    PlateCondition("저해상도32", height=32, jpeg_quality=70),
    PlateCondition("복합", height=70, angle=8, brightness=0.5,
                   contrast=0.6, noise=5, jpeg_quality=55),
]


def prepared(plate: str, cond: PlateCondition, seed: int = 400):
    """전처리를 거친 번호판 이미지 (실제 파이프라인과 같은 입력)."""
    img, mask = apply_condition(render_plate(plate, 110), cond, seed=seed, with_mask=True)
    ys, xs = np.nonzero(mask)
    bbox = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
    return preprocess.run(img, bbox_xyxy=bbox, target_h=96, deskew_limit=35.0).image


class TestSegment:
    @pytest.mark.parametrize("plate", PLATES_7)
    def test_seven_char_plates(self, plate):
        boxes = segment.segment(prepared(plate, CONDITIONS[0]))
        assert len(boxes) == 7, [b.to_tuple() for b in boxes]

    @pytest.mark.parametrize("plate", PLATES_8)
    def test_eight_char_plates(self, plate):
        assert len(segment.segment(prepared(plate, CONDITIONS[0]))) == 8

    def test_boxes_sorted_left_to_right(self):
        boxes = segment.segment(prepared("12가3456", CONDITIONS[0]))
        assert [b.x1 for b in boxes] == sorted(b.x1 for b in boxes)

    def test_hangul_syllable_is_one_box(self):
        """'가'는 ㄱ과 ㅏ가 떨어져 잡히지만 한 글자로 합쳐져야 한다."""
        boxes = segment.segment(prepared("12가3456", CONDITIONS[0]))
        hangul = boxes[2]
        digits = [b for i, b in enumerate(boxes) if i != 2]
        median_w = sorted(b.width for b in digits)[len(digits) // 2]
        assert hangul.width > median_w        # 한글은 숫자보다 넓다

    def test_overall_accuracy_across_conditions(self):
        ok = total = 0
        for cond in CONDITIONS:
            for i, plate in enumerate(PLATES_7 + PLATES_8):
                total += 1
                ok += len(segment.segment(prepared(plate, cond, seed=400 + i))) == len(plate)
        rate = ok / total
        assert rate >= 0.90, f"분할 정확도 {rate:.0%}"

    def test_empty_and_tiny_inputs(self):
        assert segment.segment(None) == []
        assert segment.segment(np.zeros((0, 0), np.uint8)) == []
        assert segment.segment(np.zeros((5, 10), np.uint8)) == []

    def test_single_character_crop(self):
        """한 글자만 잘라낸 이미지도 분할되어야 한다.

        폭 제한을 '이미지 폭 대비'로 걸면 이 경우 정상 글자가 걸러진다.
        (2패스 인식의 한글 패스가 바로 이 입력을 쓴다)
        """
        g = prepared("12가3456", CONDITIONS[0])
        boxes = segment.segment(g)
        crop = segment.crop(g, boxes[2], pad_x=6, pad_y=6)
        assert len(segment.segment(crop)) == 1


class TestLayout:
    def test_hangul_index_by_length(self):
        assert segment.hangul_index(7) == 2
        assert segment.hangul_index(8) == 3
        assert segment.hangul_index(6) is None

    def test_split_layout_positions(self):
        boxes = segment.segment(prepared("12가3456", CONDITIONS[0]))
        head, hangul, tail = segment.split_layout(boxes)
        assert len(head) == 2 and len(tail) == 4
        assert boxes.index(hangul) == 2

    def test_split_layout_eight_char(self):
        boxes = segment.segment(prepared("123허4567", CONDITIONS[0]))
        head, hangul, tail = segment.split_layout(boxes)
        assert len(head) == 3 and len(tail) == 4

    def test_rejects_wrong_char_count(self):
        assert segment.split_layout([]) is None

    def test_rejects_when_hangul_slot_is_narrow(self):
        """자모가 쪼개져 8개로 잡힌 7글자 판을 8글자로 오인하면 안 된다.

        모두 같은 폭이면 한글 자리를 특정할 수 없으므로 거부해야 한다.
        """
        boxes = [segment.CharBox(i * 40, 0, i * 40 + 30, 50) for i in range(8)]
        assert segment.split_layout(boxes) is None


class TestMaskAndCrop:
    def test_mask_replaces_region_with_background(self):
        g = prepared("12가3456", CONDITIONS[0])
        boxes = segment.segment(g)
        masked = segment.mask_region(g, boxes[2])
        # 덮은 자리는 밝은 배경이 되어 글자가 사라진다
        assert len(segment.segment(masked)) == 6
        assert masked.shape == g.shape

    def test_mask_does_not_modify_original(self):
        g = prepared("12가3456", CONDITIONS[0])
        before = g.copy()
        segment.mask_region(g, segment.segment(g)[2])
        assert np.array_equal(g, before)

    def test_crop_returns_region(self):
        g = prepared("12가3456", CONDITIONS[0])
        box = segment.segment(g)[2]
        crop = segment.crop(g, box, pad_x=4, pad_y=4)
        assert crop is not None
        assert crop.shape[0] >= box.height
        assert crop.shape[1] >= box.width

    def test_crop_clamped_to_bounds(self):
        g = prepared("12가3456", CONDITIONS[0])
        h, w = g.shape[:2]
        crop = segment.crop(g, segment.CharBox(0, 0, 20, 20), pad_x=50, pad_y=50)
        assert crop.shape[0] <= h and crop.shape[1] <= w

    def test_crop_rejects_degenerate_box(self):
        g = prepared("12가3456", CONDITIONS[0])
        assert segment.crop(g, segment.CharBox(5, 5, 5, 5), pad_x=0, pad_y=0) is None


class TestMergeSyllables:
    def test_merges_narrow_tall_vowel(self):
        # ㄱ(넓음) + ㅏ(좁고 김) → 한 글자
        merged = segment.merge_syllables([[0, 10, 40, 60], [42, 0, 58, 70]])
        assert len(merged) == 1

    def test_keeps_digits_apart(self):
        # 같은 크기 숫자 두 개는 합쳐지면 안 된다
        merged = segment.merge_syllables([[0, 0, 34, 51], [40, 0, 74, 51]])
        assert len(merged) == 2

    def test_merges_stacked_vowel(self):
        # ㅗ 처럼 자음 아래에 놓여 x 구간이 겹치는 경우
        merged = segment.merge_syllables([[0, 0, 40, 30], [5, 34, 45, 50]])
        assert len(merged) == 1

    def test_empty(self):
        assert segment.merge_syllables([]) == []
