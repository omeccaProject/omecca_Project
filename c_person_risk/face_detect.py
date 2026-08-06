import os
import cv2
import face_recognition

class FaceDetector:
    def __init__(self, known_faces_dir="known_faces"):
        self.known_face_encodings = []
        self.known_face_names = []
        self.load_known_faces(known_faces_dir)

    def load_known_faces(self, known_faces_dir):
        if not os.path.exists(known_faces_dir):
            return

        for filename in os.listdir(known_faces_dir):
            if filename.endswith(('.jpg', '.png', '.jpeg')):
                filepath = os.path.join(known_faces_dir, filename)
                image = face_recognition.load_image_file(filepath)
                encodings = face_recognition.face_encodings(image)
                if encodings:
                    self.known_face_encodings.append(encodings[0])
                    name = os.path.splitext(filename)[0]
                    self.known_face_names.append(name)
                    print(f"[INFO] 수배자 DB 로드 완료: {name}")

    def detect_faces(self, rgb_small_frame):
        # 축소된 프레임에서 위치 탐지 및 인코딩
        face_locations = face_recognition.face_locations(rgb_small_frame)
        face_encodings = face_recognition.face_encodings(rgb_small_frame, face_locations)

        results = []
        for face_encoding, face_location in zip(face_encodings, face_locations):
            matches = face_recognition.compare_faces(self.known_face_encodings, face_encoding, tolerance=0.5)
            name = "Unknown"
            confidence = 0.0

            face_distances = face_recognition.face_distance(self.known_face_encodings, face_encoding)
            if len(face_distances) > 0:
                best_match_index = face_distances.argmin()
                if matches[best_match_index]:
                    name = self.known_face_names[best_match_index]
                    confidence = round((1.0 - face_distances[best_match_index]), 2)

            results.append({
                "name": name,
                "confidence": confidence,
                "location": face_location  # (top, right, bottom, left)
            })

        return results