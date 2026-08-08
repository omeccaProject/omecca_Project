"""전처리·검출 성능 정량 검증.

OpenCV 가 있어야 의미가 있는 테스트라, 없으면 전체를 건너뛴다.
(운영 서버에는 OpenCV 를 두지만 CI 경량 환경에서는 없을 수 있다)

측정 지표
  1. 기울기 추정 오차 — deskew 가 실제로 각도를 되돌리는지
  2. 번호판 검출 IoU — CV 폴백이 판 전체를 잡는지
  3. 전처리 유무에 따른 문자 판독 정확도 차이 — 전처리의 실제 기여도
"""

from __future__ import annotations

import pytest

cv2 = pytest.importorskip("cv2", reason="OpenCV 미설치 - 영상 처리 검증 생략")

from app.core.schemas import BBox                       # noqa: E402
from app.lpr import preprocess                          # noqa: E402
from app.lpr.detector import PlateDetector              # noqa: E402

from .plate_synth import (                              # noqa: E402
    CONDITIONS, PlateCondition, render_plate, render_vehicle_scene,
)
from .simple_ocr import char_accuracy, read_plate       # noqa: E402

PLATES = ["12가3456", "34나5678", "123허4567", "78라1234", "90마2345", "67바8901"]


def _gray(img):
    return img if len(img.shape) == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


# ==========================================================================
# 1. 기울기 추정
# ==========================================================================
class TestDeskew:
    @pytest.mark.parametrize("angle", [-18, -12, -6, -3, 0, 3, 6, 12, 18])
    def test_angle_estimated_within_tolerance(self, angle):
        from .plate_synth import apply_condition

        img = apply_condition(render_plate("12가3456"),
                              PlateCondition("t", height=110, angle=angle), seed=7)
        est = preprocess.estimate_skew(_gray(img), limit=20.0)
        # estimate_skew 는 '되돌려야 할 각도'를 부호 반대로 준다
        assert abs(-est - angle) < 1.5, f"부여 {angle}도, 추정 {-est:.2f}도"

    def test_rotation_actually_straightens(self):
        from .plate_synth import apply_condition

        img = apply_condition(render_plate("12가3456"),
                              PlateCondition("t", height=110, angle=11), seed=3)
        gray = _gray(img)
        fixed = preprocess.rotate(gray, preprocess.estimate_skew(gray, 20.0))
        assert abs(preprocess.estimate_skew(fixed, 20.0)) < 1.5

    def test_background_heavy_crop_does_not_break(self):
        """크롭에 어두운 배경이 많이 섞여도 각도 추정이 무너지지 않아야 한다.

        (외접 사각형 방식은 이 조건에서 이미지 전체로 붕괴해 항상 0을 냈다)
        """
        import numpy as np

        plate = render_plate("12가3456", 60)
        canvas = np.full((200, 500, 3), 40, np.uint8)
        canvas[70:70 + plate.shape[0], 120:120 + plate.shape[1]] = plate
        est = preprocess.estimate_skew(_gray(canvas), 20.0)
        assert abs(est) < 2.0        # 기울지 않았으므로 0에 가까워야 한다

    def test_beyond_limit_is_ignored(self):
        from .plate_synth import apply_condition

        img = apply_condition(render_plate("12가3456"),
                              PlateCondition("t", height=110, angle=35), seed=5)
        # 한계를 넘는 각도는 오추정 위험이 커 보정하지 않는다
        assert preprocess.estimate_skew(_gray(img), limit=20.0) == 0.0

    def test_empty_input_is_safe(self):
        import numpy as np

        assert preprocess.estimate_skew(np.zeros((0, 0), np.uint8)) == 0.0
        assert preprocess.estimate_skew(np.zeros((3, 3), np.uint8)) == 0.0
        assert preprocess.estimate_skew(None) == 0.0


