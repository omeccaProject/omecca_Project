"""
anomaly_detection.py
==============================================
Trajectory Analysis Module (이상 주행 패턴 탐지)

track.py(Tracking Module)와 완전히 독립된 파일입니다.
track.py를 수정하지 않으며, 이 파일 단독으로 실행됩니다.

목적
----
차량을 "추적"하는 것이 아니라, 차량의 이동 궤적(중심 좌표 이력)을
분석하여 좌우로 흔들리며 주행하는 "이상 주행 패턴(Weaving)"을
규칙 기반(Rule-Based)으로 탐지합니다.

※ 이 모듈은 음주운전 여부를 "판정"하지 않습니다.
   어디까지나 궤적 패턴을 근거로 한 "음주운전 의심 차량" 탐지 보조 도구입니다.

구조
----
Tracking (detect + update_track)
    ↓
Trajectory Analysis (calculate_heading + calculate_delta_angle)
    ↓
Rule-Based Detection (detect_weaving)
    ↓
Alert / Event (draw_warning + emit_event)

향후 emit_event()에 핸들러만 추가하면 다음 기능을 붙일 수 있습니다.
    - PostgreSQL 이벤트 저장
    - WebSocket 실시간 경보 전송
    - Leaflet 지도에 이벤트 좌표 표시
"""

import math
from collections import deque
from dataclasses import dataclass
from datetime import datetime

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from ultralytics import YOLO


# ==================================================
# 설정 (Config)
# ==================================================

MODEL_PATH = "yolo11m.pt"
VIDEO_PATH = "videos/0805.mp4"
OUTPUT_PATH = "result/anomaly_result.mp4"
WINDOW_NAME = "Anomaly Detection - Trajectory Analysis"

# 차량 클래스 (COCO: car, motorcycle, bus, truck)
VEHICLE_CLASSES = [2, 3, 5, 7]
CONF_THRESHOLD = 0.25

# 궤적에 저장할 최근 좌표 개수
TRAJECTORY_MAXLEN = 60

# 두 좌표 사이 이동 거리가 이보다 작으면 방향 계산에서 제외
# (정지 상태에 가까울 때 각도가 노이즈로 튀는 것을 방지)
MIN_DISPLACEMENT_PX = 4

# 이 각도(도) 이상 방향이 꺾여야 "유의미한 방향 전환"으로 기록
ANGLE_CHANGE_THRESHOLD_DEG = 12

# 방향 전환 이력을 몇 개까지 기억할지
TURN_EVENT_MAXLEN = 30

# 최근 몇 프레임 이내의 방향 전환만 Weaving 판단에 사용할지
WEAVING_WINDOW_FRAMES = 90  # 30fps 기준 약 3초

# 이 윈도우 안에서 좌↔우 전환이 몇 번 이상 반복되어야 Weaving으로 판단할지
WEAVING_MIN_ALTERNATIONS = 3

# 같은 차량에 대해 콘솔/이벤트 로그를 다시 찍기까지 최소 간격 (프레임)
# (화면 경고 박스는 조건이 유지되는 동안 계속 그려지고, 이건 "로그 스팸 방지"용)
ALERT_COOLDOWN_FRAMES = 60

# --------------------------------------------------
# Event Hold (경고 상태 유지)
# --------------------------------------------------
# Weaving이 감지된 뒤, 다시 감지되지 않더라도 "이상 주행 차량" 상태를
# 몇 초 동안 유지할지. 이 값 하나만 바꾸면 2초/3초/5초 등으로 조절된다.
HOLD_WARNING_SECONDS = 4

# 위 초(sec) 값을 프레임 수로 환산한 것. run() 실행 시 실제 영상 fps로
# 다시 계산되어 덮어써진다. 여기 있는 값은 fps를 아직 모를 때 쓰는 기본값(30fps 가정)이다.
HOLD_WARNING_FRAMES = HOLD_WARNING_SECONDS * 30

# 화면 표시
WARNING_COLOR = (0, 0, 255)          # 빨간색 (OpenCV, BGR)
WARNING_COLOR_RGB = tuple(reversed(WARNING_COLOR))  # PIL은 RGB 순서를 쓴다

