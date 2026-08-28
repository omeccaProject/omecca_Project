import cv2
import time
import requests
import numpy as np
import torch
from ultralytics import YOLO


# ============================================================
# 1. 기본 설정 (전부 기존 그대로 - YOLO/ByteTrack/Track Coasting 미변경)
# ============================================================

HLS_URL = "https://strm1.spatic.go.kr/live/76.stream/chunklist_w1824089310.m3u8"

MODEL_PATH = "yolo11m.pt"

IMG_SIZE = 416

VEHICLE_CLASSES = [2, 3, 5, 7]

CONF_THRESH = 0.30

# [병합] GitHub 쪽이 "bytetrack.yaml"(기본 설정)으로 되돌려놨었는데, 요구사항 4번에
# 따라 반드시 커스텀 설정(bytetrack_custom.yaml)을 그대로 써야 한다 - 그대로 유지.
TRACKER_CONFIG = "bytetrack_custom.yaml"

# CPU 노트북에서는 "cpu", CUDA가 있는 GPU 컴퓨터에서는 0으로 바꿔서 쓴다.
DEVICE = "cpu"


# ============================================================
# 2. 대시보드(b_gateway) 연결 설정
# ------------------------------------------------------------
# ws://localhost:4000/events(Node)는 e_tracking 자체 Leaflet 지도(map.js)만 듣고
# 있고, React 대시보드(b_dashboard, 5173)는 이 소켓을 한 번도 연결한 적이 없다 -
# 포트가 아예 다르다(대시보드는 오직 b_gateway:8080의 STOMP 소켓 /ws만 연결한다).
# 그래서 대시보드가 "이미 연결해 둔" b_gateway(8080)로 직접 보내고, 거기에 추가한
# /api/cctv/detections → /topic/cctv/detections 채널을 태운다.
# (b_gateway/CctvDetectionController.java 참고 - DB 저장 없는 순수 방송 전용)
#
# 차량 하나당 POST를 한 번씩 날리면(예: 6대 x 30fps = 초당 180회 연결) 매우
# 비효율적이므로, 한 프레임의 전체 검출 결과를 배치로 묶어서 프레임당 딱 1번만 보낸다.
# ============================================================

GATEWAY_URL = "http://localhost:8080/api/cctv/detections"
GATEWAY_API_KEY = "omecca-dev-key-2026"  # b_gateway .env의 GATEWAY_API_KEY와 반드시 동일해야 함

# [중요] "카메라 관리"에 이수역을 등록할 때 입력한 camId와 반드시 똑같아야 한다.
# 대시보드 브라우저 개발자도구(F12) → Network → GET /api/cameras 응답에서 확인한
# 실제 등록 camId(L010263, UTIC 원본 cam_id와 동일)로 이미 맞춰져 있다.
CCTV_ID = "L010263"

# 연결을 재사용하는 세션 - 매 프레임마다 새 TCP 연결을 맺지 않아 훨씬 가볍다.
_session = requests.Session()
_session.headers.update({"X-API-Key": GATEWAY_API_KEY})

REQUEST_TIMEOUT_SEC = 0.8  # 프레임당 1번뿐이라 예전(0.3초, 차량당 1번)보다 여유 있게 잡아도 부담 없음


def send_frame_detections(cam_id, frame_width, frame_height, tracked_objects):
    """
    이 프레임에서 검출/코스팅된 전체 차량 목록을 한 번에 b_gateway로 보낸다.
    실패해도(게이트웨이 미기동 등) YOLO/화면 표시에는 전혀 영향 없다 - 콘솔에만 남긴다.

    [주의] 전송 JSON 스키마(camId/frameWidth/frameHeight/detections[].trackId/bbox)는
    b_gateway의 CctvDetectionController.DetectionBatch와 정확히 일치해야 하므로
    그대로 유지한다 - confidence는 내부적으로만 활용하고(아래 TrackCoaster 참고)
    이 전송 payload에는 포함시키지 않는다(기존 계약 변경 금지).
    """
    detections = []
    for track_id, info in tracked_objects.items():
        x1, y1, x2, y2 = info["bbox"]
        detections.append({
            "trackId": int(track_id),
            "bbox": {
                "x1": float(x1),
                "y1": float(y1),
                "x2": float(x2),
                "y2": float(y2),
            },
        })

    payload = {
        "camId": cam_id,
        "frameWidth": int(frame_width),
        "frameHeight": int(frame_height),
        "detections": detections,
    }

    try:
        response = _session.post(GATEWAY_URL, json=payload, timeout=REQUEST_TIMEOUT_SEC)
        if not response.ok:
            print(f"[AI EVENT 전송 실패] HTTP={response.status_code} body={response.text[:200]}")
        # 성공 로그는 매 프레임 찍으면 콘솔이 도배되므로 생략한다 - 실패했을 때만 남긴다.
    except requests.exceptions.RequestException as e:
        print(f"[AI EVENT 네트워크 오류] {e}")
    except Exception as e:
        print(f"[AI EVENT 오류] {e}")