# ==========================================================================
# 2. 전처리 파이프라인
# ==========================================================================
class TestPipelineStages:
    @pytest.mark.parametrize("cond", CONDITIONS, ids=[c.name for c in CONDITIONS])
    def test_runs_on_every_condition(self, cond):
        from .plate_synth import apply_condition

        img = apply_condition(render_plate("12가3456"), cond, seed=11)
        r = preprocess.run(img, target_h=96, deskew_limit=20.0)
        assert r.image is not None
        assert r.binary is not None
        assert "clahe" in r.applied and "binarize" in r.applied

    def test_upscales_small_plates(self):
        from .plate_synth import apply_condition

        img = apply_condition(render_plate("12가3456"),
                              PlateCondition("small", height=32), seed=1)
        r = preprocess.run(img, target_h=96)
        assert r.image.shape[0] == 96

    def test_crop_uses_bbox(self):
        scene, gt = render_vehicle_scene("12가3456", plate_height=44, seed=2)
        r = preprocess.run(scene, bbox_xyxy=gt, target_h=96)
        # 크롭 후 확대되므로 원본 장면보다 작아야 한다
        assert r.image.shape[1] < scene.shape[1]

    def test_invalid_bbox_returns_empty(self):
        scene, _ = render_vehicle_scene("12가3456", seed=2)
        r = preprocess.run(scene, bbox_xyxy=(10, 10, 5, 5))
        assert r.image is None


class TestTrimToPlate:
    """기울기 보정 후 남는 여백 정리."""

    def test_trims_padding_around_rotated_plate(self):
        """여백이 큰 이미지일수록 정리가 필요하다.

        판정 기준을 '이미지 대비 비율'로 두면 정작 이런 경우에 거부된다.
        """
        from .plate_synth import apply_condition

        img = apply_condition(render_plate("34나5678"),
                              PlateCondition("t", height=110, angle=10), seed=3)
        gray = _gray(img)
        rotated = preprocess.rotate(gray, preprocess.estimate_skew(gray, 35.0))
        trimmed = preprocess.trim_to_plate(rotated)
        assert trimmed.shape[0] < rotated.shape[0] * 0.6
        assert 2.5 <= trimmed.shape[1] / trimmed.shape[0] <= 8.0

    def test_readable_after_full_pipeline(self):
        """여백 정리가 빠지면 이진화가 배경에 지배당해 판독이 실패한다."""
        from .plate_synth import apply_condition

        img = apply_condition(render_plate("34나5678"),
                              PlateCondition("t", height=110, angle=10), seed=3)
        out = preprocess.run(img, target_h=96, deskew_limit=35.0).image
        text, _ = read_plate(out)
        assert char_accuracy("34나5678", text) >= 0.85

    def test_keeps_image_when_no_plate_like_region(self):
        """균일한 밝은 면을 번호판으로 오인해 잘라내면 안 된다."""
        import numpy as np

        flat = np.full((80, 300), 200, np.uint8)
        assert preprocess.trim_to_plate(flat).shape == flat.shape

    def test_tiny_input_is_safe(self):
        import numpy as np

        tiny = np.zeros((6, 10), np.uint8)
        assert preprocess.trim_to_plate(tiny).shape == tiny.shape
        assert preprocess.trim_to_plate(None) is None


# ==========================================================================
# 3. 번호판 검출 (CV 폴백)
# ==========================================================================
DETECT_CONDITIONS = [
    PlateCondition("이상적", height=44),
    PlateCondition("기울기+8", height=44, angle=8),
    PlateCondition("기울기-12", height=44, angle=-12),
    PlateCondition("야간", height=44, brightness=0.4, contrast=0.6, noise=6),
    PlateCondition("저해상도", height=28, jpeg_quality=60),
    PlateCondition("블러", height=44, blur=3),
    PlateCondition("복합", height=32, angle=6, brightness=0.5,
                   contrast=0.6, noise=5, jpeg_quality=55),
]


def _detect_iou(det, plate_no, cond, seed):
    scene, gt = render_vehicle_scene(plate_no, plate_height=cond.height, cond=cond, seed=seed)
    h, w = scene.shape[:2]
    veh = BBox(w * 0.12, h * 0.18, w * 0.88, h * 0.92)
    boxes = det.detect(scene, veh)
    g = BBox(*gt)
    return max((b.iou(g) for b in boxes), default=0.0)