WARNING_TITLE_KOR = "이상 주행 감지"    # 예: ABNORMAL DRIVING
WEAVING_REASON_KOR = "지그재그 주행"    # 예: WEAVING

# 한글 출력용 폰트. 매 프레임 새로 로드하면 느려지므로 모듈 로드 시 한 번만 생성한다.
FONT_PATH = "C:/Windows/Fonts/malgun.ttf"
FONT_BOLD_PATH = "C:/Windows/Fonts/malgunbd.ttf"  # 번호판(굵은 글씨) 전용
FONT_TITLE = ImageFont.truetype(FONT_PATH, 22)      # "이상 주행 감지"
FONT_BODY = ImageFont.truetype(FONT_PATH, 18)       # 원인
FONT_PLATE = ImageFont.truetype(FONT_BOLD_PATH, 22)  # 번호판 (굵게)

# --------------------------------------------------
# 실시간 이벤트 로그 패널 (좌측 상단)
# --------------------------------------------------
EVENT_LOG_MAXLEN = 5  # 최근 몇 건까지 화면에 표시할지

EVENT_LOG_PANEL_X = 20
EVENT_LOG_PANEL_Y = 20
EVENT_LOG_PANEL_WIDTH = 240

EVENT_LOG_PADDING_X = 14        # 좌우 내부 여백
EVENT_LOG_PADDING_TOP = 12      # 제목 위쪽 여백
EVENT_LOG_PADDING_BOTTOM = 14   # 마지막 줄 아래쪽 여백 (요구사항 6)

EVENT_LOG_TITLE_HEIGHT = 30     # 제목 한 줄이 차지하는 높이
EVENT_LOG_LINE_HEIGHT = 24      # 이벤트 한 줄(시간/번호판/원인)이 차지하는 높이
EVENT_LOG_ENTRY_GAP = 16        # 이벤트 블록 사이 간격(구분선 포함)

EVENT_LOG_BG_COLOR = (0, 0, 0)   # 반투명 검은색 배경
EVENT_LOG_BG_ALPHA = 140         # 0(완전 투명) ~ 255(불투명)

EVENT_LOG_TITLE_COLOR = (255, 255, 0)     # 노란색 - "AI 관제 이벤트"
EVENT_LOG_TIME_COLOR = (255, 255, 255)    # 흰색 - 발생 시각
EVENT_LOG_VEHICLE_COLOR = (255, 255, 255)   # 흰색 - 차량 번호판
EVENT_LOG_LABEL_COLOR = (255, 255, 255)   # 흰색 - 이벤트 종류
EVENT_LOG_DIVIDER_COLOR = (255, 255, 255, 70)  # 반투명 흰색 구분선

FONT_LOG_TITLE = ImageFont.truetype(FONT_PATH, 20)
FONT_LOG_BODY = ImageFont.truetype(FONT_PATH, 16)


# ==================================================
# 이벤트 모델 & 발행 구조 (확장 포인트)
# ==================================================

@dataclass
class AnomalyEvent:
    """이상 주행 이벤트 1건. 추후 DB 저장/전송 시 이 구조를 그대로 직렬화하면 됩니다."""
    track_id: int
    frame_idx: int
    timestamp_sec: float
    event_type: str      # 예: "WEAVING_DETECTED"
    position: tuple       # (x, y) 이벤트 발생 시점 차량 중심 좌표 (지도 표시용)
    message: str


# 이벤트가 발생했을 때 호출될 핸들러 목록.
# 지금은 콘솔 출력 핸들러 하나만 등록되어 있지만,
# 아래처럼 핸들러를 추가로 등록하기만 하면 기능이 확장됩니다.
#
#   register_event_handler(postgres_event_handler)
#   register_event_handler(websocket_event_handler)
_event_handlers = []


def register_event_handler(handler):
    """이상 주행 이벤트가 발생할 때마다 호출될 함수를 등록한다."""
    _event_handlers.append(handler)


def emit_event(event: AnomalyEvent):
    """등록된 모든 핸들러에게 이벤트를 전달한다."""
    for handler in _event_handlers:
        handler(event)


