import cv2
import time
from face_detect import FaceDetector
from weapon_detect import WeaponDetector
from event_publisher import send_event

face_detector = FaceDetector()
weapon_detector = WeaponDetector("models/best.pt")

cap = cv2.VideoCapture("sample.mp4")

frame_count = 0
skip_frames = 3
current_faces = []

# 이벤트 중복 발송 방지용 타임스탬프 저장소
last_sent_time = {
    "WANTED_PERSON": {},  # key: name, value: last_time
    "WEAPON": 0            # value: last_time
}
COOLDOWN_SEC = 3.0  # 동일 이벤트 재전송 대기 시간(초)


def resize_to_fit(frame, max_width=720, max_height=1280):
    """세로/가로 어떤 영상이든 비율 유지하면서 화면에 맞게 축소"""
    h, w = frame.shape[:2]
    scale = min(max_width / w, max_height / h, 1.0)
    if scale < 1.0:
        frame = cv2.resize(frame, (int(w * scale), int(h * scale)))
    return frame


while cap.isOpened():
    ret, frame = cap.read()
    if not ret:
        break

    frame = resize_to_fit(frame)  # ← 추가: 세로 영상 잘림 방지

    frame_count += 1
    current_time = time.time()

    # 1. 흉기 탐지 및 이벤트 발행
    weapons = weapon_detector.detect_weapons(frame)
    for w in weapons:
        if current_time - last_sent_time["WEAPON"] > COOLDOWN_SEC:
            send_event(
                event_type="WEAPON",  # ← 수정: 스키마 규격 eventType과 일치
                confidence=w["confidence"],
                bbox=w["bbox"],
                meta={"weaponType": w["label"]}  # ← 수정: camelCase 통일
            )
            last_sent_time["WEAPON"] = current_time

        x1, y1, x2, y2 = w["bbox"]
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
        cv2.putText(frame, f"WEAPON: {w['label']}", (x1, y1 - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

    # 2. 얼굴 인식 및 이벤트 발행 (프레임 스킵)
    if frame_count % skip_frames == 0:
        small_frame = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5)
        rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
        current_faces = face_detector.detect_faces(rgb_small_frame)

    for f in current_faces:
        top, right, bottom, left = [coord * 2 for coord in f["location"]]
        name = f["name"]
        score = f["faceMatchScore"]  # ← 수정: confidence -> faceMatchScore

        if name != "Unknown":
            last_time = last_sent_time["WANTED_PERSON"].get(name, 0)
            if current_time - last_time > COOLDOWN_SEC:
                send_event(
                    event_type="WANTED_PERSON",
                    confidence=score,
                    bbox=[left, top, right, bottom],
                    meta={
                        "matchedDbId": f["matchedDbId"],  # ← 추가: 스키마 필드
                        "personName": name                # ← 수정: camelCase 통일
                    }
                )
                last_sent_time["WANTED_PERSON"][name] = current_time

        color = (0, 0, 255) if name != "Unknown" else (255, 0, 0)
        cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
        cv2.putText(frame, f"{name} ({score})", (left, top - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

    cv2.imshow("OmniGuard - Risk Pipeline Test", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()