class TestDetection:
    @pytest.fixture(scope="class")
    @classmethod
    def det(cls):
        return PlateDetector(mock=False)

    @pytest.mark.parametrize("cond", DETECT_CONDITIONS, ids=[c.name for c in DETECT_CONDITIONS])
    def test_detects_plate_in_condition(self, det, cond):
        ious = [_detect_iou(det, p, cond, 100 + i) for i, p in enumerate(PLATES)]
        ok = sum(1 for v in ious if v >= 0.5)
        assert ok >= len(PLATES) - 1, f"{cond.name}: {ok}/{len(PLATES)} (IoU {ious})"

    def test_overall_detection_rate(self, det):
        ious = [
            _detect_iou(det, p, c, 100 + i)
            for c in DETECT_CONDITIONS for i, p in enumerate(PLATES)
        ]
        rate = sum(1 for v in ious if v >= 0.5) / len(ious)
        assert rate >= 0.90, f"검출률 {rate:.0%}"

    def test_box_covers_whole_plate_not_just_text(self, det):
        """문자 영역만 잡으면 크롭 시 앞뒤 글자가 잘린다."""
        cond = PlateCondition("이상적", height=44)
        scene, gt = render_vehicle_scene("12가3456", plate_height=44, cond=cond, seed=100)
        h, w = scene.shape[:2]
        boxes = det.detect(scene, BBox(w * 0.12, h * 0.18, w * 0.88, h * 0.92))
        g = BBox(*gt)
        best = max(boxes, key=lambda b: b.iou(g))
        assert best.width >= g.width * 0.85

    def test_no_false_positive_without_plate(self, det):
        """번호판이 없는 장면에서 후보가 나와도 비율 조건은 지켜야 한다."""
        import numpy as np

        scene = np.full((300, 400, 3), 90, np.uint8)
        cv2.rectangle(scene, (50, 50), (350, 250), (130, 130, 130), -1)
        for b in det.detect(scene, BBox(0, 0, 400, 300)):
            assert 1.8 <= b.width / b.height <= 7.5


# ==========================================================================
# 4. 전처리 기여도 (템플릿 매칭 OCR 기준)
# ==========================================================================
QUALITY_CONDITIONS = [
    PlateCondition("기울기+12", height=110, angle=12),
    PlateCondition("기울기-9", height=110, angle=-9),
    PlateCondition("야간", height=110, brightness=0.35, contrast=0.55, noise=8),
    PlateCondition("역광", height=110, brightness=1.45, contrast=0.35),
    PlateCondition("복합", height=70, angle=8, brightness=0.5, contrast=0.6, noise=5),
]


def _accuracy(plates, cond, with_preprocess: bool) -> float:
    """전처리 유무만 다르게 두고 문자 판독 정확도를 비교한다.

    두 조건 모두 검출기가 찾아준 번호판 영역으로 먼저 잘라낸 뒤 비교해야
    (전처리가 하는 크롭 때문이 아니라) 보정 자체의 효과를 볼 수 있다.
    """
    import numpy as np

    from .plate_synth import apply_condition

    accs = []
    for i, p in enumerate(plates):
        img, mask = apply_condition(render_plate(p, 110), cond, seed=200 + i, with_mask=True)
        ys, xs = np.nonzero(mask)
        bbox = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)

        if with_preprocess:
            out = preprocess.run(img, bbox_xyxy=bbox, target_h=96, deskew_limit=20.0).image
        else:
            out = _gray(preprocess.crop(img, bbox))

        text, _ = read_plate(out)
        accs.append(char_accuracy(p, text))
    return sum(accs) / len(accs)


class TestPreprocessContribution:
    def test_baseline_is_high_on_clean_plate(self):
        """측정 도구 자체가 신뢰할 만한지 먼저 확인한다."""
        acc = _accuracy(PLATES, PlateCondition("이상적", height=110), with_preprocess=False)
        assert acc >= 0.9, f"기준 조건 정확도 {acc:.2f} - 측정 도구 점검 필요"

    @pytest.mark.parametrize("cond", QUALITY_CONDITIONS, ids=[c.name for c in QUALITY_CONDITIONS])
    def test_preprocess_does_not_hurt(self, cond):
        before = _accuracy(PLATES, cond, with_preprocess=False)
        after = _accuracy(PLATES, cond, with_preprocess=True)
        assert after >= before - 0.05, f"{cond.name}: {before:.2f} → {after:.2f} (악화)"

    def test_preprocess_helps_on_tilted_plates(self):
        """기울기 보정의 효과가 가장 뚜렷하게 드러나는 조건."""
        cond = PlateCondition("기울기+12", height=110, angle=12)
        before = _accuracy(PLATES, cond, with_preprocess=False)
        after = _accuracy(PLATES, cond, with_preprocess=True)
        assert after > before, f"{before:.2f} → {after:.2f}"
