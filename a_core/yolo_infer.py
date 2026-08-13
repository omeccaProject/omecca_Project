import sys
import os
import time
import json
import cv2
import requests
from ultralytics import YOLO

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "a_detector"))
from hazard_classes import DEBRIS_CLASSES, WEAPON_CLASSES
from stationary_tracker import StationaryObjectTracker

from video_input import frame_generator
from schema import build_event_payload, build_weapon_event_payload

general_model = YOLO("yolo11n.pt")
hazard_model = YOLO("../runs/detect/road_hazard_v1/weights/best.pt")

ALL_MODELS = [general_model, hazard_model]

DEBRIS_CLASSES = {"electric_scooter", "car_tire", "box", "traffic_cone", "fallen_tree"}
WEAPON_CLASSES = {"knife", "blunt_weapon"}

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
            print("🚨 [DEBRIS] 이벤트 전송:")
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            send_to_gateway(payload)

        # 2. 흉기 이벤트 - 탐지 즉시 발생
        for det in detections:
            if det["class"] in WEAPON_CLASSES:
                payload = build_weapon_event_payload(CAM_ID, det)
                print("🔪 [WEAPON] 이벤트 전송:")
                print(json.dumps(payload, ensure_ascii=False, indent=2))
                send_to_gateway(payload)

        frame = draw_detections(frame, detections)
        cv2.imshow("A Module Full Pipeline Test", frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cv2.destroyAllWindows()