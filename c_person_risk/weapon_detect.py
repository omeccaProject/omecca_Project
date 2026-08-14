import os
import sys
import torch
import cv2
import numpy as np
from ultralytics import YOLO

class WeaponDetector:
    def __init__(self, model_path=None, conf_threshold=0.58):
        if model_path is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            candidate = os.path.join(base_dir, 'best.pt')
            model_path = candidate if os.path.exists(candidate) else 'yolov8n.pt'
        
        self.device = 0 if torch.cuda.is_available() else 'cpu'
        self.model = YOLO(model_path)
        self.conf_threshold = conf_threshold

    def detect_weapons(self, frame):
        h, w = frame.shape[:2]
        results = self.model(frame, device=self.device, conf=self.conf_threshold, verbose=False)[0]
        weapons = []
        
        for box in results.boxes:
            cls_id = int(box.cls[0])
            conf = float(box.conf[0])
            label = self.model.names[cls_id]
            
            # 바운더리 클리핑
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
