"""e_tracking(SmartCCTV) 추적 로그 어댑터 테스트.

여기 쓰는 JSON 구조는 `e_tracking/SmartCCTV/export_track_log.py` 의 실제
출력 형식이다 (payload = cam_id / video / fps / width / height / frame_count /
frames[{t, boxes[{track_id,x1,y1,x2,y2,alert}]}] / episodes).
"""

from __future__ import annotations

import json
import math

import pytest

from app.core.schemas import ObjectClass, ViolationType
from app.violation.track_log import TrackLogSource


def write_log(tmp_path, frames, cam_id="CAM-01", fps=15.0, video="",
              episodes=None, w=1280, h=720):
    p = tmp_path / "anomaly-track-log.json"
    p.write_text(json.dumps({
        "cam_id": cam_id, "video": video, "fps": fps,
        "width": w, "height": h, "frame_count": len(frames),
        "frames": frames, "episodes": episodes or [],
    }, ensure_ascii=False), encoding="utf-8")
    return p


def box(tid, x, y, w=84, h=105, alert=False):
    """차량 접지점이 (x, y) 가 되도록 박스를 만든다."""
    return {"track_id": tid, "x1": x - w // 2, "y1": y - h,
            "x2": x + w // 2, "y2": y, "alert": alert}


# ==========================================================================
class TestParsing:
    def test_reads_basic_log(self, tmp_path):
        p = write_log(tmp_path, [
            {"t": 0.0, "boxes": [box(5, 100, 300)]},
            {"t": 0.067, "boxes": [box(5, 110, 310), box(6, 900, 400)]},
        ])
        src = TrackLogSource(p, make_frames=False)
        out = list(src.frames())

        assert len(out) == 2
        assert src.cam_id == "CAM-01"
        assert src.fps == 15.0
        assert src.size == (1280, 720)
        assert src.tracker_name == "e_tracking(SmartCCTV)"

        frame_no, ts, frame, dets = out[1]
        assert frame_no == 1
        assert ts == pytest.approx(0.067)
        assert frame is None
        assert {d.track_id for d in dets} == {5, 6}

    def test_maps_to_our_schema(self, tmp_path):
        p = write_log(tmp_path, [{"t": 1.0, "boxes": [box(7, 500, 400)]}])
        _, _, _, dets = next(iter(TrackLogSource(p, make_frames=False).frames()))
        d = dets[0]

        assert d.track_id == 7
        assert d.cls is ObjectClass.CAR          # 로그에 차종이 없어 CAR 로 채운다
        assert d.is_vehicle()
        assert d.timestamp == 1.0
        assert d.bbox.bottom_center == (500.0, 400.0)

    def test_cam_id_override(self, tmp_path):
        p = write_log(tmp_path, [{"t": 0.0, "boxes": []}], cam_id="CAM-01")
        src = TrackLogSource(p, cam_id="ISU", make_frames=False)
        assert src.cam_id == "ISU"
        assert src.log_cam_id == "CAM-01"        # 원본도 보존 (경고 표시용)

    def test_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            TrackLogSource(tmp_path / "없는파일.json")

    def test_stride(self, tmp_path):
        frames = [{"t": i / 15, "boxes": [box(1, 100 + i, 300)]} for i in range(10)]
        src = TrackLogSource(write_log(tmp_path, frames), stride=3, make_frames=False)
        assert [f[0] for f in src.frames()] == [0, 3, 6, 9]


class TestRobustness:
    def test_skips_broken_boxes(self, tmp_path):
        p = write_log(tmp_path, [{"t": 0.0, "boxes": [
            box(1, 100, 300),
            {"track_id": 2},                              # 좌표 없음
            {"track_id": "x", "x1": 1, "y1": 1, "x2": 2, "y2": 2},   # ID 가 숫자 아님
            {"track_id": 3, "x1": 50, "y1": 50, "x2": 40, "y2": 40}, # 뒤집힌 박스
        ]}])
        _, _, _, dets = next(iter(TrackLogSource(p, make_frames=False).frames()))
        assert [d.track_id for d in dets] == [1]

    def test_empty_frames(self, tmp_path):
        p = write_log(tmp_path, [{"t": 0.0, "boxes": []}, {"t": 0.1}])
        out = list(TrackLogSource(p, make_frames=False).frames())
        assert len(out) == 2 and all(not d for *_, d in out)

    def test_counts_alerts(self, tmp_path):
        """김준호 쪽 이상운전 표시는 판정에 안 쓰고 통계로만 센다."""
        p = write_log(tmp_path, [{"t": 0.0, "boxes": [
            box(1, 100, 300, alert=True), box(2, 200, 300)]}])
        src = TrackLogSource(p, make_frames=False)
        list(src.frames())
        assert src.stats["boxes"] == 2 and src.stats["alerts"] == 1

    def test_missing_video_is_not_fatal(self, tmp_path):
        p = write_log(tmp_path, [{"t": 0.0, "boxes": []}], video="videos/없음.mp4")
        src = TrackLogSource(p, make_frames=False)
        assert src.video == ""                  # 못 찾아도 그냥 진행

    def test_blank_canvas_when_no_video(self, tmp_path):
        p = write_log(tmp_path, [{"t": 0.0, "boxes": []}], w=640, h=480)
        _, _, frame, _ = next(iter(TrackLogSource(p).frames()))
        assert frame is not None and frame.shape == (480, 640, 3)

    def test_episode_summary(self, tmp_path):
        p = write_log(tmp_path, [{"t": 0.0, "boxes": []}],
                      episodes=[{"t": 12.3, "track_id": 5, "reason": "위빙"}])
        src = TrackLogSource(p, make_frames=False)
        assert "1건" in src.episode_summary() and "#5" in src.episode_summary()


# ==========================================================================
class TestEndToEndWithEngine:
    """팀 추적 로그 → 우리 판정 엔진까지 실제로 흐르는지."""

    def _uturn_log(self, tmp_path, fps=15.0):
        """중앙선(x=640)을 넘어 유턴하는 차 1대 + 직진하는 차 1대."""
        frames = []
        n = int(9.0 * fps)
        for i in range(n):
            t = i / fps
            boxes = []

            # 유턴 차량 #101 — 내려왔다가 왼쪽으로 돌아 되올라간다
            if t < 3.5:
                x, y = 760.0, 120.0 + (520.0 - 120.0) * (t / 3.5)
            elif t < 5.5:
                th = math.pi * (t - 3.5) / 2.0
                x, y = 640.0 + 120.0 * math.cos(th), 520.0 + 45.0 * math.sin(th)
            else:
                x, y = 520.0, 520.0 - (520.0 - 120.0) * ((t - 5.5) / 3.5)
            boxes.append(box(101, int(x), int(y)))

            # 직진 차량 #103 — 반대 차로, 중앙선을 안 넘는다
            if 0.5 < t < 8.0:
                u = (t - 0.5) / 7.5
                boxes.append(box(103, 430, int(660 - 560 * u)))

            frames.append({"t": round(t, 3), "boxes": boxes})
        return write_log(tmp_path, frames, cam_id="CAM-FAKE", fps=fps)

    def test_uturn_detected_from_team_track_log(self, tmp_path, repo, matcher):
        from app.lpr.pipeline import LPRPipeline
        from app.lpr.recognizer import PlateRecognizer
        from app.violation.engine import ViolationEngine
        from app.violation.roi import ZoneRegistry
        from app.violation.signal_state import TimelineSignal
        from app.violation.synthetic import default_zone_dict

        p = self._uturn_log(tmp_path)
        src = TrackLogSource(p, cam_id="CAM-FAKE", make_frames=False)

        engine = ViolationEngine(
            zones=ZoneRegistry.from_dict(default_zone_dict("CAM-FAKE")),
            signal_provider=TimelineSignal(),
            lpr=LPRPipeline(recognizer=PlateRecognizer(mock=True), publish=False),
            matcher=matcher, repo=repo,
        )

        found = []
        for _, _, frame, dets in src.frames():
            for d in dets:
                for ev in engine.process(d, frame=frame):
                    if ev.violation_type is ViolationType.ILLEGAL_UTURN:
                        found.append(ev)

        assert len(found) == 1, [(e.track_id, e.subtype) for e in found]
        assert found[0].track_id == 101          # 유턴한 차만
        assert found[0].subtype == "no_sign"

    def test_same_interface_as_vehicle_source(self, tmp_path):
        """`VehicleSource` 를 그대로 대체할 수 있어야 한다 (run_uturn 이 둘 다 씀)."""
        src = TrackLogSource(write_log(tmp_path, [{"t": 0.0, "boxes": []}]),
                             make_frames=False)
        for attr in ("fps", "size", "total", "stride", "tracker_name", "frames"):
            assert hasattr(src, attr), attr
        first = next(iter(src.frames()))
        assert len(first) == 4                   # (frame_no, ts, frame, detections)
