import sys
import time
import json
from pathlib import Path
import cv2
from ultralytics import YOLO

HERE = Path(__file__).resolve().parent          # a_core/
ROOT = HERE.parent                              # omecca_Project/

sys.path.append(str(ROOT / "a_detector"))
from hazard_classes import DEBRIS_CLASSES, WEAPON_CLASSES
from stationary_tracker import StationaryObjectTracker

from video_input import frame_generator
from schema import build_event_payload, build_weapon_event_payload

# --- 모델 로딩 ---
general_model = YOLO("yolo11n.pt")                                    # COCO (사람/차량)
hazard_model = YOLO(str(ROOT / "a_detector/models/road_hazard_v3.pt"))  # 낙하물 3클래스

ALL_MODELS = [general_model, hazard_model]

# DEBRIS_CLASSES / WEAPON_CLASSES 는 hazard_classes.py 에서만 관리 (중복 정의 금지)


def detect(frame, conf_threshold=0.4):
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
                "confidence": round(conf, 2)
            })
    return detections


def draw_detections(frame, detections):
    for det in detections:
        x1, y1, x2, y2 = det["bbox"]
        label = f'{det["class"]} {det["confidence"]}'
        if det["class"] in WEAPON_CLASSES:
            color = (0, 0, 255)
        elif det["class"] in DEBRIS_CLASSES:
            color = (0, 255, 0)
        else:
            color = (160, 160, 160)      # COCO 일반 객체는 회색
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        cv2.putText(frame, label, (x1, y1 - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
    return frame


if __name__ == "__main__":
    tracker = StationaryObjectTracker(threshold_sec=10)
    CAM_ID = "CCTV-014"

    video_path = ROOT / "data/videos/test_kickboard.mp4"

    for frame, idx in frame_generator(str(video_path), target_fps=10):
        detections = detect(frame)
        now = time.time()

        # 1. 낙하물 - 낙하물 클래스만 정지판별에 투입
        debris_dets = [d for d in detections if d["class"] in DEBRIS_CLASSES]
        for event in tracker.update(debris_dets, now):
            payload = build_event_payload(CAM_ID, event, roi_id="roi_sidewalk_01")
            print("[DEBRIS] 이벤트 전송 예정:")
            print(json.dumps(payload, ensure_ascii=False, indent=2))

        # 2. 흉기 - 탐지 즉시 발생
        for det in detections:
            if det["class"] in WEAPON_CLASSES:
                payload = build_weapon_event_payload(CAM_ID, det)
                print("[WEAPON] 이벤트 전송 예정:")
                print(json.dumps(payload, ensure_ascii=False, indent=2))

        frame = draw_detections(frame, detections)
        cv2.imshow("A Module Full Pipeline Test", frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cv2.destroyAllWindows()