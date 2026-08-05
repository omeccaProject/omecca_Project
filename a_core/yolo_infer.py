import cv2
from ultralytics import YOLO
from video_input import frame_generator

general_model = YOLO("yolo11n.pt")  # 사람/차량 등 COCO 80개 클래스
kickboard_model = YOLO("../runs/detect/kickboard_v1/weights/best.pt")  # 킥보드 전용


def detect(frame, conf_threshold=0.4):
    detections = []

    # 1. 일반 모델로 사람/차량 등 탐지
    results = general_model(frame, verbose=False)[0]
    for box in results.boxes:
        conf = float(box.conf[0])
        if conf < conf_threshold:
            continue
        cls_name = general_model.names[int(box.cls[0])]
        x1, y1, x2, y2 = box.xyxy[0].tolist()
        detections.append({
            "class": cls_name,
            "bbox": [round(x1), round(y1), round(x2), round(y2)],
            "confidence": round(conf, 2)
        })

    # 2. 킥보드 전용 모델로 추가 탐지
    kb_results = kickboard_model(frame, verbose=False)[0]
    for box in kb_results.boxes:
        conf = float(box.conf[0])
        if conf < conf_threshold:
            continue
        cls_name = kickboard_model.names[int(box.cls[0])]
        x1, y1, x2, y2 = box.xyxy[0].tolist()
        detections.append({
            "class": cls_name,
            "bbox": [round(x1), round(y1), round(x2), round(y2)],
            "confidence": round(conf, 2)
        })

    return detections