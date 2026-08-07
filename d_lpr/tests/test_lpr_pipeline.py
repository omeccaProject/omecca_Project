"""LPR 파이프라인(다중 프레임 다수결) 테스트."""

import time

from app.core.schemas import BBox, Detection, ObjectClass
from app.lpr.pipeline import LPRPipeline
from app.lpr.recognizer import PlateRecognizer


def det(track_id: int = 1, i: int = 0, cls: ObjectClass = ObjectClass.CAR) -> Detection:
    return Detection(
        cam_id="CAM-001", track_id=track_id, cls=cls,
        bbox=BBox(600, 400, 700, 520),
        timestamp=time.time() + i * 0.1, frame_no=i,
    )


def make_pipeline() -> LPRPipeline:
    return LPRPipeline(recognizer=PlateRecognizer(mock=True), publish=False)


class TestPipeline:
    def test_ignores_non_vehicle(self):
        p = make_pipeline()
        assert p.process(det(cls=ObjectClass.PERSON)) is None

    def test_single_frame_does_not_confirm(self):
        p = make_pipeline()
        assert p.process(det(i=0), hint="12가3456") is None

    def test_confirms_after_multiple_frames(self):
        p = make_pipeline()
        result = None
        for i in range(8):
            r = p.process(det(i=i), hint="12가3456")
            result = result or r
        assert result is not None
        assert result.plate_no == "12가3456"
        assert result.valid_format

    def test_confidence_within_range(self):
        p = make_pipeline()
        r = None
        for i in range(8):
            r = p.process(det(i=i), hint="34나5678") or r
        assert r is not None
        assert 0.0 < r.confidence <= 1.0

    def test_no_duplicate_confirmation(self):
        p = make_pipeline()
        confirms = [p.process(det(i=i), hint="12가3456") for i in range(20)]
        assert len([c for c in confirms if c is not None]) == 1

    def test_voting_survives_ocr_noise(self):
        """일부 프레임이 오인식돼도 다수결로 올바른 값이 확정된다."""
        p = make_pipeline()
        confirmed = None
        for i in range(30):
            r = p.process(det(i=i), hint="56다7890")
            confirmed = confirmed or r
        assert confirmed is not None and confirmed.plate_no == "56다7890"

    def test_tracks_are_independent(self):
        p = make_pipeline()
        for i in range(8):
            p.process(det(track_id=1, i=i), hint="12가3456")
            p.process(det(track_id=2, i=i), hint="34나5678")
        assert p.confirmed_plate("CAM-001", 1) == "12가3456"
        assert p.confirmed_plate("CAM-001", 2) == "34나5678"

    def test_prune_removes_stale_tracks(self):
        p = make_pipeline()
        for i in range(8):
            p.process(det(i=i), hint="12가3456")
        assert p.prune(ttl_sec=0.0, now=time.time() + 10_000) == 1
        assert p.confirmed_plate("CAM-001", 1) is None

    def test_stats_accumulate(self):
        p = make_pipeline()
        for i in range(8):
            p.process(det(i=i), hint="12가3456")
        assert p.stats["frames"] == 8
        assert p.stats["confirmed"] == 1


class TestDetectorMock:
    def test_mock_plate_bbox_inside_vehicle(self):
        from app.lpr.detector import PlateDetector

        d = PlateDetector(mock=True)
        veh = BBox(600, 400, 700, 520)
        boxes = d.detect(None, veh)
        assert len(boxes) == 1
        b = boxes[0]
        assert veh.x1 <= b.x1 and b.x2 <= veh.x2
        assert veh.y1 <= b.y1 and b.y2 <= veh.y2
        assert 1.5 <= b.width / b.height <= 6.0     # 번호판 비율 범위

    def test_no_vehicle_no_box(self):
        from app.lpr.detector import PlateDetector

        assert PlateDetector(mock=True).detect(None, None) == []
