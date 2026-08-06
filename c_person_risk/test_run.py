import cv2
import time
from face_detect import FaceDetector
from weapon_detect import WeaponDetector
from event_publisher import send_event

face_detector = FaceDetector()
weapon_detector = WeaponDetector("models/best.pt")

cap = cv2.VideoCapture("sample.mp4")

frame_count = 0
skip_frames = 5
current_faces = []

# 이벤트 중복 발송 방지용 타임스탬프 저장소
last_sent_time = {
    "WANTED_PERSON": {}, # key: name, value: last_time
    "WEAPON_DETECTED": 0 # value: last_time
}
COOLDOWN_SEC = 3.0 # 동일 이벤트 재전송 대기 시간(초)

while cap.isOpened():
    ret, frame = cap.read()
    if not ret:
        break

    frame_count += 1
    current_time = time.time()

    # 1. 흉기 탐지 및 이벤트 발행
    weapons = weapon_detector.detect_weapons(frame)
    for w in weapons:
        # 흉기 감지 이벤트 전송 (Cool-down 적용)
        if current_time - last_sent_time["WEAPON_DETECTED"] > COOLDOWN_SEC:
            send_event(
                event_type="WEAPON_DETECTED",
                confidence=w["confidence"],
                bbox=w["bbox"],
                details={"weapon_type": w["label"]}
            )
            last_sent_time["WEAPON_DETECTED"] = current_time

        # 시각화
        x1, y1, x2, y2 = w["bbox"]
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
        cv2.putText(frame, f"WEAPON: {w['label']}", (x1, y1 - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

    # 2. 얼굴 인식 및 이벤트 발행 (프레임 스킵)
    if frame_count % skip_frames == 0:
        small_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
        rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
        current_faces = face_detector.detect_faces(rgb_small_frame)

    for f in current_faces:
        top, right, bottom, left = [coord * 4 for coord in f["location"]]
        name = f["name"]

        # 수배자 인지 시 이벤트 전송 (Unknown 제외, Cool-down 적용)
        if name != "Unknown":
            last_time = last_sent_time["WANTED_PERSON"].get(name, 0)
            if current_time - last_time > COOLDOWN_SEC:
                send_event(
                    event_type="WANTED_PERSON",
                    confidence=f["confidence"],
                    bbox=[left, top, right, bottom],
                    details={"person_name": name}
                )
                last_sent_time["WANTED_PERSON"][name] = current_time

        # 시각화
        color = (0, 0, 255) if name != "Unknown" else (255, 0, 0)
        cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
        cv2.putText(frame, f"{name} ({f['confidence']})", (left, top - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

    cv2.imshow("OmniGuard - Risk Pipeline Test", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()