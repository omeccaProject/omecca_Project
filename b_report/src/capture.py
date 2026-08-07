"""OpenCV 기반 이벤트 전/후 프레임 확보."""

from __future__ import annotations

from pathlib import Path

import cv2


def capture_frame_from_video(video_path: str | Path, timestamp_sec: float, out_path: str | Path) -> Path:
    """영상에서 특정 시각의 프레임을 추출해 저장한다."""
    video_path = Path(video_path)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_idx = max(int(timestamp_sec * fps), 0)
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
    ok, frame = cap.read()
    cap.release()
    if not ok or frame is None:
        raise RuntimeError(f"failed to read frame at {timestamp_sec}s from {video_path}")

    if not cv2.imwrite(str(out_path), frame):
        raise RuntimeError(f"failed to write image: {out_path}")
    return out_path


def ensure_image(path: str | Path) -> Path:
    """이미 존재하는 이미지 경로를 검증한다 (Mock/외부 파이프라인 연동용)."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    img = cv2.imread(str(path))
    if img is None:
        raise RuntimeError(f"invalid image file: {path}")
    return path


def capture_before_after_from_video(
    video_path: str | Path,
    event_sec: float,
    out_dir: str | Path,
    margin_sec: float = 1.0,
) -> tuple[Path, Path]:
    """이벤트 시각 기준 전/후 프레임을 캡쳐한다."""
    out_dir = Path(out_dir)
    before = capture_frame_from_video(video_path, max(event_sec - margin_sec, 0.0), out_dir / "before.jpg")
    after = capture_frame_from_video(video_path, event_sec + margin_sec, out_dir / "after.jpg")
    return before, after
