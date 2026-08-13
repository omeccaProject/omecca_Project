import cv2
import time
from face_detect import FaceDetector
from weapon_detect import WeaponDetector
from event_publisher import send_event

face_detector = FaceDetector()
weapon_detector = WeaponDetector("models/best.pt")

cap = cv2.VideoCapture("1sample.mp4")

frame_count = 0
skip_frames = 3
current_faces = []

last_sent_time = {
    "WANTED_PERSON": {},
    "WEAPON": 0
}
COOLDOWN_SEC = 3.0

last_pkl_check = 0
PKL_CHECK_INTERVAL = 5

def resize_to_fit(frame, max_width=720, max_height=1280):
    h, w = frame.shape[:2]
    scale = min(max_width / w, max_height / h, 1.0)
    if scale < 1.0:
        frame = cv2.resize(frame, (int(w * scale), int(h * scale)))
    return frame

while cap.isOpened():
    ret, frame = cap.read()
    if not ret:
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        continue

    frame = resize_to_fit(frame)
    frame_count += 1
    current_time = time.time()

    # 0. Hot-Reload 폴링 감지
    if current_time - last_pkl_check > PKL_CHECK_INTERVAL:
        face_detector.check_and_reload()
        last_pkl_check = current_time

    # 1. 흉기 탐지 및 이벤트 발행
    weapons = weapon_detector.detect_weapons(frame)
    for w in weapons:
        if current_time - last_sent_time["WEAPON"] > COOLDOWN_SEC:
            send_event(
                event_type="WEAPON",
                confidence=w["confidence"],
                bbox=w["bbox"],
                meta={"weaponType": w["label"]}
            )
            last_sent_time["WEAPON"] = current_time

        x1, y1, x2, y2 = w["bbox"]
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
        cv2.putText(frame, f"WEAPON: {w['label']}", (x1, y1 - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

    # 2. Person-Crop 2단계 얼굴 인식 및 이벤트 발행 (프레임 스킵)
    if frame_count % skip_frames == 0:
        # fx=0.5 축소 단계 제거 및 원본 Crop 100% 탐지 적용
        current_faces = face_detector.detect_faces_with_person_crop(frame, person_conf=0.35)

    for f in current_faces:
        # *2 배율 복원 제거 (detect_faces_with_person_crop에서 절대좌표 산출 완료)
        top, right, bottom, left = f["location"]
        name = f["name"]
        score = f["faceMatchScore"]

        if name != "Unknown":
            last_time = last_sent_time["WANTED_PERSON"].get(name, 0)
            if current_time - last_time > COOLDOWN_SEC:
                send_event(
                    event_type="WANTED_PERSON",
                    confidence=score,
                    bbox=[left, top, right, bottom],
                    meta={
                        "matchedDbId": f["matchedDbId"],
                        "personName": name
                    }
                )
                last_sent_time["WANTED_PERSON"][name] = current_time

        color = (0, 255, 0) if name != "Unknown" else (255, 0, 0)
        cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
        cv2.putText(frame, f"{name} ({score})", (left, top - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

    cv2.imshow("OmniGuard - Risk Pipeline Test", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()