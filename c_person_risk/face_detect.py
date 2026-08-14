import os
import pickle
import numpy as np
import cv2
import face_recognition

class FaceDetector:
    def __init__(self, db_path=None, tolerance=0.55):
        if db_path is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            db_path = os.path.join(base_dir, "face_embeddings.pkl")
        self.db_path = db_path
        self.tolerance = tolerance
        self.known_ids = []
        self.known_names = []
        self.known_embeddings = []
        self.last_mtime = 0
        self.load_db()

    def load_db(self):
        if not os.path.exists(self.db_path):
            print(f"[WARN] 수배자 DB 파일 없음: {self.db_path}")
            return
        try:
            self.last_mtime = os.path.getmtime(self.db_path)
            with open(self.db_path, "rb") as f:
                data = pickle.load(f)
            
            self.known_ids = []
            self.known_names = []
            self.known_embeddings = []

            if isinstance(data, list):
                for item in data:
                    self.known_ids.append(item.get("id", "UNKNOWN"))
                    self.known_names.append(item.get("name", "UNKNOWN"))
                    self.known_embeddings.append(item["embedding"])
            elif isinstance(data, dict):
                for k, v in data.items():
                    self.known_ids.append(k)
                    if isinstance(v, dict):
                        self.known_names.append(v.get("name", k))
                        self.known_embeddings.append(v["embedding"])
                    else:
                        self.known_names.append(k)
                        self.known_embeddings.append(v)
            
            print(f"[INFO] 수배자 DB 로드 완료: {len(self.known_ids)}개 임베딩 등록됨")
        except Exception as e:
            print(f"[ERROR] DB 로드 실패: {e}")

    def check_and_reload(self):
        if os.path.exists(self.db_path):
            current_mtime = os.path.getmtime(self.db_path)
            if current_mtime > self.last_mtime:
                print(f"[INFO] 수배자 DB 변동 감지 -> Hot Reload 실행")
                self.load_db()

    def detect_faces(self, frame, person_boxes=None):
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        face_locations = face_recognition.face_locations(rgb_frame)

        if not face_locations or len(self.known_embeddings) == 0:
            return []

        face_encodings = face_recognition.face_encodings(rgb_frame, face_locations)
        results = []

        for (top, right, bottom, left), face_encoding in zip(face_locations, face_encodings):
            distances = face_recognition.face_distance(self.known_embeddings, face_encoding)
            if len(distances) > 0:
                best_idx = np.argmin(distances)
                dist_val = float(distances[best_idx])
                
                if dist_val <= self.tolerance:
                    results.append({
                        "targetId": self.known_ids[best_idx],
                        "name": self.known_names[best_idx],
                        "confidence": round(float(1 - dist_val), 2),
                        "distance": round(dist_val, 4),
                        "location": (top, right, bottom, left),
                        "bbox": [left, top, right, bottom]
                    })

        return results

    def detect_faces_with_person_crop(self, frame, person_boxes=None, *args, **kwargs):
        return self.detect_faces(frame, person_boxes)
