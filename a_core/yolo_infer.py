import sys
import os
import time
import cv2
from ultralytics import YOLO

# a_detector 폴더의 stationary_tracker.py를 import하기 위한 경로 추가
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "a_detector"))
from stationary_tracker import StationaryObjectTracker

from video_input import frame_generator

# 모델 두 개 로드
general_model = YOLO("yolo11n.pt")  # 사람/차량 등 COCO 80개 클래스
kickboard_model = YOLO("../runs/detect/kickboard_v1/weights/best.pt")  # 킥보드 전용 파인튜닝 모델


def detect(frame, conf_threshold=0.4):
    """
    한 프레임을 받아서 일반 모델 + 킥보드 모델 결과를 합쳐서 반환.
    """
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


def draw_detections(frame, detections):
    """확인용: 박스와 클래스명을 프레임 위에 그려줌"""
    for det in detections:
        x1, y1, x2, y2 = det["bbox"]
        label = f'{det["class"]} {det["confidence"]}'
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(frame, label, (x1, y1 - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
    return frame


if __name__ == "__main__":
    tracker = StationaryObjectTracker(threshold_sec=10)

    for frame, idx in frame_generator("../data/videos/kickboard_test.mp4", target_fps=10):
        detections = detect(frame)
        now = time.time()

        # 방치물 이벤트 판별
        events = tracker.update(detections, now)
        for event in events:
            print(f"🚨 방치물 이벤트 발생: {event}")

        # 탐지 결과 로그 출력 (너무 많으면 이 줄은 나중에 지워도 됨)
        if detections:
            print(f"프레임 #{idx}: {detections}")

        frame = draw_detections(frame, detections)
        cv2.imshow("Stationary Object Test", frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cv2.destroyAllWindows()