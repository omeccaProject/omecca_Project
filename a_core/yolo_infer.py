import sys
import time
import json
import argparse
from pathlib import Path

import cv2
from ultralytics import YOLO

# ── 경로 기준점 (실행 위치와 무관하게 동작) ──────────────────────
BASE_DIR = Path(__file__).resolve().parent          # a_core/
PROJECT_ROOT = BASE_DIR.parent                       # omecca_Project/
DETECTOR_DIR = PROJECT_ROOT / "a_detector"

sys.path.append(str(DETECTOR_DIR))

from hazard_classes import DEBRIS_CLASSES, WEAPON_CLASSES   # noqa: E402
from stationary_tracker import StationaryObjectTracker       # noqa: E402
from video_input import frame_generator                      # noqa: E402
from schema import build_event_payload, build_weapon_event_payload  # noqa: E402

# ── 모델 로드 ────────────────────────────────────────────────
HAZARD_MODEL_PATH = DETECTOR_DIR / "models" / "road_hazard.pt"

if not HAZARD_MODEL_PATH.exists():
    raise FileNotFoundError(
        f"낙하물 모델을 찾을 수 없습니다: {HAZARD_MODEL_PATH}\n"
        "저장소를 clone한 직후라면 a_detector/models/road_hazard.pt 가 "
        "포함되어 있는지 확인하세요."
    )

general_model = YOLO("yolo11n.pt")            # COCO 사전학습 (사람·차량 등)
hazard_model = YOLO(str(HAZARD_MODEL_PATH))   # 낙하물 파인튜닝 모델

ALL_MODELS = [general_model, hazard_model]

OUTPUT_DIR = BASE_DIR / "outputs"          # a_core/outputs/
OUTPUT_DIR.mkdir(exist_ok=True)

DEFAULT_VIDEO = PROJECT_ROOT / "data" / "videos" / "kickboard.mp4"
CAM_ID = "CCTV-014"


def detect(frame, conf_threshold=0.4):
    """프레임 1장에 대해 전체 모델 추론 후 탐지 리스트 반환."""
    detections = []
    for model in ALL_MODELS:
        results = model(frame, verbose=False)[0]
        for box in results.boxes:
            conf = float(box.conf[0])
            if conf < conf_threshold:
                continue
            cls_name = model.names[int(box.cls[0])]
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            detections.append({
                "class": cls_name,
                "bbox": [round(x1), round(y1), round(x2), round(y2)],
                # ERD 규격: confidence DECIMAL(4,3), 0~1 범위
                "confidence": round(conf, 3),
            })
    return detections


def draw_detections(frame, detections):
    for det in detections:
        x1, y1, x2, y2 = det["bbox"]
        label = f'{det["class"]} {det["confidence"]}'
        if det["class"] in WEAPON_CLASSES:
            color = (0, 0, 255)      # 흉기 = 빨강
        elif det["class"] in DEBRIS_CLASSES:
            color = (0, 165, 255)    # 낙하물 = 주황
        else:
            color = (0, 255, 0)      # 일반 객체 = 초록
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        cv2.putText(frame, label, (x1, y1 - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
    return frame


def resize_for_display(frame, max_width=960):
    """화면 표시용으로만 축소. 탐지는 이미 끝난 뒤라 정확도에 영향 없음."""
    h, w = frame.shape[:2]
    if w <= max_width:
        return frame
    scale = max_width / w
    return cv2.resize(frame, (max_width, int(h * scale)))


def main():
    parser = argparse.ArgumentParser(description="모듈 A 낙하물·흉기 탐지 실행")
    parser.add_argument("--video", default=str(DEFAULT_VIDEO), help="입력 영상 경로")
    parser.add_argument("--fps", type=int, default=10, help="처리 FPS")
    parser.add_argument("--threshold", type=int, default=10,
                        help="방치물 판정 정지 지속시간(초)")
    parser.add_argument("--no-display", action="store_true",
                        help="화면 출력 없이 실행 (서버 연동용)")
    parser.add_argument("--save", action="store_true",
                    help="탐지 결과 영상을 a_core/outputs/ 에 저장")
    args = parser.parse_args()

    tracker = StationaryObjectTracker(threshold_sec=args.threshold)

    writer = None
    if args.save:
        save_path = OUTPUT_DIR / f"{Path(args.video).stem}_detected.mp4"

    for frame, idx in frame_generator(args.video, target_fps=args.fps):
        detections = detect(frame)
        now = time.time()

        # 1. 낙하물(방치물) 이벤트
        debris_candidates = [d for d in detections if d["class"] in DEBRIS_CLASSES]
        for event in tracker.update(debris_candidates, now):
            payload = build_event_payload(CAM_ID, event, roi_id="roi_sidewalk_01")
            print("[DEBRIS] 이벤트 전송 예정:")
            print(json.dumps(payload, ensure_ascii=False, indent=2))

        # 2. 흉기 이벤트
        for det in detections:
            if det["class"] in WEAPON_CLASSES:
                payload = build_weapon_event_payload(CAM_ID, det)
                print("[WEAPON] 이벤트 전송 예정:")
                print(json.dumps(payload, ensure_ascii=False, indent=2))

        # 박스 그리기는 저장/화면표시 둘 다에 필요하므로 여기서 한 번만 수행
        frame = draw_detections(frame, detections)

        if args.save:
            if writer is None:
                h, w = frame.shape[:2]
                fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                writer = cv2.VideoWriter(str(save_path), fourcc, args.fps, (w, h))
            writer.write(frame)

        if not args.no_display:
            cv2.imshow("OMECCA - Module A", resize_for_display(frame))
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    if writer is not None:
        writer.release()
        print(f"[SAVE] 저장 완료: {save_path}")

    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()