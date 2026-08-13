from ultralytics import YOLO
import cv2
import time
import torch
from collections import defaultdict, deque
import math


# ============================================================
# 1. 설정
# ============================================================

HLS_URL = (
    "https://strm1.spatic.go.kr/live/"
    "76.stream/chunklist_w1824089310.m3u8"
)

MODEL_PATH = "yolo11m.pt"

# 차량 클래스
# 2 = car
# 3 = motorcycle
# 5 = bus
# 7 = truck
VEHICLE_CLASSES = [2, 3, 5, 7]

# 이상운전 판단 설정
HISTORY_LENGTH = 20

# 방향이 바뀌는 최소 이동 거리
MIN_MOVE_DISTANCE = 5

# 좌우 방향 변화가 이 횟수 이상 반복되면 이상운전
WEAVING_THRESHOLD = 3

# 차량이 잠깐 사라져도 유지할 프레임
MAX_MISSING_FRAMES = 10


# ============================================================
# 2. GPU / CPU 자동 설정
# ============================================================

if torch.cuda.is_available():

    DEVICE = 0

    # GPU에서는 기존 anomaly_detection.py의 yolo11m 사용
    IMG_SIZE = 640

    # GPU에서는 최대한 자주 분석
    PROCESS_EVERY = 1

    MODE = "GPU"

    print("=" * 50)
    print("🟢 NVIDIA GPU 감지")
    print(f"GPU : {torch.cuda.get_device_name(0)}")
    print("GPU 모드로 실행합니다.")
    print("=" * 50)

else:

    DEVICE = "cpu"

    # CPU에서는 조금 가볍게
    IMG_SIZE = 320
    PROCESS_EVERY = 3

    MODE = "CPU"

    print("=" * 50)
    print("🟡 NVIDIA GPU 없음")
    print("CPU 모드로 실행합니다.")
    print("=" * 50)


# ============================================================
# 3. YOLO 모델
# ============================================================

print("YOLO 모델 로딩 중...")

model = YOLO(MODEL_PATH)

print("✅ YOLO 모델 로딩 완료")


# ============================================================
# 4. HLS 연결
# ============================================================

cap = cv2.VideoCapture(HLS_URL)

if not cap.isOpened():

    print("❌ HLS 연결 실패")
    exit()

print("✅ 이수역 CCTV 연결 성공")
print("🚗 실시간 차량 추적 + 이상운전 감지 시작")
print("ESC를 누르면 종료합니다.")


# ============================================================
# 5. 차량별 상태
# ============================================================

# Vehicle ID -> 최근 중심좌표
track_history = defaultdict(
    lambda: deque(maxlen=HISTORY_LENGTH)
)

# Vehicle ID -> 마지막으로 보인 프레임
last_seen = {}

# 이미 이상운전으로 판단된 차량
anomaly_vehicles = set()


# ============================================================
# 6. 방향 계산
# ============================================================

def get_direction(dx, dy):

    # 좌우 이동량을 중심으로 판단
    if abs(dx) < MIN_MOVE_DISTANCE:
        return None

    if dx > 0:
        return "RIGHT"

    return "LEFT"


# ============================================================
# 7. 이상운전 판단
# ============================================================

def detect_weaving(track_id):

    points = track_history[track_id]

    if len(points) < 8:
        return False

    directions = []

    for i in range(1, len(points)):

        x1, y1 = points[i - 1]
        x2, y2 = points[i]

        dx = x2 - x1
        dy = y2 - y1

        direction = get_direction(dx, dy)

        if direction is not None:
            directions.append(direction)

    if len(directions) < 5:
        return False

    # 연속적인 좌우 방향 변화 횟수 계산
    changes = 0

    for i in range(1, len(directions)):

        if directions[i] != directions[i - 1]:
            changes += 1

    return changes >= WEAVING_THRESHOLD


# ============================================================
# 8. 빨간 이상운전 박스
# ============================================================

