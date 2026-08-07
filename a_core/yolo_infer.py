import sys
import os
import time
import json
import cv2
from ultralytics import YOLO

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "a_detector"))
from stationary_tracker import StationaryObjectTracker

from video_input import frame_generator
from schema import build_event_payload, build_weapon_event_payload

general_model = YOLO("yolo11n.pt")
kickboard_model = YOLO("../runs/detect/kickboard_v1/weights/best.pt")
weapon_model = YOLO("../runs/detect/weapon_v1/weights/best.pt")

ALL_MODELS = [general_model, kickboard_model, weapon_model]

WEAPON_CLASSES = {"knife"}  # 친구 모델 클래스명 그대로


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
        color = (0, 0, 255) if det["class"] in WEAPON_CLASSES else (0, 255, 0)
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        cv2.putText(frame, label, (x1, y1 - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
    return frame


if __name__ == "__main__":
    tracker = StationaryObjectTracker(threshold_sec=10)
    CAM_ID = "CCTV-014"

    for frame, idx in frame_generator("../data/videos/crime2.mp4", target_fps=10):
        detections = detect(frame)
        now = time.time()

        # 1. 낙하물(방치물) 이벤트 - 정지판별 거침
        debris_events = tracker.update(detections, now)
        for event in debris_events:
            payload = build_event_payload(CAM_ID, event, roi_id="roi_sidewalk_01")
            print("🚨 [DEBRIS] 이벤트 전송 예정:")
            print(json.dumps(payload, ensure_ascii=False, indent=2))

        # 2. 흉기 이벤트 - 탐지 즉시 발생
        for det in detections:
            if det["class"] in WEAPON_CLASSES:
                payload = build_weapon_event_payload(CAM_ID, det)
                print("🔪 [WEAPON] 이벤트 전송 예정:")
                print(json.dumps(payload, ensure_ascii=False, indent=2))

        frame = draw_detections(frame, detections)
        cv2.imshow("A Module Full Pipeline Test", frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cv2.destroyAllWindows()