from ultralytics import YOLO
import cv2
import time

# ==========================
# 설정
# ==========================

HLS_URL = "https://strm1.spatic.go.kr/live/76.stream/chunklist_w1824089310.m3u8"

# YOLO11s
model = YOLO("yolo11s.pt")

# 차량 클래스
# 2 = car
# 3 = motorcycle
# 5 = bus
# 7 = truck
VEHICLE_CLASSES = [2, 3, 5, 7]

# AI 분석 이미지 크기
IMG_SIZE = 410

# 검출 신뢰도
CONF = 0.30

# ==========================
# HLS 연결
# ==========================

cap = cv2.VideoCapture(HLS_URL)

if not cap.isOpened():
    print("❌ HLS 연결 실패")
    exit()

print("✅ 이수역 CCTV 연결 성공")
print("🚗 YOLO Detection Only 시작")
print("⚠️ ByteTrack 사용 안 함")
print("ESC = 종료")

# ==========================
# 상태
# ==========================

frame_count = 0

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

    # ==========================
    # YOLO Detection
    # ==========================

    results = model.predict(
        frame,
        classes=VEHICLE_CLASSES,
        conf=CONF,
        imgsz=IMG_SIZE,
        verbose=False
    )

    result = results[0]

    annotated_frame = frame.copy()

    # 현재 프레임의 검출 차량 수
    detection_count = 0

    if result.boxes is not None:

        for box in result.boxes:

            detection_count += 1

            # Bounding Box
            x1, y1, x2, y2 = map(
                int,
                box.xyxy[0]
            )

            # Confidence
            confidence = float(box.conf[0])

            # 클래스
            class_id = int(box.cls[0])

            # ==========================
            # 차량 박스
            # ==========================

            cv2.rectangle(
                annotated_frame,
                (x1, y1),
                (x2, y2),
                (0, 255, 0),
                2
            )

            # ==========================
            # 차량 정보
            # ==========================

            cv2.putText(
                annotated_frame,
                f"Vehicle {confidence:.2f}",
                (x1, max(y1 - 10, 20)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (0, 255, 0),
                2
            )

    # ==========================
    # 검출 객체 수 출력
    # ==========================

    print(
        f"검출 객체 수: {detection_count}"
    )

    # ==========================
    # FPS
    # ==========================

    current_time = time.time()

    elapsed = current_time - prev_time

    if elapsed >= 1.0:

        fps = frame_count / elapsed

        frame_count = 0
        prev_time = current_time

    cv2.putText(
        annotated_frame,
        f"YOLO FPS: {fps:.1f}",
        (20, 35),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (0, 255, 255),
        2
    )

    # ==========================
    # 검출 차량 수 화면 표시
    # ==========================

    cv2.putText(
        annotated_frame,
        f"Vehicles: {detection_count}",
        (20, 70),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (0, 255, 255),
        2
    )

    # ==========================
    # 화면 출력
    # ==========================

    cv2.imshow(
        "UTIC L010263 - YOLO Detection Only",
        annotated_frame
    )

    # ESC
    if cv2.waitKey(1) & 0xFF == 27:
        break


# ==========================
# 종료
# ==========================

cap.release()
cv2.destroyAllWindows()

print("YOLO Detection 종료")