import os
import sys
import time
import json
import argparse
from pathlib import Path

import cv2
import requests
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

DEFAULT_VIDEO = PROJECT_ROOT / "data" / "videos" / "cone.mp4"
CAM_ID = "CCTV-014"

VEHICLE_CLASSES = {"car", "truck", "bus", "motorcycle"}

# b_gateway 전송 설정. b_gateway의 GATEWAY_API_KEY 환경변수와 같은 값이어야 함
# (기본값은 서로 일치하게 맞춰둠).
GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://localhost:8080") + "/api/events"
API_KEY = os.environ.get("GATEWAY_API_KEY", "omecca-dev-key-2026")


def send_to_gateway(payload):
    """이벤트를 b_gateway로 전송한다. 게이트웨이가 죽어있어도 탐지 루프는 계속 돌아야 하므로
    실패해도 예외를 밖으로 던지지 않고 로그만 남긴다."""
    try:
        resp = requests.post(GATEWAY_URL, json=payload, headers={"X-API-Key": API_KEY}, timeout=3)
        if resp.status_code == 201:
            print(f"  → 게이트웨이 전송 성공 ({resp.status_code})")
        else:
            print(f"  → 게이트웨이 전송 거부 ({resp.status_code}): {resp.text[:200]}")
    except requests.exceptions.RequestException as e:
        print(f"  → 게이트웨이 전송 실패(연결 안 됨): {e}")


def compute_iou(box_a, box_b):
    """두 bbox([x1,y1,x2,y2])의 IoU 계산."""
    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b

    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)

    inter_w = max(0, inter_x2 - inter_x1)
    inter_h = max(0, inter_y2 - inter_y1)
    inter_area = inter_w * inter_h

    if inter_area == 0:
        return 0.0

    area_a = (ax2 - ax1) * (ay2 - ay1)
    area_b = (bx2 - bx1) * (by2 - by1)
    return inter_area / float(area_a + area_b - inter_area)

def detect(frame, conf_threshold=0.4, vehicle_overlap_threshold=0.15):
    """프레임 1장에 대해 전체 모델 추론 후 탐지 리스트 반환.
    낙하물 후보가 차량 bbox와 vehicle_overlap_threshold 이상 겹치면
    (= 차량에 붙어있는 타이어 등으로 판단) 결과에서 제외한다.
    """
    vehicle_boxes = []
    hazard_candidates = []

    for model in ALL_MODELS:
        results = model(frame, verbose=False)[0]
        for box in results.boxes:
            conf = float(box.conf[0])
            if conf < conf_threshold:
                continue
            cls_name = model.names[int(box.cls[0])]
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            bbox = [round(x1), round(y1), round(x2), round(y2)]

            if model is general_model and cls_name in VEHICLE_CLASSES:
                vehicle_boxes.append(bbox)
            else:
                hazard_candidates.append({
                    "class": cls_name,
                    "bbox": bbox,
                    "confidence": round(conf, 3),
                })

    detections = []
    for det in hazard_candidates:
        if det["class"] in DEBRIS_CLASSES:
            overlaps_vehicle = any(
                compute_iou(det["bbox"], vbox) >= vehicle_overlap_threshold
                for vbox in vehicle_boxes
            )
            if overlaps_vehicle:
                continue  # 차량에 붙은 타이어로 판단 → 버림
        detections.append(det)

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

            print("🚨 [DEBRIS] 이벤트 전송:")
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            send_to_gateway(payload)

        # 2. 흉기 이벤트
        for det in detections:
            if det["class"] in WEAPON_CLASSES:
                payload = build_weapon_event_payload(CAM_ID, det)
                print("🔪 [WEAPON] 이벤트 전송:")
                print(json.dumps(payload, ensure_ascii=False, indent=2))
                send_to_gateway(payload)

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