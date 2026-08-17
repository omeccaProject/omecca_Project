"""김준호 담당 e_tracking(SmartCCTV) 결과 → 우리 `Detection` 스트림.

`e_tracking/SmartCCTV/export_track_log.py` 가 만든 JSON 을 읽어 위반 판정
엔진에 밀어 넣는다. 차량 검출·추적을 우리가 다시 하지 않고 **팀 모듈 결과를
그대로 쓴다.**

입력 JSON 형식 (export_track_log.py 실측)

    {
      "cam_id": "CAM-01",
      "video": "videos/0805.mp4",
      "fps": 30.0, "width": 1920, "height": 1080, "frame_count": 900,
      "frames": [
        {"t": 0.033, "boxes": [
            {"track_id": 5, "x1": 100, "y1": 200, "x2": 180, "y2": 320, "alert": false}
        ]}
      ],
      "episodes": [ {"t": 12.3, "track_id": 5, "plate": "...", "reason": "..."} ]
    }

우리 규격으로 옮길 때

    track_id  → 그대로 (ByteTrack ID)
    x1..y2    → BBox
    t         → timestamp (영상 시작 0초 기준)
    cls       → 로그에 차종이 없다. 차량만 다루므로 CAR 로 채운다
    alert     → 김준호 쪽 이상운전(위빙) 플래그. 유턴 판정에는 안 쓰고
                통계로만 남긴다 (같은 차량을 양쪽이 잡았는지 대조용)

이 어댑터가 붙으면 `vehicle_track.py`(임시 YOLO 대역)는 필요 없어진다.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Iterator, Optional

from ..core.schemas import BBox, Detection, ObjectClass

log = logging.getLogger("omeca.violation.track_log")


class TrackLogSource:
    """`VehicleSource` 와 같은 인터페이스. 그래서 `run_uturn.py` 가 그대로 쓴다.

    영상 파일이 함께 있으면 프레임을 읽어 화면에 그려 주고, 없으면 빈 캔버스를
    만든다. 판정 자체는 좌표만 있으면 되므로 영상이 없어도 돌아간다.
    """

    def __init__(
        self,
        log_path: str | Path,
        video: str = "",
        cam_id: str = "",
        stride: int = 1,
        make_frames: bool = True,
    ) -> None:
        self.path = Path(log_path)
        if not self.path.exists():
            raise FileNotFoundError(f"추적 로그가 없습니다: {self.path}")

        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.data = data
        self.log_cam_id = str(data.get("cam_id", "") or "")
        self.cam_id = cam_id or self.log_cam_id or "CAM-TRACK"
        self.fps = float(data.get("fps") or 30.0)
        self.size = (int(data.get("width") or 0), int(data.get("height") or 0))
        self._records: list[dict] = list(data.get("frames") or [])
        self.total = len(self._records)
        self.stride = max(1, stride)
        self.make_frames = make_frames
        self.tracker_name = "e_tracking(SmartCCTV)"
        self.episodes: list[dict] = list(data.get("episodes") or [])
        self.stats = {"boxes": 0, "alerts": 0, "frames": 0}

        # 영상 경로: 인자 > 로그에 적힌 경로(로그 파일 기준 상대경로도 시도)
        self.video = self._resolve_video(video)

    # ------------------------------------------------------------------
    def _resolve_video(self, video: str) -> str:
        if video:
            return video if Path(video).exists() else ""
        raw = str(self.data.get("video") or "")
        if not raw:
            return ""
        for cand in (Path(raw), self.path.parent / raw, self.path.parent.parent / raw):
            if cand.exists():
                return str(cand)
        log.info("로그에 적힌 영상(%s)을 못 찾음 → 빈 화면으로 진행", raw)
        return ""

    # ------------------------------------------------------------------
    def describe(self) -> str:
        v = Path(self.video).name if self.video else "(영상 없음 · 빈 화면)"
        return (f"추적 로그 {self.path.name} — cam={self.cam_id} "
                f"프레임 {self.total} · {self.fps:.0f}fps · "
                f"{self.size[0]}x{self.size[1]} · {v}")

    # ------------------------------------------------------------------
    def _to_detections(self, rec: dict, frame_no: int, ts: float) -> list[Detection]:
        out: list[Detection] = []
        for b in rec.get("boxes") or []:
            try:
                tid = int(b["track_id"])
                x1, y1 = float(b["x1"]), float(b["y1"])
                x2, y2 = float(b["x2"]), float(b["y2"])
            except (KeyError, TypeError, ValueError):
                continue                      # 깨진 박스는 조용히 건너뛴다
            if x2 <= x1 or y2 <= y1:
                continue
            if b.get("alert"):
                self.stats["alerts"] += 1
            out.append(Detection(
                cam_id=self.cam_id, track_id=tid, cls=ObjectClass.CAR,
                bbox=BBox(x1, y1, x2, y2), timestamp=ts,
                confidence=1.0, frame_no=frame_no,
            ))
        self.stats["boxes"] += len(out)
        return out

    # ------------------------------------------------------------------
    def frames(self) -> Iterator[tuple[int, float, Any, list[Detection]]]:
        cap = None
        blank = None
        if self.make_frames:
            import numpy as np

            if self.video:
                import cv2

                cap = cv2.VideoCapture(self.video)
                if not cap.isOpened():
                    log.warning("영상을 열 수 없음(%s) → 빈 화면", self.video)
                    cap = None
            if cap is None:
                h = self.size[1] or 720
                w = self.size[0] or 1280
                blank = np.full((h, w, 3), 40, dtype=np.uint8)

        try:
            for i, rec in enumerate(self._records):
                frame = None
                if cap is not None:
                    ok, img = cap.read()      # 로그와 영상은 프레임 1:1 대응
                    frame = img if ok else (blank.copy() if blank is not None else None)
                elif blank is not None:
                    frame = blank.copy()

                if i % self.stride:
                    continue

                ts = float(rec.get("t", i / self.fps))
                self.stats["frames"] += 1
                yield i, ts, frame, self._to_detections(rec, i, ts)
        finally:
            if cap is not None:
                cap.release()

    # ------------------------------------------------------------------
    def episode_summary(self) -> str:
        """김준호 쪽이 잡은 이상운전 에피소드. 우리 결과와 대조할 때 쓴다."""
        if not self.episodes:
            return "e_tracking 이상운전 에피소드: 없음"
        lines = [f"e_tracking 이상운전 에피소드 {len(self.episodes)}건"]
        for e in self.episodes[:10]:
            lines.append(f"  t={float(e.get('t', 0)):6.2f}s  track=#{e.get('track_id')}  "
                         f"{e.get('reason', '')}")
        return "\n".join(lines)
