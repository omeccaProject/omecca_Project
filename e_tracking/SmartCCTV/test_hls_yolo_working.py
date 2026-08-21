"""
실시간 CCTV 차량 검출/추적 - Track Coasting(A+B) 버전
------------------------------------------------------------
기존 구조를 그대로 유지하면서 딱 하나만 추가했습니다: TrackCoaster.

문제 진단:
  - Detection-only 테스트에서도 움직이는 차량 박스가 깜빡였다는 것은,
    ByteTrack association 문제가 아니라 "움직이는 차량의 YOLO confidence가
    프레임마다 0.30 threshold 근처에서 출렁이는 문제"라는 뜻입니다.
  - model.track(persist=True)가 반환하는 boxes는 "이번 프레임에 실제로 매칭된
    track"만 포함합니다. ByteTrack이 내부적으로 track_buffer 프레임 동안
    Kalman 상태를 들고 있으면서 "ID 재연결"은 해주지만, 그 사이 화면에 그릴
    좌표를 API로 내주지는 않습니다 - 그래서 track_buffer를 아무리 올려도
    "박스가 사라지는 것" 자체는 해결되지 않았던 것입니다.
  - 따라서 이 문제는 YOLO/ByteTrack 설정이 아니라, 애플리케이션(이 스크립트)
    레이어에서 "검출이 잠깐 끊긴 track_id의 마지막 위치+속도로 다음 위치를
    예측해서 화면에 계속 그려주는" 방식으로 풀어야 합니다 (Option A+B).

바뀐 것:
  - TrackCoaster 클래스 추가 (약 50줄)
  - 메인 루프에서 boxes를 그대로 순회하며 그리던 부분을,
    "이번 프레임 실제 검출" -> coaster.update() -> "화면에 그릴 전체 목록"
    으로 한 단계 거치도록 변경
  - 기존 EMA smoothing(smooth_boxes)은 그대로 유지하고, 그 위에 적용됨
  - HLS 연결 방식, YOLO 모델/설정, ByteTrack 설정, IMG_SIZE, 차량 클래스는
    전부 그대로입니다.

디버그용: COAST 중인(예측으로 유지 중인) 박스는 노란색으로 표시됩니다.
1단계 테스트가 끝나고 정상 확인되면 SHOW_COASTED_IN_YELLOW = False로 바꿔서
평소처럼 전부 초록색으로 보이게 하면 됩니다.

[참고] 두 문서에서 모델이 서로 다르게 적혀 있었습니다 - 요구사항 설명에는
"YOLO11s / yolo11s.pt", 실제 첨부하신 현재 코드에는 "yolo11m.pt"가 쓰여
있었습니다. 실제 첨부 코드 기준(yolo11m.pt)으로 그대로 유지했습니다 - 만약
실제로 s 모델을 쓰고 계신 거라면 MODEL_PATH 한 줄만 바꾸시면 됩니다.
"""

from ultralytics import YOLO
import cv2
import time

# ==========================
# 설정 (기존 값 그대로)
# ==========================

HLS_URL = "https://strm1.spatic.go.kr/live/76.stream/chunklist_w1824089310.m3u8"

MODEL_PATH = "yolo11m.pt"  # 첨부하신 실제 코드 기준. yolo11s.pt를 쓰고 계셨다면 이 줄만 바꾸세요.
model = YOLO(MODEL_PATH)

# 차량 클래스: 2=car, 3=motorcycle, 5=bus, 7=truck
VEHICLE_CLASSES = [2, 3, 5, 7]

IMG_SIZE = 416
PROCESS_EVERY = 1
CONF_THRESH = 0.30

# ==========================
# [신규] Track Coasting 설정
# ==========================

# 검출이 끊겨도 이 프레임 수까지는 "마지막 속도로 예측한 위치"로 박스를 유지합니다.
# 30FPS 기준 8프레임 ≈ 267ms. 너무 크게 잡으면 실제로 화면을 빠져나간 차량 박스가
# 계속 남아있는 것처럼 보이니, 1단계 테스트에서 로그를 보고 조정하세요(아래 3번 참고).
COAST_MAX_FRAMES = 8

# 프레임 간 속도 추정치 자체에도 살짝 EMA를 걸어서, 위치 노이즈가 속도 추정에
# 그대로 튀는 것을 줄입니다. 1.0이면 EMA 없음(매 프레임 속도를 그대로 신뢰),
# 낮출수록 속도가 더 부드럽게(하지만 방향 전환에는 더 느리게) 반응합니다.
VELOCITY_SMOOTHING = 0.5

# 1단계 검증용 - 예측(coast)으로 유지 중인 박스를 노란색으로 구분 표시합니다.
# 정상 동작 확인되면 False로 바꿔서 평소처럼 전부 초록색으로 표시하세요.
SHOW_COASTED_IN_YELLOW = True

