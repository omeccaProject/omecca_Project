import os
import pickle
import numpy as np
import face_recognition

class FaceDetector:
    def __init__(self, db_path="face_embeddings.pkl"):
        self.known_ids = []
        self.known_names = []
        self.known_face_encodings = []
        self.load_known_faces(db_path)

    def load_known_faces(self, db_path):
        if not os.path.exists(db_path):
            print(f"[WARN] {db_path} 없음. build_face_db.py 먼저 실행하세요.")
            return

        with open(db_path, "rb") as f:
            db = pickle.load(f)

        for person in db:
            self.known_ids.append(person["id"])
            self.known_names.append(person["name"])
            self.known_face_encodings.append(person["embedding"])
            print(f"[INFO] 수배자 DB 로드 완료: {person['id']} - {person['name']}")

    def detect_faces(self, rgb_small_frame):
        face_locations = face_recognition.face_locations(rgb_small_frame)
        face_encodings = face_recognition.face_encodings(rgb_small_frame, face_locations)

        results = []
        for face_encoding, face_location in zip(face_encodings, face_locations):
            matched_id = None
            name = "Unknown"
            confidence = 0.0

            if len(self.known_face_encodings) > 0:
                matches = face_recognition.compare_faces(self.known_face_encodings, face_encoding, tolerance=0.5)
                face_distances = face_recognition.face_distance(self.known_face_encodings, face_encoding)
                best_match_index = face_distances.argmin()

                if matches[best_match_index]:
                    matched_id = self.known_ids[best_match_index]
                    name = self.known_names[best_match_index]
                    confidence = round((1.0 - face_distances[best_match_index]), 2)

            results.append({
                "matchedDbId": matched_id,   # 스키마 meta.matchedDbId 에 그대로 들어감
                "name": name,
                "faceMatchScore": confidence,  # 스키마 meta.faceMatchScore 에 그대로 들어감
                "location": face_location
            })

        return results