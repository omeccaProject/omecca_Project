from ultralytics import YOLO
import cv2
from PIL import Image
from PIL import ImageDraw
from PIL import ImageFont
import numpy as np

# ==========================
# 설정
# ==========================

model = YOLO("yolo11m.pt")

# 차량 클래스
VEHICLE_CLASSES = [2, 3, 5, 7]

# 사용할 번호판 목록
available_plates = [
    "01가0785",
    "12가3456",
    "85나1234",
    "99모1111",
    "11나2222",
    "77가7777",
    "33다1234",
    "88허5678"
]

# 관심 차량
wanted_db = {
    "12가3456",
    "99모1111"
}

# 관심 차량 표시 색상 (빨간색)
WANTED_COLOR = (0, 0, 255)

# 몇 프레임까지 "유지"해서 그려줄지 (관심 차량만 적용)
HOLD_FRAMES = 5

# 이 프레임 수 이상 안 보이면 아예 기록에서 삭제 (메모리 정리)
STALE_FRAMES = 150

# ==========================
# 상태 저장용 변수
# ==========================

# Track ID -> 번호판 (모든 차량 대상. 최초 등장 시 한 번만 배정)
track_to_plate = {}
plate_index = 0

# 아래 세 딕셔너리는 "관심 차량"에 대해서만 채워진다
# Track ID -> 이동 경로 좌표 리스트
track_history = {}
# Track ID -> 마지막 박스 좌표
last_boxes = {}
# Track ID -> 마지막으로 검출된 프레임 번호
last_seen = {}

# Track ID -> Kalman Filter (관심 차량이 잠시 안 보일 때 위치 예측용)
kalman_filters = {}

frame_count = 0


# ==========================
# 그리기 헬퍼 함수
# ==========================

def get_or_assign_plate(track_id):
    """처음 등장한 track_id면 번호판을 새로 배정하고, 이미 있으면 기존 번호판 반환."""
    global plate_index

    if track_id not in track_to_plate:
        track_to_plate[track_id] = available_plates[plate_index % len(available_plates)]
        plate_index += 1

    return track_to_plate[track_id]


def create_kalman_filter(cx, cy):
    """등속도 모델(x, y, vx, vy) 기반 Kalman Filter 생성."""
    kf = cv2.KalmanFilter(4, 2)

    kf.measurementMatrix = np.array([
        [1, 0, 0, 0],
        [0, 1, 0, 0]
    ], np.float32)

    kf.transitionMatrix = np.array([
        [1, 0, 1, 0],
        [0, 1, 0, 1],
        [0, 0, 1, 0],
        [0, 0, 0, 1]
    ], np.float32)

    kf.processNoiseCov = np.eye(4, dtype=np.float32) * 0.03

    kf.statePre = np.array([[cx], [cy], [0], [0]], np.float32)
    kf.statePost = np.array([[cx], [cy], [0], [0]], np.float32)

    return kf


def update_kalman_filter(track_id, cx, cy):
    """YOLO가 실제로 검출한 프레임: Kalman Filter를 생성하거나 predict + correct."""
    if track_id not in kalman_filters:
        kalman_filters[track_id] = create_kalman_filter(cx, cy)
    else:
        kf = kalman_filters[track_id]
        kf.predict()
        kf.correct(np.array([[np.float32(cx)], [np.float32(cy)]]))


def predict_box_from_kalman(track_id, box_size):
    """YOLO가 놓친 프레임: Kalman Filter로 다음 위치를 예측해서 박스 좌표를 만든다."""
    kf = kalman_filters.get(track_id)

    if kf is None:
        return None

    predicted = kf.predict()
    pred_cx, pred_cy = float(predicted[0, 0]), float(predicted[1, 0])

    w, h = box_size
    x1 = int(pred_cx - w / 2)
    y1 = int(pred_cy - h / 2)
    x2 = int(pred_cx + w / 2)
    y2 = int(pred_cy + h / 2)

    return (x1, y1, x2, y2)


def draw_trajectory(frame, points):
    """관심 차량의 이동 경로(빨간 선)를 그린다."""
    for i in range(1, len(points)):
        cv2.line(frame, points[i - 1], points[i], WANTED_COLOR, 2)


def draw_wanted_box(frame, coords, track_id, plate, plate_draw_jobs):
    """관심 차량 박스 + Vehicle ID + TARGET 텍스트를 그리고,
    번호판은 나중에 한 번에 그리기 위해 작업 목록에 추가한다."""
    x1, y1, x2, y2 = coords

    cv2.rectangle(frame, (x1, y1), (x2, y2), WANTED_COLOR, 2)

    cv2.putText(
        frame, f"Vehicle #{track_id}", (x1, y1 - 10),
        cv2.FONT_HERSHEY_SIMPLEX, 0.7, WANTED_COLOR, 2
    )

    cv2.putText(
        frame, "TARGET", (x1, y2 + 25),
        cv2.FONT_HERSHEY_SIMPLEX, 0.7, WANTED_COLOR, 2
    )

    plate_draw_jobs.append((x1, y1, plate))


# ==========================
# 영상 열기
# ==========================