# 코스팅→재검출 전환이 일어날 때마다 "몇 프레임 놓쳤었는지" 콘솔에 남깁니다.
# 이 숫자들을 보고 COAST_MAX_FRAMES가 충분한지 판단하면 됩니다 (진단 3번 참고).
LOG_COAST_RECOVERY = True


class TrackCoaster:
    """
    ByteTrack이 이번 프레임에 특정 track_id를 놓쳤을 때(=box.id가 없거나
    이번 프레임 boxes에 그 id가 없을 때), 마지막으로 알려진 위치 + 추정 속도로
    다음 위치를 예측해서 최대 COAST_MAX_FRAMES 프레임까지 박스를 계속 표시한다.
    그 이상 놓치면 실제로 화면을 벗어났거나 완전히 놓친 것으로 보고 지운다.

    이 클래스는 YOLO/ByteTrack 내부를 전혀 건드리지 않는다 - model.track()의
    출력을 "화면에 그릴 좌표 목록"으로 한 번 더 가공하는 순수 후처리 레이어다.
    """

    def __init__(self, coast_max_frames=8, velocity_smoothing=0.5, log_recovery=True):
        self.coast_max_frames = coast_max_frames
        self.velocity_smoothing = velocity_smoothing
        self.log_recovery = log_recovery
        self.tracks = {}  # track_id -> {"bbox": (x1,y1,x2,y2), "velocity": (vx,vy), "missed": int}

    def update(self, current_ids_boxes):
        """
        current_ids_boxes: { track_id: (x1,y1,x2,y2) } - 이번 프레임에 실제로 검출된 것만.

        반환값: { track_id: {"bbox": (x1,y1,x2,y2), "coasted": bool} }
                실제 검출 + 아직 coast 유효기간 안인 놓친 track을 합친, 화면에 그릴 전체 목록.
        """
        output = {}

        # ---- 1) 실제로 검출된 track: 위치/속도 갱신 ----
        for tid, bbox in current_ids_boxes.items():
            prev = self.tracks.get(tid)

            if prev is not None:
                px1, py1, px2, py2 = prev["bbox"]
                cx_prev, cy_prev = (px1 + px2) / 2, (py1 + py2) / 2
                cx_new, cy_new = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
                vx, vy = cx_new - cx_prev, cy_new - cy_prev

                if "velocity" in prev:
                    a = self.velocity_smoothing
                    vx = a * vx + (1 - a) * prev["velocity"][0]
                    vy = a * vy + (1 - a) * prev["velocity"][1]

                if self.log_recovery and prev.get("missed", 0) > 0:
                    print(f"[COAST] track {tid} 재검출됨 ({prev['missed']}프레임 예측으로 유지했음)")
            else:
                vx, vy = 0.0, 0.0

            self.tracks[tid] = {"bbox": bbox, "velocity": (vx, vy), "missed": 0}
            output[tid] = {"bbox": bbox, "coasted": False}

        # ---- 2) 이번 프레임에 못 잡힌(놓친) track: 예측 위치로 coast ----
        missing_ids = set(self.tracks.keys()) - set(current_ids_boxes.keys())
        for tid in list(missing_ids):
            t = self.tracks[tid]
            t["missed"] += 1

            if t["missed"] > self.coast_max_frames:
                del self.tracks[tid]  # coast 유효기간 초과 - 완전히 제거 (실제로 나갔다고 판단)
                continue

            x1, y1, x2, y2 = t["bbox"]
            vx, vy = t["velocity"]
            w, h = x2 - x1, y2 - y1
            cx, cy = (x1 + x2) / 2 + vx, (y1 + y2) / 2 + vy
            new_bbox = (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)

            t["bbox"] = new_bbox  # 다음 프레임도 이어서 이 위치를 기준으로 예측(속도 유지)
            output[tid] = {"bbox": new_bbox, "coasted": True}

        return output

    def active_ids(self):
        return set(self.tracks.keys())


# ==========================
# HLS 연결 (기존 그대로)
# ==========================

cap = cv2.VideoCapture(HLS_URL)

if not cap.isOpened():
    print("❌ HLS 연결 실패")
    exit()

print("✅ 이수역 CCTV 연결 성공")
print("🚗 YOLO + ByteTrack + Track Coasting 시작")
print("ESC = 종료")

# ==========================
# 상태
# ==========================

frame_count = 0
last_result = None

smooth_boxes = {}  # 기존 EMA smoothing 그대로 유지 (track_id -> (x1,y1,x2,y2))
coaster = TrackCoaster(COAST_MAX_FRAMES, VELOCITY_SMOOTHING, LOG_COAST_RECOVERY)

