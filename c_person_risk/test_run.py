import cv2
import time
from face_detect import FaceDetector
from weapon_detect import WeaponDetector
from event_publisher import send_event

# 9클래스 흉기 -> B파트 규격 2클래스(knife, blunt_weapon) 매핑
CLASS_MAPPER = {
    'knife': 'knife', 
    'long knife': 'knife', 
    'pocket-knife': 'knife', 
    'ice pick': 'knife',
    'baseball bat': 'blunt_weapon', 
    'crow bar': 'blunt_weapon', 
    'hammer': 'blunt_weapon', 
    'sumpak': 'blunt_weapon'
}

face_detector = FaceDetector()
weapon_detector = WeaponDetector("models/best.pt")

cap = cv2.VideoCapture("1sample.mp4")

frame_count = 0
skip_frames = 3
current_faces = []

# 이벤트 중복 발송 방지 타임스탬프 (인물별, 흉기종류별 독립 쿨다운)
last_sent_time = {
    "WANTED_PERSON": {},  # key: name, value: timestamp
    "WEAPON": {}          # key: mapped_label, value: timestamp
}
COOLDOWN_SEC = 3.0

last_pkl_check = 0
PKL_CHECK_INTERVAL = 1

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

    # 0. Hot-Reload 폴링 감지 (5초 간격)
    if current_time - last_pkl_check > PKL_CHECK_INTERVAL:
        face_detector.check_and_reload()
        last_pkl_check = current_time

    # 1. 흉기 탐지 및 이벤트 발행
    weapons = weapon_detector.detect_weapons(frame)
    for w in weapons:
        w_label = w["label"]
        mapped_label = CLASS_MAPPER.get(w_label, w_label)  # 2클래스 매핑
        
        # 흉기 종류별 독립 쿨다운 적용 (dict 연산 버그 수정)
        last_w_time = last_sent_time["WEAPON"].get(w_label, 0)
        if current_time - last_w_time > COOLDOWN_SEC:
            send_event(
                event_type="WEAPON",
                confidence=w["confidence"],
                bbox=w["bbox"],
                meta={"weaponType": mapped_label}
            )
            last_sent_time["WEAPON"][w_label] = current_time

        # 화면 시각화 (매핑된 2클래스 라벨로 통일 표기)
        x1, y1, x2, y2 = w["bbox"]
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
        cv2.putText(frame, f"WEAPON: {mapped_label}", (x1, y1 - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

    # 2. Person-Crop 2단계 얼굴 인식 (프레임 스킵)
    if frame_count % skip_frames == 0:
        current_faces = face_detector.detect_faces_with_person_crop(frame, person_conf=0.35)

    # 얼굴 시각화 및 수배자 이벤트 전송
    for f in current_faces:
        top, right, bottom, left = f["location"]
        name = f["name"]
        score = f["faceMatchScore"]

        # 수배자(Unknown이 아닌 인물)만 이벤트 전송 및 화면 박스 표시
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

            # 녹색 수배자 바운딩 박스 표시
            cv2.rectangle(frame, (left, top), (right, bottom), (0, 255, 0), 2)
            cv2.putText(frame, f"WANTED: {name} ({score})", (left, top - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

    cv2.imshow("OmniGuard - Risk Pipeline Test", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()