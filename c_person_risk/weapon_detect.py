import os
import sys
import torch
import cv2
import numpy as np
from ultralytics import YOLO


class WeaponDetector:
    def __init__(self, model_path=None, conf_threshold=0.58):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        if model_path is None:
            # 1순위: models/best.pt, 2순위: c_person_risk/best.pt, 3순위: yolov8n.pt
            candidates = [
                os.path.join(base_dir, 'models', 'best.pt'),
                os.path.join(base_dir, 'models', 'best_integrated_test.pt'),
                os.path.join(base_dir, 'best.pt'),
            ]
            model_path = next((c for c in candidates if os.path.exists(c)), 'yolov8n.pt')

        self.model_path = model_path
        self.device = 0 if torch.cuda.is_available() else 'cpu'
        self.model = YOLO(model_path)
        self.model.to(self.device)
        self.conf_threshold = conf_threshold

        # 커스텀 흉기 모델이 아닌 일반 COCO 모델일 경우 허용할 흉기류 라벨
        self.allowed_coco_weapons = {'knife', 'scissors', 'baseball bat'}

    def detect_weapons(self, frame):
        h, w = frame.shape[:2]
        results = self.model(frame, device=self.device, conf=self.conf_threshold, verbose=False)[0]
        weapons = []

        is_custom_model = 'yolov8n.pt' not in self.model_path.lower()

        for box in results.boxes:
            cls_id = int(box.cls[0])
            conf = float(box.conf[0])
            label = self.model.names[cls_id]

            # 커스텀 모델이면 모든 클래스 수용, COCO 모델이면 person 제외 흉기류만 수용
            if not is_custom_model and label not in self.allowed_coco_weapons:
                continue

            xyxy = box.xyxy[0].cpu().numpy()
            l = max(0, min(w, int(xyxy[0])))
            t = max(0, min(h, int(xyxy[1])))
            r = max(0, min(w, int(xyxy[2])))
            b = max(0, min(h, int(xyxy[3])))

            weapons.append({
                'label': label,
                'confidence': conf,
                'bbox': [l, t, r, b]
            })
        return weapons