def console_event_handler(event: AnomalyEvent):
    """기본 핸들러: 콘솔에 이벤트를 출력한다."""
    print(f"[{event.timestamp_sec:.2f} sec] Vehicle #{event.track_id} {event.event_type.replace('_', ' ')}")


# --- 향후 확장 예시 (아직 미구현, 자리만 잡아둔 스텁) ---------------------

def postgres_event_handler(event: AnomalyEvent):
    """TODO: PostgreSQL events 테이블에 event를 INSERT."""
    raise NotImplementedError


def websocket_event_handler(event: AnomalyEvent):
    """TODO: 연결된 WebSocket 클라이언트들에게 event를 broadcast."""
    raise NotImplementedError




# ============================================================
# gis_event_bridge_PATCH.py
# ------------------------------------------------------------
# anomaly_detection.py에 "추가만" 하는 패치입니다.
# 기존 함수(detect, update_track, detect_weaving, handle_anomaly,
# draw_warning, run 등)는 단 한 줄도 수정하지 않습니다.
#
# 적용 방법
# ------------------------------------------------------------
# 1. 아래 "여기부터"~"여기까지" 블록을 anomaly_detection.py의
#    websocket_event_handler 함수 정의 바로 다음(향후 확장 스텁들 근처)에
#    그대로 붙여넣습니다.
#
# 2. anomaly_detection.py 맨 아래
#
#        if __name__ == "__main__":
#            register_event_handler(console_event_handler)
#            run()
#
#    이 블록을 아래처럼 바꿉니다.
#
#        if __name__ == "__main__":
#            _gis_read_existing_seq()
#            register_event_handler(console_event_handler)
#            register_event_handler(gis_event_handler)
#            run(video_path="videos/0805.mp4")   # ← 0807.mp4가 아니라 0805.mp4로 변경
#
#    ⚠️ 중요: 현재 anomaly_detection.py 상단의
#        VIDEO_PATH = "videos/0807.mp4"
#    는 0807.mp4를 가리키고 있습니다. GIS에서는 H4642 CCTV가
#    0805.mp4에 연결되어 있으므로, 실제로 분석할 영상도 0805.mp4여야
#    의미가 맞습니다. run(video_path=...) 인자로 넘기거나, 위 상수
#    자체를 "videos/0805.mp4"로 바꿔주세요.
# ============================================================

import json
import os

# --------------------------------------------------
# GIS 연동 설정
# --------------------------------------------------
# anomaly_detection.py를 프로젝트 루트(SMARTCCTV/)에서 실행한다고 가정한 경로입니다.
# 만약 다른 위치에서 실행한다면 이 경로만 실제 위치에 맞게 바꿔주세요.
GIS_EVENT_JSON_PATH = "web/data/event.json"

# 이번 단계에서는 H4642(이수어린이집 앞) 하나만 분석 대상입니다.
# GIS의 TEST_VIDEO_OVERRIDES에 등록된 것과 동일한 cam_id/설치장소를 그대로 사용합니다.
GIS_CAM_ID = "H4642"
GIS_LOCATION_NAME = "이수어린이집 앞"

_gis_seq = 0