def draw_anomaly_box(
    frame,
    x1,
    y1,
    x2,
    y2,
    track_id
):

    # 빨간색
    RED = (0, 0, 255)

    cv2.rectangle(
        frame,
        (x1, y1),
        (x2, y2),
        RED,
        3
    )

    cv2.putText(
        frame,
        f"Vehicle #{track_id}",
        (x1, max(y1 - 30, 25)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        RED,
        2
    )

    cv2.putText(
        frame,
        "WARNING: ABNORMAL DRIVING",
        (x1, y2 + 25),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        RED,
        2
    )


# ============================================================
# 9. FPS
# ============================================================

frame_count = 0
ai_count = 0

fps_start = time.time()

display_fps = 0
ai_fps = 0


# ============================================================
# 10. 실시간 처리
# ============================================================

while True:

    ret, frame = cap.read()

    if not ret:

        print("⚠️ 프레임 수신 실패")
        time.sleep(0.05)
        continue

    frame_count += 1

    annotated_frame = frame.copy()

    # ========================================================
    # AI 분석
    # ========================================================

    if frame_count % PROCESS_EVERY == 0:

        results = model.track(

            frame,

            tracker="bytetrack.yaml",

            classes=VEHICLE_CLASSES,

            conf=0.25,

            persist=True,

            verbose=False,

            imgsz=IMG_SIZE,

            max_det=50,

            device=DEVICE
        )

        ai_count += 1

        boxes = results[0].boxes

        if boxes is not None:

            for box in boxes:

                # Track ID 없는 차량 제외
                if box.id is None:
                    continue

                x1, y1, x2, y2 = map(
                    int,
                    box.xyxy[0]
                )

                track_id = int(box.id[0])

                # 중심점
                cx = int((x1 + x2) / 2)
                cy = int((y1 + y2) / 2)

                # 마지막 확인 프레임
                last_seen[track_id] = frame_count

                # 이동경로 저장
                track_history[track_id].append(
                    (cx, cy)
                )

                # ==================================================
                # 이상운전 판단
                # ==================================================

                if detect_weaving(track_id):

                    anomaly_vehicles.add(track_id)


                
                # 이상운전 차량만 화면에 표시
                # 일반 차량은 추적만 하고 화면에는 표시하지 않음
                # ==================================================

                if track_id in anomaly_vehicles:

                    draw_anomaly_box(
                        annotated_frame,
                        x1,
                        y1,
                        x2,
                        y2,
                        track_id
                    )


    # ========================================================
    # 오래된 차량 상태 정리
    # ========================================================

    stale_ids = []

    for track_id, last_frame in last_seen.items():

        if frame_count - last_frame > MAX_MISSING_FRAMES:

            stale_ids.append(track_id)

    for track_id in stale_ids:

        last_seen.pop(track_id, None)
        track_history.pop(track_id, None)

        # [수정] anomaly_vehicles에서도 같이 정리해야 한다.
        # 이걸 안 하면 이 track_id가 영원히 "이상운전 차량"으로 남아있게 되고,
        # ByteTrack이 나중에 같은 번호를 완전히 다른 차량에게 재사용했을 때
        # 그 새 차량이 아무 이상행동을 안 해도 처음부터 빨간 박스로 잘못 표시된다.
        anomaly_vehicles.discard(track_id)


    # ========================================================
    # FPS 계산
    # ========================================================

    elapsed = time.time() - fps_start

    if elapsed >= 1.0:

        display_fps = frame_count / elapsed
        ai_fps = ai_count / elapsed

        frame_count = 0
        ai_count = 0

        fps_start = time.time()


    # ========================================================
    # 화면 정보
    # ========================================================

    cv2.putText(
        annotated_frame,
        f"MODE: {MODE}",
        (20, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (0, 255, 255),
        2
    )

    cv2.putText(
        annotated_frame,
        f"Display FPS: {display_fps:.1f}",
        (20, 60),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (0, 255, 255),
        2
    )

    cv2.putText(
        annotated_frame,
        f"AI FPS: {ai_fps:.1f}",
        (20, 90),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (0, 255, 255),
        2
    )

    # 이상운전 차량 수
    cv2.putText(
        annotated_frame,
        f"Anomaly Vehicles: {len(anomaly_vehicles)}",
        (20, 120),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (0, 0, 255),
        2
    )


    # ========================================================
    # 화면 출력
    # ========================================================

    cv2.imshow(
        "UTIC LIVE - Real Time Anomaly Detection",
        annotated_frame
    )


    # ESC
    if cv2.waitKey(1) & 0xFF == 27:
        break


# ============================================================
# 종료
# ============================================================

cap.release()
cv2.destroyAllWindows()

print("====================================")
print("실시간 이상운전 테스트 종료")
print("====================================")