import os
import pickle
import threading
import numpy as np
import face_recognition

class FaceDetector:
    def __init__(self, db_path="face_embeddings.pkl", model="cnn"):
        self.db_path = db_path
        self.model = model
        self.lock = threading.RLock()  # Thread-safe 동기화를 위한 RLock
        self.known_ids = []
        self.known_names = []
        self.known_face_encodings = []
        self._last_mtime = None  # ← 추가: Hot-Reload 폴링용 파일 수정시간 기록
        self.load_known_faces(self.db_path)
        self._update_mtime()  # ← 추가: 최초 로드 시점의 mtime 저장

    def _update_mtime(self):
        """현재 pkl 파일의 수정시간을 기록 (없으면 None)"""
        try:
            self._last_mtime = os.path.getmtime(self.db_path)
        except FileNotFoundError:
            self._last_mtime = None

    def reload_embeddings(self):
        """API 수배자 추가 시 서버 재시작 없이 메모리를 즉시 갱신하는 메서드 (Hot Reload)"""
        print("[INFO] 수배자 DB 메모리 재로드(Hot Reload) 요청...")
        self.load_known_faces(self.db_path)
        self._update_mtime()  # ← 추가: 갱신 후 mtime도 같이 최신화 (안 하면 check_and_reload가 계속 재갱신 시도함)

    def check_and_reload(self):
        """
        pkl 파일이 마지막 로드 이후 바뀌었는지 확인하고, 바뀌었으면 reload.
        test_run.py 쪽에서 몇 초 간격으로만 호출할 것 (매 프레임 호출 금지 - 디스크 I/O 부담)
        """
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

        # 기존 리스트 형태 DB 구조 처리 ([{"id": ..., "name": ..., "embedding": ...}])
        if isinstance(db, list):
            for person in db:
                new_ids.append(person["id"])
                new_names.append(person["name"])
                new_encodings.append(person["embedding"])
                print(f"[INFO] 수배자 DB 로드 완료: {person['id']} - {person['name']}")
        # 딕셔너리 형태 DB 구조 예외 처리 지원
        elif isinstance(db, dict):
            new_ids = db.get("ids", [])
            new_names = db.get("names", [])
            new_encodings = db.get("encodings", [])
            print(f"[INFO] 수배자 DB 로드 완료: 총 {len(new_ids)}명")

        # Thread-safe하게 안전하게 메모리 교체
        with self.lock:
            self.known_ids = new_ids
            self.known_names = new_names
            self.known_face_encodings = new_encodings

    def detect_faces(self, rgb_small_frame):
        # 추론 중 데이터 변경으로 인한 에러 방지를 위해 Lock 상태에서 스냅샷 복사
        with self.lock:
            known_ids_snap = list(self.known_ids)
            known_names_snap = list(self.known_names)
            known_encodings_snap = list(self.known_face_encodings)

        # 원거리 검출력 강화를 위해 upsample=2, GPU 사용을 위해 model="cnn" 적용
        face_locations = face_recognition.face_locations(rgb_small_frame, number_of_times_to_upsample=2, model=self.model)
        face_encodings = face_recognition.face_encodings(rgb_small_frame, face_locations)

        results = []
        for face_encoding, face_location in zip(face_encodings, face_locations):
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
                    confidence = round((1.0 - face_distances[best_match_index]), 2)

            results.append({
                "matchedDbId": matched_id,   # 스키마 meta.matchedDbId 에 그대로 들어감
                "name": name,
                "faceMatchScore": confidence,  # 스키마 meta.faceMatchScore 에 그대로 들어감
                "location": face_location
            })

        return results