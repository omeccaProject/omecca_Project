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
    "WEAPON": {}          # key: w_label, value: timestamp
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

    # 0. Hot-Reload 폴링 감지 (1초 간격)
    if current_time - last_pkl_check > PKL_CHECK_INTERVAL:
        face_detector.check_and_reload()
        last_pkl_check = current_time

    # 1. 흉기 탐지 및 이벤트 발행 (매 프레임)
    weapons = weapon_detector.detect_weapons(frame)
    for w in weapons:
        w_label = w["label"]
        mapped_label = CLASS_MAPPER.get(w_label, w_label)
        
        last_w_time = last_sent_time["WEAPON"].get(w_label, 0)
        if current_time - last_w_time > COOLDOWN_SEC:
            send_event(
                event_type="WEAPON",
                confidence=w["confidence"],
                bbox=w["bbox"],
                meta={"weaponType": mapped_label}
            )
            last_sent_time["WEAPON"][w_label] = current_time

        # 흉기 시각화 (빨간색)
        x1, y1, x2, y2 = w["bbox"]
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
        cv2.putText(frame, f"WEAPON: {mapped_label}", (x1, y1 - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

    # 2. Person-Crop 2단계 얼굴 인식 (3프레임 스킵)
    if frame_count % skip_frames == 0:
        current_faces = face_detector.detect_faces_with_person_crop(frame, person_conf=0.35)

    # 3. 얼굴 시각화 및 수배자(+흉기 소지 여부) 이벤트 전송
    for f in current_faces:
        top, right, bottom, left = f["location"]
        name = f["name"]
        score = f["faceMatchScore"]

        if name != "Unknown":
            # personBbox 안전 참조 (없을 경우 얼굴 Bbox로 대체)
            px1, py1, px2, py2 = f.get("personBbox", (left, top, right, bottom))
            
            armed_weapons = []
            for w in weapons:
                wx1, wy1, wx2, wy2 = w["bbox"]
                wcx, wcy = (wx1 + wx2) / 2, (wy1 + wy2) / 2
                if px1 <= wcx <= px2 and py1 <= wcy <= py2:
                    armed_weapons.append(CLASS_MAPPER.get(w["label"], w["label"]))

            # [always-defined 스키마]
            meta = {
                "matchedDbId": f["matchedDbId"],
                "personName": name,
                "isArmed": bool(armed_weapons),
                "armedWith": armed_weapons[0] if armed_weapons else None
            }

            last_time = last_sent_time["WANTED_PERSON"].get(name, 0)
            if current_time - last_time > COOLDOWN_SEC:
                send_event(
                    event_type="WANTED_PERSON",
                    confidence=score,
                    bbox=[left, top, right, bottom],
                    meta=meta
                )
                last_sent_time["WANTED_PERSON"][name] = current_time

            # 시각화: 무장 시 주황색, 미무장 시 녹색
            label_text = f"WANTED: {name} (ARMED)" if armed_weapons else f"WANTED: {name} ({score})"
            box_color = (0, 165, 255) if armed_weapons else (0, 255, 0)
            
            cv2.rectangle(frame, (left, top), (right, bottom), box_color, 2)
            cv2.putText(frame, label_text, (left, top - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, box_color, 2)

    cv2.imshow("OmniGuard - Risk Pipeline Test", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()