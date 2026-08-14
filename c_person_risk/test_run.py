import os
import sys
import cv2
import time

base_dir = os.path.dirname(os.path.abspath(__file__))
if base_dir not in sys.path:
    sys.path.append(base_dir)

from weapon_detect import WeaponDetector
from face_detect import FaceDetector

def main():
    video_path = os.path.join(base_dir, "my_sample.mp4")
    if not os.path.exists(video_path):
        video_path = "c_person_risk/my_sample.mp4"

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"[ERROR] 영상을 열 수 없습니다: {video_path}")
        return

    weapon_detector = WeaponDetector()
    face_detector = FaceDetector(tolerance=0.60)

    print("[INFO] Risk Pipeline Test 구동 시작 (종료: 'q' 키)")

    while True:
        ret, frame = cap.read()
        if not ret or frame is None:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            time.sleep(0.03)
            continue

        h, w = frame.shape[:2]
        if h > 720:
            scale = 720.0 / h
            frame = cv2.resize(frame, (int(w * scale), 720))

        try:
            if hasattr(face_detector, "check_and_reload"):
                face_detector.check_and_reload()

            # 1. 수배자 탐지 (선명한 720p frame 직접 전달)
            faces = []
            if hasattr(face_detector, "detect_faces_with_person_crop"):
                faces = face_detector.detect_faces_with_person_crop(frame)
            elif hasattr(face_detector, "detect_faces"):
                faces = face_detector.detect_faces(frame)

            for f in faces:
                name = f.get("name", "Unknown")
                target_id = f.get("targetId") or f.get("matchedDbId", "W000")
                
                print(f"[EVENT SENT 201] WANTED_PERSON: {{'targetId': '{target_id}', 'name': '{name}'}}")

                # location 및 bbox 좌표 시각화 (1:1 직접 매핑)
                if "location" in f:
                    top, right, bottom, left = f["location"]
                    cv2.rectangle(frame, (left, top), (right, bottom), (0, 0, 255), 2)
                    cv2.putText(frame, f"WANTED: {name}", (left, max(20, top - 10)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                elif "bbox" in f:
                    bbox = f["bbox"]
                    if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
                        l, t, r, b = [int(v) for v in bbox]
                        cv2.rectangle(frame, (l, t), (r, b), (0, 0, 255), 2)
                        cv2.putText(frame, f"WANTED: {name}", (l, max(20, t - 10)),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

            # 2. 흉기 탐지
            weapons = weapon_detector.detect_weapon(frame) if hasattr(weapon_detector, "detect_weapon") else []
            for w_obj in weapons:
                w_type = w_obj.get("weaponType", "knife") if isinstance(w_obj, dict) else "knife"
                print(f"[EVENT SENT 201] WEAPON: {{'weaponType': '{w_type}'}}")
                if isinstance(w_obj, dict) and "bbox" in w_obj:
                    wb = w_obj["bbox"]
                    if len(wb) == 4:
                        l, t, r, b = [int(v) for v in wb]
                        cv2.rectangle(frame, (l, t), (r, b), (0, 255, 255), 2)
                        cv2.putText(frame, f"WEAPON: {w_type}", (l, max(20, t - 10)),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

            cv2.imshow("OmniGuard - Risk Pipeline Test", frame)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

        except Exception as e:
            print(f"[FRAME ERROR] {e}")
            continue

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