def _gis_read_existing_seq():
    """이전에 만들어둔 event.json이 있다면 그 seq에서 이어서 증가시킨다.
    (스크립트를 재시작할 때마다 seq가 1로 초기화되어 GIS가 "새 이벤트"로
    잘못 재생하는 것을 방지)"""
    global _gis_seq
    try:
        with open(GIS_EVENT_JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            _gis_seq = int(data.get("seq", 0))
    except (FileNotFoundError, json.JSONDecodeError, ValueError, TypeError):
        _gis_seq = 0


def gis_event_handler(event: AnomalyEvent):
    """emit_event()가 호출하는 핸들러 중 하나.

    AnomalyEvent(판정 로직이 이미 만들어 둔 결과)를 그대로 받아서
    GIS의 web/data/event.json 계약 형식으로 옮겨 적기만 한다.
    탐지/추적/이상운전 판정 로직에는 전혀 관여하지 않는다.

    주의:
    - event.position은 영상 프레임 픽셀 좌표(x, y)이지 위경도가 아니므로
      GIS 지도 좌표로 사용하지 않는다. GIS는 H4642의 실제 설치 좌표를
      그대로 사용한다 (video_position_px는 디버깅 참고용으로만 함께 보낸다).
    - 이 알고리즘(detect_weaving)은 규칙 기반이라 수치형 신뢰도가 없다.
      confidence를 임의로 만들어내지 않고 null로 보낸다.
    """
    global _gis_seq
    _gis_seq += 1

    payload = {
        "seq": _gis_seq,
        "cam_id": GIS_CAM_ID,
        "location_name": GIS_LOCATION_NAME,
        "event_type": "ANOMALY_DRIVING",
        "track_id": str(event.track_id),
        "plate": get_vehicle_plate(event.track_id),  # 화면(draw_warning)에 표시 중인 것과 동일한 더미 번호판
        "reason": WEAVING_REASON_KOR,  # "지그재그 주행" (기존 상수 재사용)
        "time": datetime.now().strftime("%H:%M:%S"),
        "confidence": None,  # 규칙 기반 판정 - 수치형 신뢰도 없음. 하드코딩하지 않음.
        "video_position_px": {"x": event.position[0], "y": event.position[1]},  # 참고용(픽셀 좌표)
    }

    # 원자적 쓰기: GIS가 폴링 중 절반만 써진 JSON을 읽지 않도록 임시 파일 → rename
    tmp_path = GIS_EVENT_JSON_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    os.replace(tmp_path, GIS_EVENT_JSON_PATH)

    print(
        f"[GIS EVENT] seq={_gis_seq} cam_id={GIS_CAM_ID} "
        f"track_id={event.track_id} -> {GIS_EVENT_JSON_PATH}"
    )

# ============================================================
# 여기까지가 anomaly_detection.py에 추가할 내용입니다.
# ============================================================

# ==================================================
# Track별 궤적 분석 상태
# ==================================================

class TrackState:
    """Track ID 하나에 대한 궤적 및 방향 전환 이력을 보관한다."""

    def __init__(self):
        self.positions = deque(maxlen=TRAJECTORY_MAXLEN)     # 중심 좌표 이력
        self.last_heading = None                              # 직전 진행 방향 (도)
        self.turn_events = deque(maxlen=TURN_EVENT_MAXLEN)     # (frame_idx, "L" | "R")
        self.last_alert_frame = -ALERT_COOLDOWN_FRAMES         # 마지막으로 이벤트를 발행한 프레임
        self.last_weaving_frame = -10 ** 9                     # 마지막으로 Weaving이 실제 감지된 프레임 (Event Hold용)


# Track ID -> TrackState
track_states: dict[int, "TrackState"] = {}


def get_or_create_track_state(track_id: int) -> TrackState:
    if track_id not in track_states:
        track_states[track_id] = TrackState()
    return track_states[track_id]


# ==================================================
# 번호판 표시 (현재: 더미 매핑 / 향후: PaddleOCR 인식 결과로 교체)
# ==================================================
# get_vehicle_plate() 하나만 호출부에서 사용하고, 내부 구현은 자유롭게 바꿀 수 있도록
# 분리해뒀다. 나중에 PaddleOCR을 붙일 때는 이 함수 내부만
# "OCR 인식 결과 조회"로 교체하면 되고, draw_warning() 등 호출부는 손댈 필요가 없다.

DUMMY_PLATES = [
    "12가3456",
    "34나7890",
    "56다1234",
    "78라5678",
    "90마9012",
    "11바3456",
    "22사7890",
    "33아1234",
]

# Track ID -> 번호판 문자열 (최초 등장 시 한 번만 배정, 이후 동일 차량은 같은 번호판 유지)
track_to_plate: dict[int, str] = {}
_dummy_plate_index = 0


def get_vehicle_plate(track_id: int) -> str:
    """
    화면에 표시할 차량 번호판 문자열을 반환한다.

    지금은 Track ID마다 더미 번호판을 순서대로 배정해서 반환하지만,
    향후 PaddleOCR로 실제 번호판 인식이 가능해지면
    이 함수 내부만 "OCR 인식 결과 조회" 코드로 교체하면 된다.
    """
    global _dummy_plate_index

    if track_id not in track_to_plate:
        track_to_plate[track_id] = DUMMY_PLATES[_dummy_plate_index % len(DUMMY_PLATES)]
        _dummy_plate_index += 1

    return track_to_plate[track_id]


# ==================================================
# 1~2. 탐지 + Track ID 유지 (YOLOv11m + ByteTrack)
# ==================================================

def detect(model: YOLO, frame):
    """YOLOv11m으로 차량을 탐지하고, ByteTrack으로 Track ID를 유지한 결과를 반환한다."""
    return model.track(
        frame,
        tracker="bytetrack.yaml",
        classes=VEHICLE_CLASSES,
        conf=CONF_THRESHOLD,
        persist=True,
        verbose=False,
    )


# ==================================================
# 4~5. 진행 방향(Heading) 및 방향 변화량(ΔAngle) 계산
# ==================================================

def calculate_heading(p1, p2) -> float:
    """두 좌표(p1 -> p2) 사이의 진행 방향을 각도(도)로 반환한다."""
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    return math.degrees(math.atan2(dy, dx))


def calculate_delta_angle(prev_heading: float, curr_heading: float) -> float:
    """두 진행 방향 사이의 차이를 -180 ~ 180도 범위로 정규화해서 반환한다."""
    diff = curr_heading - prev_heading
    return (diff + 180) % 360 - 180


# ==================================================
# 3. Track ID별 궤적 저장 + 유의미한 방향 전환 기록
# ==================================================

def update_track(track_id: int, center: tuple, frame_idx: int):
    """
    새로 검출된 중심 좌표를 해당 Track의 궤적에 추가하고,
    직전 진행 방향과 비교해 유의미한 방향 전환(턴)이 있었다면 기록한다.
    """
    state = get_or_create_track_state(track_id)
    state.positions.append(center)

    if len(state.positions) < 2:
        return

    prev_point = state.positions[-2]
    displacement = math.hypot(center[0] - prev_point[0], center[1] - prev_point[1])

    # 거의 정지한 상태에서는 각도가 노이즈로 크게 튈 수 있으므로 계산을 건너뜀
    if displacement < MIN_DISPLACEMENT_PX:
        return

    heading = calculate_heading(prev_point, center)

    if state.last_heading is not None:
        delta_angle = calculate_delta_angle(state.last_heading, heading)

        if abs(delta_angle) >= ANGLE_CHANGE_THRESHOLD_DEG:
            direction = "R" if delta_angle > 0 else "L"
            state.turn_events.append((frame_idx, direction))

    state.last_heading = heading


# ==================================================
# 6. Weaving(좌우 흔들림 반복) 판단 - 규칙 기반
# ==================================================

def detect_weaving(track_id: int, frame_idx: int) -> bool:
    """
    최근 WEAVING_WINDOW_FRAMES 이내에 기록된 방향 전환들을 살펴보고,
    좌<->우 전환이 WEAVING_MIN_ALTERNATIONS 회 이상 반복되었는지 확인한다.

    점수나 학습 모델을 쓰지 않는 순수 규칙 기반 로직이다.
    """
    state = track_states.get(track_id)

    if state is None:
        return False

    recent_events = [
        (f, d) for f, d in state.turn_events
        if frame_idx - f <= WEAVING_WINDOW_FRAMES
    ]

    if len(recent_events) < WEAVING_MIN_ALTERNATIONS + 1:
        return False

    alternations = sum(
        1 for i in range(1, len(recent_events))
        if recent_events[i][1] != recent_events[i - 1][1]
    )

    return alternations >= WEAVING_MIN_ALTERNATIONS


# 등록된 이상 주행 판별 규칙들.
# 나중에 "급정지", "역주행" 같은 패턴을 추가하려면
# 같은 시그니처(track_id, frame_idx) -> (event_type, label) | None 의
# 함수를 만들어 이 리스트에 추가하기만 하면 된다.
def _check_weaving_rule(track_id: int, frame_idx: int):
    if detect_weaving(track_id, frame_idx):
        return "WEAVING_DETECTED", WEAVING_REASON_KOR
    return None


ANOMALY_RULES = [
    _check_weaving_rule,
]


def evaluate_anomaly_rules(track_id: int, frame_idx: int):
    """등록된 규칙들을 순서대로 평가해, 처음으로 감지된 (event_type, label)을 반환한다."""
    for rule in ANOMALY_RULES:
        result = rule(track_id, frame_idx)
        if result is not None:
            return result
    return None


# --------------------------------------------------
# Event Hold (경고 상태 유지)
# --------------------------------------------------
# 판단 알고리즘(detect_weaving 등)은 전혀 건드리지 않는다.
# "지금 이 순간 Weaving인가?"와 "지금 경고를 계속 보여줘야 하는가?"를
# 분리해서, 후자만 HOLD_WARNING_FRAMES 기준으로 별도 판단한다.

def is_abnormal_active(track_id: int, frame_idx: int) -> bool:
    """
    최근 HOLD_WARNING_FRAMES 이내에 Weaving이 감지된 적이 있다면
    지금 당장 재감지되지 않았더라도 '경고 유지 상태'로 간주한다.
    """
    state = track_states.get(track_id)

    if state is None:
        return False

    return frame_idx - state.last_weaving_frame <= HOLD_WARNING_FRAMES


# ==================================================
# 7. 화면 경고 표시
# ==================================================

def draw_warning(frame, box, track_id: int, label: str):
    """
    이상 주행 차량 경고를 그린다.

    - 박스(사각형)는 텍스트가 아니므로 그대로 OpenCV(cv2.rectangle)로 그린다.
    - 한글 텍스트(번호판 / 제목 / 원인)는 OpenCV가 한글을 지원하지 않으므로
      PIL(ImageDraw + ImageFont)로 한 번에 그린 뒤 다시 frame에 반영한다.
    - 번호판은 get_vehicle_plate()를 통해 가져온다 (현재는 더미, 추후 OCR 결과로 교체 예정).

    frame은 numpy 배열을 그 자리에서(in-place) 갱신하므로,
    호출부(handle_anomaly, run)의 기존 사용 방식은 그대로 유지된다.
    """
    x1, y1, x2, y2 = box
    plate = get_vehicle_plate(track_id)

    # 박스 (OpenCV)
    cv2.rectangle(frame, (x1, y1), (x2, y2), WARNING_COLOR, 3)

    # 한글 텍스트 (PIL)
    pil_image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil_image)

    draw.text((x1, max(y1 - 56, 0)), plate, font=FONT_PLATE, fill=WARNING_COLOR_RGB)
    draw.text((x1, max(y1 - 32, 0)), WARNING_TITLE_KOR, font=FONT_TITLE, fill=WARNING_COLOR_RGB)
    draw.text((x1, y2 + 8), f"원인 : {label}", font=FONT_BODY, fill=WARNING_COLOR_RGB)

    frame[:] = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)


