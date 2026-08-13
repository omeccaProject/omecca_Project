import os
import sys
import time
from pathlib import Path
import cv2

# ============================================================================
# 1. 프로젝트 루트 및 A모듈(a_core) 경로 등록 (a_core 내부 임포트 충돌 방지)
# ============================================================================
PROJECT_ROOT = Path(__file__).resolve().parent.parent
A_CORE_DIR = PROJECT_ROOT / "a_core"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(A_CORE_DIR) not in sys.path:
    sys.path.insert(0, str(A_CORE_DIR))

# 모듈 Import
from a_core.yolo_infer import detect, WEAPON_CLASSES
from c_person_risk.face_detect import FaceDetector
from c_person_risk.event_publisher import send_event

# ============================================================================
# 2. 경로 및 객체 초기화
# ============================================================================
C_RISK_DIR = PROJECT_ROOT / "c_person_risk"
DB_PATH = str(C_RISK_DIR / "face_embeddings.pkl")
VIDEO_PATH = str(C_RISK_DIR / "sample.mp4")  # 테스트용 샘플 비디오 경로

# GPU 기반 CNN 모델을 사용하는 FaceDetector 생성
face_detector = FaceDetector(db_path=DB_PATH, model="cnn")

CAM_ID = "CCTV-014"
frame_count = 0
skip_frames = 2  # GPU 서버 환경이므로 프레임 스킵 간격을 줄여 반응성 향상
current_faces = []

# 이벤트 쿨다운 관리
last_sent_time = {
    "WANTED_PERSON": {},
    "WEAPON": 0
}
COOLDOWN_SEC = 3.0


def resize_to_fit(frame, max_width=1280, max_height=720):
    """화면 표시 및 추론용 해상도 조절 (원본 비율 유지)"""
    h, w = frame.shape[:2]
    scale = min(max_width / w, max_height / h, 1.0)
    if scale < 1.0:
        frame = cv2.resize(frame, (int(w * scale), int(h * scale)))
    return frame


# 비디오 로드
cap = cv2.VideoCapture(VIDEO_PATH)
if not cap.isOpened():
    print(f"[ERROR] 비디오 파일을 열 수 없습니다: {VIDEO_PATH}")
    sys.exit(1)

print(f"[INFO] 통합 관제 테스트 시작 (CAM_ID: {CAM_ID})... 'q' 누르면 종료")

while cap.isOpened():
    ret, frame = cap.read()
    if not ret:
        break

    frame = resize_to_fit(frame)
    frame_count += 1
    current_time = time.time()

    # ------------------------------------------------------------------------
    # 1. 흉기 탐지 — A모듈 detect() 결과 중 WEAPON_CLASSES만 필터링
    # ------------------------------------------------------------------------
    detections = detect(frame, conf_threshold=0.4)
    weapons = [d for d in detections if d["class"] in WEAPON_CLASSES]

    for w in weapons:
        if current_time - last_sent_time["WEAPON"] > COOLDOWN_SEC:
            send_event(
                event_type="WEAPON",
                confidence=w["confidence"],
                bbox=w["bbox"],
                cam_id=CAM_ID,
                meta={"weaponType": w["class"]}
            )
            last_sent_time["WEAPON"] = current_time

        x1, y1, x2, y2 = w["bbox"]
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
        cv2.putText(frame, f"WEAPON: {w['class']}", (x1, y1 - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

    # ------------------------------------------------------------------------
    # 2. 수배자 얼굴 인식 (GPU cnn 기반 - 원거리 디테일 보존을 위해 축소 없이 전달)
    # ------------------------------------------------------------------------
    if frame_count % skip_frames == 0:
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        current_faces = face_detector.detect_faces(rgb_frame)

    for f in current_faces:
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
                    cam_id=CAM_ID,
                    meta={
                        "matchedDbId": f["matchedDbId"],
                        "personName": name
                    }
                )
                last_sent_time["WANTED_PERSON"][name] = current_time

        color = (0, 0, 255) if name != "Unknown" else (255, 0, 0)
        cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
        cv2.putText(frame, f"{name} ({score})", (left, top - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

    # 화면 시각화
    cv2.imshow("OmniGuard - Integrated Pipeline Test (Face + Weapon)", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()