cap = cv2.VideoCapture("videos/traffic.mp4")

width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
fps = cap.get(cv2.CAP_PROP_FPS)

fourcc = cv2.VideoWriter_fourcc(*'mp4v')

out = cv2.VideoWriter(
    "result/result.mp4",
    fourcc,
    fps,
    (width, height)
)

# ==========================
# 추적 시작
# ==========================

font = ImageFont.truetype("C:/Windows/Fonts/malgun.ttf", 22)

while True:

    frame_count += 1

    ret, frame = cap.read()

    if not ret:
        break

    results = model.track(
        frame,
        tracker="bytetrack.yaml",
        classes=VEHICLE_CLASSES,
        conf=0.25,
        persist=True,
        verbose=False
    )

    annotated_frame = frame.copy()

    boxes = results[0].boxes

    # 이번 프레임에 실제로 검출된 "관심 차량" track_id 모음
    seen_wanted_this_frame = set()

    # 이번 프레임에 그려야 할 번호판 텍스트 정보 모음
    # (x1, y1, plate_text) 형태로 저장해뒀다가 PIL로 한 번에 그림
    plate_draw_jobs = []

    if boxes is not None:

        for box in boxes:

            if box.id is None:
                continue

            x1, y1, x2, y2 = map(int, box.xyxy[0])
            center = ((x1 + x2) // 2, (y1 + y2) // 2)

            track_id = int(box.id[0])
            conf = float(box.conf[0])

            print(f"ID={track_id}, Conf={conf:.2f}")

            plate = get_or_assign_plate(track_id)

            # ==========================
            # 일반 차량: 탐지만 하고 화면엔 아무것도 표시하지 않는다
            # ==========================
            if plate not in wanted_db:
                continue

            # ==========================
            # 관심 차량: 여기서부터만 추적 상태 갱신 + 화면 표시
            # ==========================
            seen_wanted_this_frame.add(track_id)
            last_boxes[track_id] = (x1, y1, x2, y2)
            last_seen[track_id] = frame_count

            update_kalman_filter(track_id, center[0], center[1])

            track_history.setdefault(track_id, []).append(center)

            # 최근 15개 좌표만 유지
            if len(track_history[track_id]) > 15:
                track_history[track_id].pop(0)

            draw_trajectory(annotated_frame, track_history[track_id])
            draw_wanted_box(annotated_frame, (x1, y1, x2, y2), track_id, plate, plate_draw_jobs)

    # ==========================
    # 박스 유지 기능 (관심 차량만 적용):
    # 이번 프레임엔 안 보였지만
    # 최근 HOLD_FRAMES 프레임 안에는 보였던 관심 차량을 마지막 상태로 계속 그림
    # ==========================
    for track_id in list(last_boxes.keys()):

        if track_id in seen_wanted_this_frame:
            continue

        if frame_count - last_seen[track_id] <= HOLD_FRAMES:

            plate = track_to_plate[track_id]

            # 마지막 박스 크기는 유지한 채, 위치만 Kalman Filter로 예측
            x1, y1, x2, y2 = last_boxes[track_id]
            box_size = (x2 - x1, y2 - y1)

            predicted_coords = predict_box_from_kalman(track_id, box_size)
            coords = predicted_coords if predicted_coords is not None else last_boxes[track_id]

            # 예측된 위치도 궤적에 반영해야 이동 경로가 자연스럽게 이어짐
            predicted_center = ((coords[0] + coords[2]) // 2, (coords[1] + coords[3]) // 2)
            track_history.setdefault(track_id, []).append(predicted_center)

            if len(track_history[track_id]) > 15:
                track_history[track_id].pop(0)

            draw_trajectory(annotated_frame, track_history[track_id])
            draw_wanted_box(annotated_frame, coords, track_id, plate, plate_draw_jobs)

    # ==========================
    # 번호판 텍스트 한 번에 그리기 (PIL 변환은 프레임당 1회만)
    # ==========================
    if plate_draw_jobs:

        pil_image = Image.fromarray(cv2.cvtColor(annotated_frame, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(pil_image)

        for x1, y1, plate in plate_draw_jobs:
            draw.text((x1, y1 + 15), plate, font=font, fill=(255, 255, 0))

        annotated_frame = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)

    # ==========================
    # 오래된 관심 차량 추적 정보 정리 (메모리 관리)
    # ==========================
    stale_ids = [
        track_id for track_id in list(last_seen.keys())
        if frame_count - last_seen[track_id] > STALE_FRAMES
    ]

    for track_id in stale_ids:
        last_boxes.pop(track_id, None)
        last_seen.pop(track_id, None)
        track_history.pop(track_id, None)
        kalman_filters.pop(track_id, None)
        # track_to_plate은 남겨둠: 같은 차량이 다시 나타나면 같은 번호판 유지

    # 저장
    out.write(annotated_frame)

    # 화면 출력
    cv2.imshow("Smart CCTV", annotated_frame)

    # ESC 종료
    if cv2.waitKey(1) == 27:
        break

cap.release()
out.release()
cv2.destroyAllWindows()

print("차량 추적 완료!")