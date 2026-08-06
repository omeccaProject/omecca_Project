import os
from ultralytics import YOLO

class WeaponDetector:
    def __init__(self, model_path="models/best.pt"):
        # 전달받은 model_path 사용 (파일이 없으면 기본 yolov8n.pt 로드)
        target_path = model_path if os.path.exists(model_path) else "yolov8n.pt"
        self.model = YOLO(target_path)

    def detect_weapons(self, frame, conf_threshold=0.4):
        results = self.model(frame, conf=conf_threshold, verbose=False)[0]
        detections = []

        for box in results.boxes:
            cls_id = int(box.cls[0])
            label = self.model.names[cls_id]
            conf = float(box.conf[0])
            
            # 'person' 클래스는 무기 감지 대상에서 제외
            if label.lower() == 'person':
                continue

            xyxy = box.xyxy[0].cpu().numpy().tolist()

            detections.append({
                "label": label,
                "confidence": round(conf, 2),
                "bbox": [int(coord) for coord in xyxy]
            })

        return detections