# ============================================================
# 3. Track Coasting 설정 (기존 그대로)
# ============================================================

COAST_MAX_FRAMES = 8
SHOW_COASTED_IN_YELLOW = False


# ============================================================
# 4. Track Coaster (기존 그대로 - 로직 미변경)
# ------------------------------------------------------------
# [병합] GitHub 쪽에서 새로 추가된 "detection별 confidence 캡처" 기능을 살리기
# 위해, update()가 bbox 하나만이 아니라 (bbox, confidence) 튜플도 받을 수 있게
# 확장했다 - 기존처럼 bbox만 넘겨도(하위 호환) 그대로 동작한다(confidence는 None).
# 코스팅(예측) 중인 프레임은 confidence를 알 수 없으므로 마지막 실측값을 그대로
# 들고 있는다.
# ============================================================

class TrackCoaster:

    def __init__(self, max_frames=8):
        self.max_frames = max_frames
        self.tracks = {}

    def update(self, detections):

        current_ids = set()

        for track_id, value in detections.items():

            track_id = int(track_id)
            current_ids.add(track_id)

            # (bbox, confidence) 튜플이면 분리하고, bbox만 왔으면 confidence는 None.
            if isinstance(value, tuple) and len(value) == 2:
                bbox, confidence = value
            else:
                bbox, confidence = value, None

            bbox = np.array(bbox, dtype=np.float32)

            if track_id in self.tracks:
                old_bbox = self.tracks[track_id]["bbox"]
                old_center = np.array([(old_bbox[0] + old_bbox[2]) / 2, (old_bbox[1] + old_bbox[3]) / 2])
                new_center = np.array([(bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2])
                velocity = new_center - old_center
                self.tracks[track_id]["velocity"] = velocity
            else:
                self.tracks[track_id] = {
                    "bbox": bbox,
                    "velocity": np.array([0.0, 0.0]),
                    "missed": 0,
                }

            self.tracks[track_id]["bbox"] = bbox
            self.tracks[track_id]["missed"] = 0
            self.tracks[track_id]["coasted"] = False
            if confidence is not None:
                self.tracks[track_id]["confidence"] = confidence

        for track_id in list(self.tracks.keys()):

            if track_id in current_ids:
                continue

            info = self.tracks[track_id]
            info["missed"] += 1

            if info["missed"] <= self.max_frames:
                bbox = info["bbox"].copy()
                velocity = info["velocity"]
                bbox[0] += velocity[0]
                bbox[2] += velocity[0]
                bbox[1] += velocity[1]
                bbox[3] += velocity[1]
                info["bbox"] = bbox
                info["coasted"] = True
                # confidence는 실측이 아니므로 마지막 값을 그대로 들고 있는다(갱신 안 함).
            else:
                del self.tracks[track_id]

        return self.tracks


# ============================================================
# 5. YOLO 모델 로드 (기존 그대로)
# ============================================================

print("YOLO 모델 로딩 중...")
model = YOLO(MODEL_PATH)
print("YOLO 모델 로딩 완료")
print(f"Device: {DEVICE}")


# ============================================================
# 6. CCTV 연결 (기존 그대로)
# ============================================================

cap = cv2.VideoCapture(HLS_URL)

if not cap.isOpened():
    print("❌ CCTV 연결 실패")
    raise SystemExit

print()
print("✅ 이수역 CCTV 연결 성공")
print("🚗 YOLO + ByteTrack + Track Coasting 시작")
print(f"📡 대시보드 전송: {GATEWAY_URL} (camId={CCTV_ID})")
print("ESC = 종료")
print()


# ============================================================
# 7. Track Coaster 생성 (기존 그대로)
# ============================================================

coaster = TrackCoaster(max_frames=COAST_MAX_FRAMES)


# ============================================================
# 8. FPS 측정 (기존 그대로 + GitHub이 추가한 정밀 추론시간 측정 병합)
# ============================================================

fps = 0.0
prev_time = time.time()
inference_time_accum = 0.0
inference_count = 0
inference_ms = 0.0  # 이번 프레임 1건의 순수 추론 소요시간(ms) - 화면 표시용(GitHub 추가분)


# ============================================================
# 9. 메인 루프
# ============================================================

while True:

    ret, frame = cap.read()

    if not ret:
        print("⚠️ CCTV 프레임 수신 실패")
        time.sleep(0.1)
        continue

    frame_height, frame_width = frame.shape[:2]  # 실제 원본 프레임 크기 - 대시보드 스케일링에 사용됨

    # --------------------------------------------------------
    # YOLO + ByteTrack
    # --------------------------------------------------------
    # [병합] GitHub이 추가한 time.perf_counter() 기반 "이번 프레임 1건"의 정밀
    # 추론시간 측정(inference_ms, 화면 표시용)과, 기존(stash)의 누적 평균 진단
    # (inference_time_accum, 콘솔 로그용) 둘 다 유지한다 - 서로 다른 용도라 병행 가능.
    # --------------------------------------------------------

    start_inference = time.perf_counter()

    results = model.track(
        frame,
        tracker=TRACKER_CONFIG,
        classes=VEHICLE_CLASSES,
        conf=CONF_THRESH,
        persist=True,
        verbose=False,
        imgsz=IMG_SIZE,
        device=DEVICE,
    )

    end_inference = time.perf_counter()
    inference_ms = (end_inference - start_inference) * 1000
    inference_time_accum += (end_inference - start_inference)
    inference_count += 1

    last_result = results[0]

    # --------------------------------------------------------
    # 검출 결과 저장
    # ------------------------------------------------------
    # [병합] GitHub이 추가한 confidence 추출을 같이 담는다 - bbox와 함께
    # (bbox, confidence) 튜플로 저장해서 TrackCoaster가 내부적으로 들고 있게 한다
    # (b_gateway 전송 스키마는 변경하지 않음 - send_frame_detections 주석 참고).
    # --------------------------------------------------------

    detections = {}

    if last_result.boxes is not None and last_result.boxes.id is not None:
        boxes = last_result.boxes.xyxy.cpu().numpy()
        track_ids = last_result.boxes.id.cpu().numpy().astype(int)
        confidences = last_result.boxes.conf.cpu().numpy()
        for track_id, bbox, confidence in zip(track_ids, boxes, confidences):
            detections[int(track_id)] = (bbox, float(confidence))

    # --------------------------------------------------------
    # Track Coasting 적용 (기존 그대로)
    # --------------------------------------------------------

    tracked_objects = coaster.update(detections)

    current_ids = sorted(tracked_objects.keys())
    print(f"현재 ID: {current_ids}")

    # --------------------------------------------------------
    # 차량 이벤트를 b_gateway로 "프레임당 1회, 배치로" 전송
    # --------------------------------------------------------

    send_frame_detections(CCTV_ID, frame_width, frame_height, tracked_objects)

    # --------------------------------------------------------
    # 화면 표시 (Track Coasting 결과 기준 - 기존 그대로)
    # --------------------------------------------------------

    annotated_frame = frame.copy()

    for track_id, info in tracked_objects.items():
        bbox = info["bbox"]
        is_coasted = info["coasted"]
        x1, y1, x2, y2 = map(int, bbox)

        color = (0, 255, 255) if (is_coasted and SHOW_COASTED_IN_YELLOW) else (0, 255, 0)

        cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), color, 2)

        label = f"Vehicle #{track_id}"
        cv2.putText(annotated_frame, label, (x1, max(y1 - 10, 20)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

    # --------------------------------------------------------
    # FPS 계산 (기존 그대로)
    # --------------------------------------------------------

    current_time = time.time()
    elapsed = current_time - prev_time
    if elapsed > 0:
        fps = 1.0 / elapsed
    prev_time = current_time

    cv2.putText(annotated_frame, f"AI FPS: {fps:.1f}", (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)

    # [병합] GitHub이 추가한 "이번 프레임 순수 추론시간(ms)" 화면 표시.
    cv2.putText(annotated_frame, f"YOLO: {inference_ms:.1f} ms", (20, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 255), 2)

    # [병합] GitHub이 추가한 GPU 이름 표시 - 단, CUDA가 없는 CPU 환경(지금 이 노트북)에서
    # torch.cuda.get_device_name(0)을 그대로 호출하면 매 프레임 예외가 나서 즉시 크래시한다.
    # DEVICE="cpu"로 실행 가능해야 한다는 요구사항 때문에, 실제로 CUDA를 쓰는 경우에만
    # 표시하고 CPU에서는 "CPU"로 대체 표시한다 - GPU 컴퓨터에서 DEVICE=0으로 바꾸면
    # 그대로 GPU 이름이 표시된다(코드 추가 수정 불필요).
    if DEVICE != "cpu" and torch.cuda.is_available():
        gpu_label = torch.cuda.get_device_name(0)
    else:
        gpu_label = "CPU"
    cv2.putText(annotated_frame, f"Device: {gpu_label}", (20, 95), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 2)

    if inference_count > 0 and inference_count % 5 == 0:
        avg_ms = (inference_time_accum / inference_count) * 1000
        print(f"[진단] 전체 FPS={fps:.1f} | 순수 추론 평균={avg_ms:.1f}ms/frame ({inference_count}회)")
        inference_time_accum = 0
        inference_count = 0

    cv2.imshow("Smart CCTV - YOLO + ByteTrack", annotated_frame)

    key = cv2.waitKey(1) & 0xFF
    if key == 27:
        break


# ============================================================
# 종료 (기존 그대로)
# ============================================================

cap.release()
cv2.destroyAllWindows()

print()
print("🚗 차량 추적 종료 (YOLO Detection 종료)")