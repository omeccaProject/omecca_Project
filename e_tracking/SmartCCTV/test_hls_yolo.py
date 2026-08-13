from ultralytics import YOLO
import cv2
import time

# ==========================
# 설정
# ==========================

HLS_URL = "https://strm1.spatic.go.kr/live/76.stream/chunklist_w1824089310.m3u8"

# 내장그래픽이므로 가벼운 모델 사용
model = YOLO("yolo11s.pt")

# 차량 클래스
# 2 = car
# 3 = motorcycle
# 5 = bus
# 7 = truck
VEHICLE_CLASSES = [2, 3, 5, 7]

# AI 분석용 이미지 크기
IMG_SIZE = 416

# AI 분석 간격
# 1 = 모든 프레임
# 2 = 한 프레임 건너뜀
PROCESS_EVERY = 2


# ==========================
# HLS 연결
# ==========================

cap = cv2.VideoCapture(HLS_URL)

if not cap.isOpened():
    print("❌ HLS 연결 실패")
    exit()

print("✅ 이수역 CCTV 연결 성공")
print("🚗 YOLO + ByteTrack 시작")
print("ESC = 종료")


# ==========================
# 상태
# ==========================

frame_count = 0

last_result = None

prev_time = time.time()
fps = 0


# ==========================
# 실시간 처리
# ==========================

while True:

    ret, frame = cap.read()

    if not ret:
        print("⚠️ 프레임 수신 실패")
        time.sleep(0.05)
        continue

    frame_count += 1

    # --------------------------------
    # AI 분석 프레임
    # --------------------------------

    if frame_count % PROCESS_EVERY == 0:

        results = model.track(
            frame,
            tracker="bytetrack.yaml",
            classes=VEHICLE_CLASSES,
            conf=0.30,
            persist=True,
            verbose=False,
            imgsz=IMG_SIZE
        )

        last_result = results[0]

    # --------------------------------
    # 화면
    # --------------------------------

    annotated_frame = frame.copy()

    if last_result is not None:

        boxes = last_result.boxes

        if boxes is not None:

            for box in boxes:

                # Track ID 없는 객체 제외
                if box.id is None:
                    continue

                x1, y1, x2, y2 = map(
                    int,
                    box.xyxy[0]
                )

                track_id = int(box.id[0])

                confidence = float(box.conf[0])

                # 차량 박스
                cv2.rectangle(
                    annotated_frame,
                    (x1, y1),
                    (x2, y2),
                    (0, 255, 0),
                    2
                )

                # 차량 ID
                cv2.putText(
                    annotated_frame,
                    f"Vehicle #{track_id}",
                    (x1, max(y1 - 10, 20)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    (0, 255, 0),
                    2
                )

    # --------------------------------
    # FPS 표시
    # --------------------------------

    current_time = time.time()

    elapsed = current_time - prev_time

    if elapsed >= 1.0:

        fps = frame_count / elapsed

        frame_count = 0
        prev_time = current_time

    cv2.putText(
        annotated_frame,
        f"AI FPS: {fps:.1f}",
        (20, 35),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (0, 255, 255),
        2
    )

    # --------------------------------
    # 화면 출력
    # --------------------------------

    cv2.imshow(
        "UTIC L010263 - AI Vehicle Tracking",
        annotated_frame
    )

    # ESC 종료
    if cv2.waitKey(1) & 0xFF == 27:
        break


# ==========================
# 종료
# ==========================

cap.release()
cv2.destroyAllWindows()

print("차량 추적 종료")