# ==================================================
# 실시간 이벤트 로그 (좌측 상단 패널)
# ==================================================
# "이상 주행 에피소드"가 새로 시작된 순간에만 1건씩 쌓인다.
# (같은 에피소드가 HOLD_WARNING_FRAMES 동안 유지되는 중에는 추가되지 않음)
event_logs = deque(maxlen=EVENT_LOG_MAXLEN)


def add_event_log(track_id: int, label: str):
    """이상 주행 에피소드가 새로 시작된 순간, 이벤트 로그에 1건을 등록한다."""
    event_logs.append({
        "time": datetime.now().strftime("%H:%M:%S"),
        "track_id": track_id,
        "plate": get_vehicle_plate(track_id),  # 차량 위 UI와 동일한 더미 번호판(추후 OCR 결과로 교체)
        "label": label,
    })


def _calc_event_log_panel_height(entry_count: int) -> int:
    """
    이벤트 개수에 맞는 패널 전체 높이를 계산한다.
    draw_event_log_panel()의 실제 그리기 루프와 반드시 같은 값을 써야 하므로,
    두 곳 모두 이 함수(또는 아래의 동일한 EVENT_LOG_* 상수)를 통해서만 계산한다.
    """
    if entry_count == 0:
        return 0

    content_height = (
        EVENT_LOG_TITLE_HEIGHT
        + entry_count * (EVENT_LOG_LINE_HEIGHT * 3)
        + entry_count * EVENT_LOG_ENTRY_GAP
    )

    return EVENT_LOG_PADDING_TOP + content_height + EVENT_LOG_PADDING_BOTTOM


