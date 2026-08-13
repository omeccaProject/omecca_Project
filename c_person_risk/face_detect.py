import os
import pickle
import threading
import cv2
import numpy as np
import face_recognition
from ultralytics import YOLO

class FaceDetector:
    def __init__(self, db_path="face_embeddings.pkl", model="cnn"):
        self.db_path = db_path
        self.model = model
        self.lock = threading.RLock()
        self.known_ids = []
        self.known_names = []
        self.known_face_encodings = []
        self._last_mtime = None
        
        # YOLO Person 탐지용 모델 초기화 (1회만 로드)
        self.person_model = YOLO("yolov8n.pt")
        
        self.load_known_faces(self.db_path)
        self._update_mtime()

    def _update_mtime(self):
        try:
            self._last_mtime = os.path.getmtime(self.db_path)
        except FileNotFoundError:
            self._last_mtime = None

    def reload_embeddings(self):
        print("[INFO] 수배자 DB 메모리 재로드(Hot Reload) 요청...")
        self.load_known_faces(self.db_path)
        self._update_mtime()

    def check_and_reload(self):
        try:
            mtime = os.path.getmtime(self.db_path)
        except FileNotFoundError:
            return

        if mtime != self._last_mtime:
            self.reload_embeddings()

    def load_known_faces(self, db_path):
        if not os.path.exists(db_path):
            print(f"[WARN] {db_path} 없음. build_face_db.py 먼저 실행하세요.")
            return

        with open(db_path, "rb") as f:
            db = pickle.load(f)

        new_ids = []
        new_names = []
        new_encodings = []

        if isinstance(db, list):
            for person in db:
                new_ids.append(person["id"])
                new_names.append(person["name"])
                new_encodings.append(person["embedding"])
                print(f"[INFO] 수배자 DB 로드 완료: {person['id']} - {person['name']}")
        elif isinstance(db, dict):
            new_ids = db.get("ids", [])
            new_names = db.get("names", [])
            new_encodings = db.get("encodings", [])
            print(f"[INFO] 수배자 DB 로드 완료: 총 {len(new_ids)}명")

        with self.lock:
            self.known_ids = new_ids
            self.known_names = new_names
            self.known_face_encodings = new_encodings

    def detect_faces_with_person_crop(self, frame, person_conf=0.35):
        """
        2단계 Person Crop 파이프라인
        - YOLO로 사람 영역선출 후 원본 해상도(100%) Crop 내부에서 얼굴 인식
        - 절대좌표 오프셋 변환 반환 (*2 배율 연산 불필요)
        """
        with self.lock:
            known_ids_snap = list(self.known_ids)
            known_names_snap = list(self.known_names)
            known_encodings_snap = list(self.known_face_encodings)

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
                    confidence = 0.0

                    if len(known_encodings_snap) > 0:
                        matches = face_recognition.compare_faces(known_encodings_snap, face_encoding, tolerance=0.4)
                        face_distances = face_recognition.face_distance(known_encodings_snap, face_encoding)
                        best_match_index = face_distances.argmin()

                        if matches[best_match_index]:
                            matched_id = known_ids_snap[best_match_index]
                            name = known_names_snap[best_match_index]
                            confidence = round(float(1.0 - face_distances[best_match_index]), 2)

                    # Crop 오프셋 기준 글로벌 절대좌표 계산
                    global_top = py1 + top
                    global_right = px1 + right
                    global_bottom = py1 + bottom
                    global_left = px1 + left

                    results.append({
                        "matchedDbId": matched_id,
                        "name": name,
                        "faceMatchScore": confidence,
                        "location": (global_top, global_right, global_bottom, global_left)
                    })

        return results