prev_time = time.time()
fps = 0

# [신규 - 진단용] 순수 추론시간과 전체 루프 시간을 분리 측정 (우선순위 J)
# 콘솔에 1초마다 같이 찍혀서, "AI FPS"가 실제로 추론 때문에 낮은 건지
# 캡처/디스플레이 오버헤드 때문인지 구분할 수 있다.
inference_time_accum = 0.0
inference_count = 0

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
    # AI 분석 (기존 설정 그대로)
    # --------------------------------

    if frame_count % PROCESS_EVERY == 0:

        t_infer_start = time.time()

        results = model.track(
            frame,
            tracker="bytetrack_custom.yaml",
            classes=VEHICLE_CLASSES,
            conf=CONF_THRESH,
            persist=True,
            verbose=False,
            imgsz=IMG_SIZE
            
        )

        inference_time_accum += time.time() - t_infer_start
        inference_count += 1

        last_result = results[0]

    # --------------------------------
    # 이번 프레임의 실제 검출 결과를 dict로 정리
    # --------------------------------

    current_ids_boxes = {}
    if last_result is not None and last_result.boxes is not None:
        for box in last_result.boxes:
            if box.id is None:
                continue
            track_id = int(box.id[0])
            x1, y1, x2, y2 = map(float, box.xyxy[0])
            current_ids_boxes[track_id] = (x1, y1, x2, y2)

    # --------------------------------
    # [신규] Track Coasting 적용 - 실제 검출 + 예측으로 유지 중인 track 합산
    # --------------------------------

    display_tracks = coaster.update(current_ids_boxes)

    # 더 이상 coaster가 들고 있지 않은 track_id는 smooth_boxes에서도 정리
    # (그대로 두면 메모리에 계속 쌓임 - 매 프레임 비용은 미미하지만 정리해두는 게 안전)
    smooth_boxes = {tid: v for tid, v in smooth_boxes.items() if tid in coaster.active_ids()}

    # --------------------------------
    # 화면
    # --------------------------------

    annotated_frame = frame.copy()
    current_ids = set()

    for track_id, info in display_tracks.items():

        current_ids.add(track_id)
        x1, y1, x2, y2 = map(int, info["bbox"])

        # ---- 기존 Bounding Box Smoothing 그대로 적용 (실제/예측 좌표 모두에) ----
        if track_id in smooth_boxes:
            prev_x1, prev_y1, prev_x2, prev_y2 = smooth_boxes[track_id]
            alpha = 0.6
            x1 = int(alpha * x1 + (1 - alpha) * prev_x1)
            y1 = int(alpha * y1 + (1 - alpha) * prev_y1)
            x2 = int(alpha * x2 + (1 - alpha) * prev_x2)
            y2 = int(alpha * y2 + (1 - alpha) * prev_y2)

        smooth_boxes[track_id] = (x1, y1, x2, y2)

        # ---- 차량 Bounding Box ----
        is_coasted = info["coasted"]
        color = (0, 255, 0) if (is_coasted and SHOW_COASTED_IN_YELLOW) else (0, 255, 0)

        cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), color, 2)

        label = f"Vehicle #{track_id}"
        

        cv2.putText(
            annotated_frame,
            label,
            (x1, max(y1 - 10, 20)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            color,
            2,
        )

    # --------------------------------
    # 현재 Track ID 출력 (기존 그대로)
    # --------------------------------

    print("현재 ID:", sorted(current_ids))

    # --------------------------------
    # FPS 계산 (기존 그대로 + 순수 추론시간 같이 출력)
    # --------------------------------

    current_time = time.time()
    elapsed = current_time - prev_time

    if elapsed >= 1.0:
        fps = frame_count / elapsed

        if inference_count > 0:
            avg_infer_ms = (inference_time_accum / inference_count) * 1000
            print(f"[진단] 전체 FPS={fps:.1f} | 순수 추론 평균={avg_infer_ms:.1f}ms/frame ({inference_count}회)")

        frame_count = 0
        prev_time = current_time
        inference_time_accum = 0.0
        inference_count = 0

    # --------------------------------
    # FPS 표시
    # --------------------------------

    cv2.putText(
        annotated_frame,
        f"AI FPS: {fps:.1f}",
        (20, 35),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (0, 255, 0),
        2,
    )

    # --------------------------------
    # 화면 출력
    # --------------------------------

    cv2.imshow("UTIC L010263 - AI Vehicle Tracking", annotated_frame)

    if cv2.waitKey(1) & 0xFF == 27:
        break

# ==========================
# 종료
# ==========================

cap.release()
cv2.destroyAllWindows()

print("차량 추적 종료")