def draw_event_log_panel(frame):
    """좌측 상단에 반투명 배경의 실시간 이벤트 로그 패널을 그린다 (PIL).

    패널 높이는 현재 이벤트 개수에 맞춰 자동으로 커지거나 작아진다.
    """
    if not event_logs:
        return

    entry_count = len(event_logs)
    panel_height = _calc_event_log_panel_height(entry_count)

    base = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)).convert("RGBA")

    # 반투명 배경은 별도 레이어에 그린 뒤 합성한다 (alpha 채널 사용)
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    overlay_draw.rectangle(
        [
            EVENT_LOG_PANEL_X,
            EVENT_LOG_PANEL_Y,
            EVENT_LOG_PANEL_X + EVENT_LOG_PANEL_WIDTH,
            EVENT_LOG_PANEL_Y + panel_height,
        ],
        fill=(*EVENT_LOG_BG_COLOR, EVENT_LOG_BG_ALPHA),
    )

    x_left = EVENT_LOG_PANEL_X + EVENT_LOG_PADDING_X
    x_right = EVENT_LOG_PANEL_X + EVENT_LOG_PANEL_WIDTH - EVENT_LOG_PADDING_X
    y = EVENT_LOG_PANEL_Y + EVENT_LOG_PADDING_TOP

    # 제목 아래 구분선
    overlay_draw.line(
        [(x_left, y + EVENT_LOG_TITLE_HEIGHT - 6), (x_right, y + EVENT_LOG_TITLE_HEIGHT - 6)],
        fill=EVENT_LOG_DIVIDER_COLOR,
        width=1,
    )

    composed = Image.alpha_composite(base, overlay)
    draw = ImageDraw.Draw(composed)

    draw.text((x_left, y), "AI 관제 이벤트", font=FONT_LOG_TITLE, fill=EVENT_LOG_TITLE_COLOR)
    y += EVENT_LOG_TITLE_HEIGHT

    for i, entry in enumerate(event_logs):
        draw.text((x_left, y), entry["time"], font=FONT_LOG_BODY, fill=EVENT_LOG_TIME_COLOR)
        y += EVENT_LOG_LINE_HEIGHT

        draw.text((x_left, y), entry["plate"], font=FONT_LOG_BODY, fill=EVENT_LOG_VEHICLE_COLOR)
        y += EVENT_LOG_LINE_HEIGHT

        draw.text((x_left, y), entry["label"], font=FONT_LOG_BODY, fill=EVENT_LOG_LABEL_COLOR)
        y += EVENT_LOG_LINE_HEIGHT

        # 마지막 이벤트 뒤에는 구분선을 그리지 않는다 (아래 여백만 남김)
        if i < entry_count - 1:
            draw.line(
                [(x_left, y + EVENT_LOG_ENTRY_GAP // 2), (x_right, y + EVENT_LOG_ENTRY_GAP // 2)],
                fill=EVENT_LOG_DIVIDER_COLOR,
                width=1,
            )

        y += EVENT_LOG_ENTRY_GAP

    frame[:] = cv2.cvtColor(np.array(composed.convert("RGB")), cv2.COLOR_RGB2BGR)


# ==================================================
# 8. 이상 주행 이벤트 처리 (경고 표시 + 로그/이벤트 발행)
# ==================================================

def handle_anomaly(frame, box, track_id: int, frame_idx: int, fps: float):
    """
    한 Track에 대해 이상 주행 규칙을 평가한다.

    - 지금 새로 Weaving이 감지되면: 경고 유지 시간을 현재 프레임으로 갱신(연장)한다.
    - 새로 감지되지 않았더라도 HOLD_WARNING_FRAMES 이내라면: 계속 경고 상태를 유지한다.
    - 콘솔/이벤트 로그는 "실제로 새로 감지된 순간"에만 남긴다 (유지 기간 동안 스팸 방지).
    - 좌측 상단 이벤트 로그는 "새 에피소드가 시작된 순간"에만 1건 등록한다.
    """
    state = get_or_create_track_state(track_id)

    # 이번 프레임에 새로 감지되어 last_weaving_frame이 갱신되기 "전" 상태를 먼저 확인해둔다.
    # (에피소드가 이미 진행 중이었는지, 지금 막 새로 시작하는지 구분하기 위함)
    was_active_before = is_abnormal_active(track_id, frame_idx)

    # ① 판단 알고리즘은 그대로 호출 (수정 없음)
    result = evaluate_anomaly_rules(track_id, frame_idx)

    if result is not None:
        # 새로 감지됨 -> 유지 시간을 지금 시점으로 연장
        state.last_weaving_frame = frame_idx

    # ② / ③ 유지 시간이 지났고 새로 감지도 안 됐다면 정상 상태 -> 아무 것도 하지 않음
    if not is_abnormal_active(track_id, frame_idx):
        return

    # 여기 도달하면 "방금 감지됨" 또는 "유지 시간 중" 둘 중 하나이므로 경고를 계속 그린다
    label = result[1] if result is not None else WEAVING_REASON_KOR
    draw_warning(frame, box, track_id, label)

    # 좌측 상단 이벤트 로그: 이전에는 비활성 상태였는데 지금 막 새로 감지된 경우 = 새 에피소드 시작
    if result is not None and not was_active_before:
        add_event_log(track_id, WARNING_TITLE_KOR)

    # 새로 감지된 경우가 아니면(유지 기간 중이면) 콘솔 로그는 남기지 않는다
    if result is None:
        return

    event_type, label = result

    # 콘솔/이벤트 로그는 너무 자주 찍히지 않도록 쿨다운을 둔다
    if frame_idx - state.last_alert_frame < ALERT_COOLDOWN_FRAMES:
        return

    state.last_alert_frame = frame_idx

    event = AnomalyEvent(
        track_id=track_id,
        frame_idx=frame_idx,
        timestamp_sec=frame_idx / fps,
        event_type=event_type,
        position=state.positions[-1],
        message=f"Vehicle #{track_id} {label}",
    )

    emit_event(event)


# ==================================================
# 메인 실행 루프
# ==================================================

def run(video_path: str = VIDEO_PATH, output_path: str = OUTPUT_PATH):
    model = YOLO(MODEL_PATH)

    cap = cv2.VideoCapture(video_path)

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0

    # HOLD_WARNING_SECONDS(초 단위 설정)를 실제 영상 fps 기준 프레임 수로 정확히 환산
    global HOLD_WARNING_FRAMES
    HOLD_WARNING_FRAMES = max(1, round(HOLD_WARNING_SECONDS * fps))

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

    frame_idx = 0

    while True:

        frame_idx += 1
        ret, frame = cap.read()

        if not ret:
            break

        results = detect(model, frame)
        annotated_frame = frame.copy()

        boxes = results[0].boxes

        if boxes is not None:

            for box in boxes:

                if box.id is None:
                    continue

                x1, y1, x2, y2 = map(int, box.xyxy[0])
                center = ((x1 + x2) // 2, (y1 + y2) // 2)
                track_id = int(box.id[0])

                update_track(track_id, center, frame_idx)
                handle_anomaly(annotated_frame, (x1, y1, x2, y2), track_id, frame_idx, fps)

        # 좌측 상단 실시간 이벤트 로그 패널 (프레임당 1회, 영상 저장에도 함께 포함됨)
        draw_event_log_panel(annotated_frame)

        out.write(annotated_frame)
        cv2.imshow(WINDOW_NAME, annotated_frame)

        if cv2.waitKey(1) == 27:  # ESC 종료
            break

    cap.release()
    out.release()
    cv2.destroyAllWindows()

    print("이상 주행 패턴 분석 완료!")


if __name__ == "__main__":
    _gis_read_existing_seq()
    register_event_handler(console_event_handler)
    register_event_handler(gis_event_handler)
    run(video_path="videos/0805.mp4")