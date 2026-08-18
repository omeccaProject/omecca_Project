import os
import pickle
import threading
import cv2
import numpy as np
import face_recognition
from ultralytics import YOLO


class FaceDetector:
    def __init__(self, db_path=None, tolerance=0.55, model="cnn"):
        if db_path is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            db_path = os.path.join(base_dir, "face_embeddings.pkl")
        self.db_path = db_path
        self.tolerance = tolerance
        self.model = model
        self.lock = threading.RLock()
        self.known_ids = []
        self.known_names = []
        self.known_embeddings = []
        self.last_mtime = 0

        # YOLO Person 탐지용 모델 초기화 (1회만 로드)
        self.person_model = YOLO("yolov8n.pt")

        self.load_db()

    def load_db(self):
        if not os.path.exists(self.db_path):
            return
        try:
            self.last_mtime = os.path.getmtime(self.db_path)
            with open(self.db_path, "rb") as f:
                data = pickle.load(f)

            new_ids = []
            new_names = []
            new_embeddings = []

            if isinstance(data, list):
                for item in data:
                    new_ids.append(item.get("id", "UNKNOWN"))
                    new_names.append(item.get("name", "UNKNOWN"))
                    new_embeddings.append(item["embedding"])
            elif isinstance(data, dict):
                for k, v in data.items():
                    new_ids.append(k)
                    if isinstance(v, dict):
                        new_names.append(v.get("name", k))
                        new_embeddings.append(v["embedding"])
                    else:
                        new_names.append(k)
                        new_embeddings.append(v)

            with self.lock:
                self.known_ids = new_ids
                self.known_names = new_names
                self.known_embeddings = new_embeddings
        except Exception as e:
            print(f"[ERROR] DB 로드 실패: {e}")

    # 하위 호환용 별칭 (다른 코드가 load_known_faces를 호출할 수도 있어 남겨둠)
    def load_known_faces(self, db_path=None):
        if db_path is not None:
            self.db_path = db_path
        self.load_db()

    def reload_embeddings(self):
        print("[INFO] 수배자 DB 메모리 재로드(Hot Reload) 요청...")
        self.load_db()

    def check_and_reload(self):
        if os.path.exists(self.db_path):
            current_mtime = os.path.getmtime(self.db_path)
            if current_mtime > self.last_mtime:
                self.load_db()

    def detect_faces_with_person_crop(self, frame, person_conf=0.35, *args, **kwargs):
        """
        2단계 Person Crop 파이프라인
        - YOLO로 사람 영역 선출 후 원본 해상도(100%) Crop 내부에서 얼굴 인식
        - 절대좌표 오프셋 변환 반환
        - personBbox: 이 얼굴이 속한 사람의 YOLO 전체 영역 (흉기 소지 판정용)
        """
        with self.lock:
            known_ids_snap = list(self.known_ids)
            known_names_snap = list(self.known_names)
            known_embeddings_snap = list(self.known_embeddings)

        person_results = self.person_model(frame, classes=[0], conf=person_conf, verbose=False)
        results = []

        for r in person_results:
            for box in r.boxes:
                px1, py1, px2, py2 = map(int, box.xyxy[0].tolist())
                crop = frame[py1:py2, px1:px2]
                if crop.size == 0:
                    continue

                rgb_crop = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
                face_locations = face_recognition.face_locations(
                    rgb_crop, number_of_times_to_upsample=1, model=self.model
                )
                face_encodings = face_recognition.face_encodings(rgb_crop, face_locations)

                for face_encoding, (top, right, bottom, left) in zip(face_encodings, face_locations):
                    matched_id = None
                    name = "Unknown"
                    score = 0.0

                    if len(known_embeddings_snap) > 0:
                        distances = face_recognition.face_distance(known_embeddings_snap, face_encoding)
                        best_idx = int(np.argmin(distances))
                        dist_val = float(distances[best_idx])

                        if dist_val <= self.tolerance:
                            score = round(float(1.0 - dist_val), 2)
                            matched_id = known_ids_snap[best_idx]
                            name = known_names_snap[best_idx]

                    global_top = py1 + top
                    global_right = px1 + right
                    global_bottom = py1 + bottom
                    global_left = px1 + left

                    results.append({
                        "matchedDbId": matched_id,
                        "targetId": matched_id,
                        "name": name,
                        "faceMatchScore": score,
                        "confidence": score,
                        "location": (global_top, global_right, global_bottom, global_left),
                        "personBbox": (px1, py1, px2, py2),
                        "bbox": [global_left, global_top, global_right, global_bottom]
                    })

        return results

    # 구버전 test_run_integrated.py 등 다른 코드가 detect_faces를 직접 부를 수도 있어 남겨둠
    def detect_faces(self, frame, person_boxes=None):
        return self.detect_faces_with_person_crop(frame)