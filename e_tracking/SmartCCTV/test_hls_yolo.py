from ultralytics import YOLO
import cv2
import time
import torch


# ============================================================
# 설정
# ============================================================

HLS_URL = "https://strm1.spatic.go.kr/live/76.stream/chunklist_w1824089310.m3u8"

MODEL_PATH = "yolo11s.pt"

# 차량 클래스
# 2 = car
# 3 = motorcycle
# 5 = bus
# 7 = truck
VEHICLE_CLASSES = [2, 3, 5, 7]

# YOLO 입력 크기
# 640은 FPS가 크게 떨어졌으므로 416 사용
IMG_SIZE = 416

# 모든 프레임 분석
PROCESS_EVERY = 1

# 검출 confidence
CONF = 0.30


# ============================================================
# GPU 설정
# ============================================================

if not torch.cuda.is_available():
    print("❌ CUDA GPU를 사용할 수 없습니다.")
    print("현재 CPU로 실행하면 이 테스트의 목적과 다르므로 종료합니다.")
    exit()

DEVICE = 0

print("=" * 50)
print("GPU 사용")
print("GPU :", torch.cuda.get_device_name(0))
print("CUDA:", torch.version.cuda)
print("=" * 50)


# ============================================================
# YOLO 모델
# ============================================================

model = YOLO(MODEL_PATH)

# 모델을 GPU로 이동
model.to(DEVICE)

print("✅ YOLO11s 모델 로드 완료")
print(f"📐 IMG_SIZE : {IMG_SIZE}")
print(f"🎯 CONF     : {CONF}")
print(f"⚡ DEVICE   : CUDA:{DEVICE}")


# ============================================================
# HLS 연결
# ============================================================

cap = cv2.VideoCapture(HLS_URL)

if not cap.isOpened():
    print("❌ HLS 연결 실패")
    exit()

print()
print("✅ 이수역 CCTV 연결 성공")
print("🚗 YOLO11s + ByteTrack 시작")
print("ESC = 종료")
print()


# ============================================================
# 상태 변수
# ============================================================

frame_count = 0

# 마지막 YOLO 결과
last_result = None

# FPS 계산
fps = 0.0
prev_time = time.time()
fps_frame_count = 0

# YOLO 추론 시간
inference_ms = 0.0


# ============================================================
# 실시간 처리
# ============================================================

while True:

    ret, frame = cap.read()

    if not ret:
        print("⚠️ 프레임 수신 실패")
        time.sleep(0.05)
        continue

    frame_count += 1
    fps_frame_count += 1


    # ========================================================
    # YOLO + ByteTrack
    # ========================================================

    if frame_count % PROCESS_EVERY == 0:

        start_inference = time.perf_counter()

        results = model.track(
            frame,

            # ByteTrack
            tracker="bytetrack.yaml",

            # 차량만 검출
            classes=VEHICLE_CLASSES,

            # confidence
            conf=CONF,

            # 이전 프레임의 Track 유지
            persist=True,

            # YOLO 입력 크기
            imgsz=IMG_SIZE,

            # GPU 사용
            device=DEVICE,

            verbose=False
        )

        end_inference = time.perf_counter()

        inference_ms = (end_inference - start_inference) * 1000

        last_result = results[0]


    # ========================================================
    # 화면 생성
    # ========================================================

    annotated_frame = frame.copy()

    current_ids = []


    if last_result is not None:

        boxes = last_result.boxes

        if boxes is not None:

            for box in boxes:

                # Track ID가 없는 객체는 제외
                if box.id is None:
                    continue


                # ------------------------------------------------
                # Track ID
                # ------------------------------------------------

                track_id = int(box.id[0])

                current_ids.append(track_id)


                # ------------------------------------------------
                # Bounding Box
                # ------------------------------------------------

                x1, y1, x2, y2 = map(
                    int,
                    box.xyxy[0]
                )


                # ------------------------------------------------
                # Confidence
                # ------------------------------------------------

                confidence = float(box.conf[0])


                # ------------------------------------------------
                # 차량 Bounding Box
                # ------------------------------------------------

                cv2.rectangle(
                    annotated_frame,
                    (x1, y1),
                    (x2, y2),
                    (0, 255, 0),
                    2
                )


                # ------------------------------------------------
                # 차량 ID
                # ------------------------------------------------

                label = f"Vehicle #{track_id}"

                cv2.putText(
                    annotated_frame,
                    label,
                    (x1, max(y1 - 10, 20)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    (0, 255, 0),
                    2
                )


    # ========================================================
    # 현재 Track ID 출력
    # ========================================================

    print(
        f"현재 ID: {sorted(current_ids)}"
    )


    # ========================================================
    # FPS 계산
    # ========================================================

    current_time = time.time()

    elapsed = current_time - prev_time

    if elapsed >= 1.0:

        fps = fps_frame_count / elapsed

        fps_frame_count = 0
        prev_time = current_time


    # ========================================================
    # 화면 정보
    # ========================================================

    cv2.putText(
        annotated_frame,
        f"AI FPS: {fps:.1f}",
        (20, 35),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (0, 255, 255),
        2
    )


    cv2.putText(
        annotated_frame,
        f"YOLO: {inference_ms:.1f} ms",
        (20, 65),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        (0, 255, 255),
        2
    )


    cv2.putText(
        annotated_frame,
        f"GPU: {torch.cuda.get_device_name(0)}",
        (20, 95),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (0, 255, 255),
        2
    )


    # ========================================================
    # 화면 출력
    # ========================================================

    cv2.imshow(
        "UTIC L010263 - YOLO11s GPU Vehicle Tracking",
        annotated_frame
    )


    # ========================================================
    # ESC 종료
    # ========================================================

    if cv2.waitKey(1) & 0xFF == 27:
        break


# ============================================================
# 종료
# ============================================================

cap.release()

cv2.destroyAllWindows()

print()
print("🚗 차량 추적 종료")