"""검증용 간이 추적기 — YOLO 없이 영상에서 추적 로그를 뽑는다.

**이건 정식 검출기가 아니다.** 배경 차감(움직이는 것만 골라내기)으로 차량을
잡으므로, 고정 카메라 + 차량이 몇 대 없는 짧은 영상에서만 쓸 만하다.

왜 만들었나
    정식 경로는 김준호 `e_tracking/export_track_log.py`(YOLO11m)다. 그런데
    그걸 돌리려면 ultralytics·torch·가중치가 필요하다. 설치 전에 **ROI를
    제대로 그었는지, 판정이 도는지** 먼저 확인하고 싶을 때가 있다.
    이 도구는 그 확인용이다.

    출력 형식이 `export_track_log.py` 와 같으므로 `run_uturn.py --track-log`
    에 그대로 넣을 수 있고, 나중에 YOLO 로그로 바꿔 끼우면 된다.

두 가지 방식
    기본(MOG2)      : 배경을 계속 갱신한다. 차가 계속 움직이는 영상에 맞다.
    --median-bg     : 영상 전체의 중앙값으로 **빈 도로 한 장**을 만들고 그것과
                      비교한다. 카메라가 고정이고 차가 느리거나 멈추는 영상에
                      훨씬 강하다. MOG2 는 느린 차를 배경으로 흡수해 놓친다.

한계 (발표에 쓸 수치는 여기서 뽑지 말 것)
    · 그림자·반사를 차로 오인할 수 있다
    · 차가 겹치면 하나로 합쳐진다
    · 중앙값 방식은 카메라가 조금이라도 움직이면 전부 오검출된다

사용법
    python quick_track.py --video 불법유턴3.mp4 --output output/uturn3.json --cam-id UTURN3
    python quick_track.py --video ... --preview output/uturn3_track.mp4   # 눈으로 확인
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from app.core.schemas import BBox                      # noqa: E402
from app.violation.vehicle_track import IoUTracker     # noqa: E402


def parse_masks(spec: str) -> list[tuple[int, int, int, int]]:
    """'x1,y1,x2,y2;...' → 사각형 목록. HUD·오버레이를 판정에서 뺄 때 쓴다."""
    out = []
    for part in spec.split(";"):
        part = part.strip()
        if not part:
            continue
        try:
            x1, y1, x2, y2 = (int(v) for v in part.split(","))
            out.append((x1, y1, x2, y2))
        except ValueError:
            sys.exit(f"--mask 형식 오류: '{part}' (x1,y1,x2,y2 여야 합니다)")
    return out


def track(video: str, cam_id: str, min_area_ratio: float = 0.004,
          warmup: int = 10, preview: str = "",
          masks: list[tuple[int, int, int, int]] | None = None,
          median_bg: bool = False, diff_thresh: int = 28) -> dict:
    import cv2
    import numpy as np

    cap = cv2.VideoCapture(video)
    if not cap.isOpened():
        sys.exit(f"영상을 열 수 없습니다: {video}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    min_area = min_area_ratio * W * H

    bg = None
    median = None
    if median_bg:
        # 영상 전체를 훑어 '빈 도로' 한 장을 만든다 (픽셀별 중앙값).
        # 차는 잠깐 지나가므로 중앙값에는 안 남는다.
        sample = []
        while True:
            ok, im = cap.read()
            if not ok:
                break
            sample.append(im)
        if not sample:
            sys.exit("프레임을 읽지 못했습니다.")
        step = max(1, len(sample) // 60)
        median = np.median(np.stack(sample[::step]), axis=0).astype(np.uint8)
        cap.release()
        cap = cv2.VideoCapture(video)
        print(f"빈 도로 배경 생성 ({len(sample[::step])}장 중앙값)")
    else:
        bg = cv2.createBackgroundSubtractorMOG2(history=250, varThreshold=45,
                                                detectShadows=True)
    tracker = IoUTracker(iou_threshold=0.25, max_missing=15)
    writer = None
    if preview:
        Path(preview).parent.mkdir(parents=True, exist_ok=True)
        writer = cv2.VideoWriter(preview, cv2.VideoWriter_fourcc(*"mp4v"), fps, (W, H))

    frames = []
    frame_idx = 0
    while True:
        ok, img = cap.read()
        if not ok:
            break

        if median is not None:
            diff = cv2.absdiff(img, median)
            gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
            _, mask = cv2.threshold(gray, diff_thresh, 255, cv2.THRESH_BINARY)
        else:
            mask = bg.apply(img)
            mask[mask < 200] = 0                   # 그림자(127)는 버린다
        for mx1, my1, mx2, my2 in (masks or []):   # HUD 등 무시할 영역
            mask[my1:my2, mx1:mx2] = 0
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((25, 25), np.uint8))

        boxes = []
        if median is not None or frame_idx >= warmup:   # 중앙값 방식은 대기 불필요
            cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for ct in cnts:
                if cv2.contourArea(ct) < min_area:
                    continue
                x, y, w, h = cv2.boundingRect(ct)
                ar = w / max(1, h)
                if not (0.4 <= ar <= 4.5):         # 차량으로 보기 힘든 형태 제외
                    continue
                boxes.append(BBox(x, y, x + w, y + h))

        ids = tracker.update(boxes, frame_idx)
        out_boxes = []
        for bb, tid in zip(boxes, ids):
            x1, y1, x2, y2 = bb.to_xyxy()
            out_boxes.append({"track_id": tid, "x1": x1, "y1": y1,
                              "x2": x2, "y2": y2, "alert": False})
            if writer is not None:
                cv2.rectangle(img, (x1, y1), (x2, y2), (0, 220, 0), 2)
                cv2.putText(img, f"#{tid}", (x1, max(16, y1 - 6)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 220, 0), 2)

        frames.append({"t": round(frame_idx / fps, 3), "boxes": out_boxes})
        if writer is not None:
            writer.write(img)
        frame_idx += 1

    cap.release()
    if writer is not None:
        writer.release()

    return {"cam_id": cam_id, "video": video, "fps": fps,
            "width": W, "height": H, "frame_count": frame_idx,
            "frames": frames, "episodes": []}


def main() -> None:
    ap = argparse.ArgumentParser(description="검증용 간이 추적기 (YOLO 불필요)")
    ap.add_argument("--video", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--cam-id", default="CAM-TEST")
    ap.add_argument("--min-area", type=float, default=0.004,
                    help="화면 대비 최소 차량 넓이 비율")
    ap.add_argument("--preview", default="", help="박스를 그린 확인용 영상 저장")
    ap.add_argument("--mask", default="",
                    help="무시할 영역 'x1,y1,x2,y2;...' (게임 HUD·자막 등)")
    ap.add_argument("--median-bg", action="store_true",
                    help="빈 도로 한 장을 만들어 비교 (느린 차·정차 차량에 강함)")
    ap.add_argument("--diff", type=int, default=28,
                    help="--median-bg 의 밝기 차이 임계값")
    a = ap.parse_args()

    try:
        import cv2  # noqa: F401
    except ImportError:
        sys.exit("OpenCV 가 필요합니다:  pip install opencv-python")

    print("※ 배경차감 기반 간이 추적기입니다. 정식 검증은 김준호 e_tracking 을 쓰세요.\n")
    masks = parse_masks(a.mask)
    if masks:
        print(f"무시 영역 {len(masks)}개: {masks}")
    data = track(a.video, a.cam_id, a.min_area, preview=a.preview, masks=masks,
                 median_bg=a.median_bg, diff_thresh=a.diff)

    ids = {b["track_id"] for f in data["frames"] for b in f["boxes"]}
    nbox = sum(len(f["boxes"]) for f in data["frames"])
    Path(a.output).parent.mkdir(parents=True, exist_ok=True)
    Path(a.output).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    print(f"프레임 {data['frame_count']}  박스 {nbox}개  track ID {len(ids)}개")
    print(f"저장 → {a.output}")
    if a.preview:
        print(f"확인용 영상 → {a.preview}")
    if len(ids) > 12:
        print("\n주의: track ID 가 너무 많습니다. 추적이 자주 끊겼다는 뜻이라")
        print("      --min-area 를 올려 잡음을 줄여 보세요.")


if __name__ == "__main__":
    main()
