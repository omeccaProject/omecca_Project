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
import os
import platform
from collections import deque
from dataclasses import dataclass
from datetime import datetime

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from ultralytics import YOLO


# ==================================================
# 한글 폰트 경로 (OS별 자동 탐색 - 이 파일 안에서 이 블록 하나만 존재해야 함)
# ==================================================
# 이전에 파일 아래쪽 "화면 표시" 섹션에 하드코딩된 FONT_PATH가 하나 더 있었는데,
# 그게 여기서 찾은 값을 덮어써서 macOS에서 항상 윈도우 경로로 되돌아가는 버그가 있었다.
# 그래서 폰트 관련 정의는 이 블록 하나로 통합했다.

def _resolve_font(candidates):
    """후보 경로들을 순서대로 실제로 열어보고, 되는 첫 번째 경로를 반환한다.
    파일이 존재해도 Pillow/FreeType이 못 여는 폰트가 있어서(AppleGothic.ttf 일부
    환경에서 확인됨) 존재 여부만 확인하지 않고 직접 로드까지 시도한다."""
    for path in candidates:
        if not path or not os.path.exists(path):
            continue
        try:
            ImageFont.truetype(path, 16)
            return path
        except OSError:
            continue
    return None


if platform.system() == "Windows":
    FONT_PATH = _resolve_font(["C:/Windows/Fonts/malgun.ttf"])
    FONT_BOLD_PATH = _resolve_font(["C:/Windows/Fonts/malgunbd.ttf"]) or FONT_PATH
elif platform.system() == "Darwin":
    FONT_PATH = _resolve_font([
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
        "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
        "/Library/Fonts/AppleGothic.ttf",
    ])
    # macOS엔 맑은 고딕 Bold에 대응하는 표준 경로가 없어서, 굵은 폰트도 같은 파일로 대체한다
    # (PIL이 자체적으로 두껍게 만들어주진 않지만, 데모 화면에서 크게 문제되지 않는다)
    FONT_BOLD_PATH = FONT_PATH
else:
    FONT_PATH = _resolve_font(["/usr/share/fonts/truetype/nanum/NanumGothic.ttf"])
    FONT_BOLD_PATH = FONT_PATH

if FONT_PATH is None:
    print("[FONT] 한글 폰트를 하나도 못 찾아서 기본 폰트로 대체합니다 (한글이 깨져 보일 수 있음)")


def _load_font(path, size):
    if path is None:
        return ImageFont.load_default()
    return ImageFont.truetype(path, size)


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
# (FONT_PATH / FONT_BOLD_PATH는 파일 위쪽 "한글 폰트 경로" 블록에서 이미 OS별로 결정됨)
FONT_TITLE = _load_font(FONT_PATH, 22)       # "이상 주행 감지"
FONT_BODY = _load_font(FONT_PATH, 18)        # 원인
FONT_PLATE = _load_font(FONT_BOLD_PATH, 22)  # 번호판 (굵게)

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

FONT_LOG_TITLE = _load_font(FONT_PATH, 20)
FONT_LOG_BODY = _load_font(FONT_PATH, 16)


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
# GIS 이벤트 브릿지 (web/data/event.json에 기록)
# ------------------------------------------------------------
# emit_event()가 호출하는 핸들러 중 하나. 탐지/추적/이상운전 판정
# 로직에는 관여하지 않고, 이미 만들어진 AnomalyEvent를 GIS가 읽는
# 파일 형식으로 옮겨 적기만 한다.
# ============================================================

import json

# anomaly_detection.py를 프로젝트 루트(SmartCCTV/)에서 실행한다고 가정한 경로입니다.
GIS_EVENT_JSON_PATH = "web/data/event.json"

# 이번 단계에서는 H4642(이수어린이집 앞) 하나만 분석 대상입니다.
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
    """AnomalyEvent를 GIS의 web/data/event.json 계약 형식으로 옮겨 적는다.

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
        "plate": get_vehicle_plate(event.track_id),
        "reason": WEAVING_REASON_KOR,
        "time": datetime.now().strftime("%H:%M:%S"),
        "confidence": None,
        "video_position_px": {"x": event.position[0], "y": event.position[1]},
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

track_to_plate: dict[int, str] = {}
_dummy_plate_index = 0


def get_vehicle_plate(track_id: int) -> str:
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


def _check_weaving_rule(track_id: int, frame_idx: int):
    if detect_weaving(track_id, frame_idx):
        return "WEAVING_DETECTED", WEAVING_REASON_KOR
    return None


ANOMALY_RULES = [
    _check_weaving_rule,
]


def evaluate_anomaly_rules(track_id: int, frame_idx: int):
    for rule in ANOMALY_RULES:
        result = rule(track_id, frame_idx)
        if result is not None:
            return result
    return None


def is_abnormal_active(track_id: int, frame_idx: int) -> bool:
    state = track_states.get(track_id)

    if state is None:
        return False

    return frame_idx - state.last_weaving_frame <= HOLD_WARNING_FRAMES


# ==================================================
# 7. 화면 경고 표시
# ==================================================

def draw_warning(frame, box, track_id: int, label: str):
    x1, y1, x2, y2 = box
    plate = get_vehicle_plate(track_id)

    cv2.rectangle(frame, (x1, y1), (x2, y2), WARNING_COLOR, 3)

    pil_image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil_image)

    draw.text((x1, max(y1 - 56, 0)), plate, font=FONT_PLATE, fill=WARNING_COLOR_RGB)
    draw.text((x1, max(y1 - 32, 0)), WARNING_TITLE_KOR, font=FONT_TITLE, fill=WARNING_COLOR_RGB)
    draw.text((x1, y2 + 8), f"원인 : {label}", font=FONT_BODY, fill=WARNING_COLOR_RGB)

    frame[:] = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)


# ==================================================
# 실시간 이벤트 로그 (좌측 상단 패널)
# ==================================================
event_logs = deque(maxlen=EVENT_LOG_MAXLEN)


def add_event_log(track_id: int, label: str):
    event_logs.append({
        "time": datetime.now().strftime("%H:%M:%S"),
        "track_id": track_id,
        "plate": get_vehicle_plate(track_id),
        "label": label,
    })


def _calc_event_log_panel_height(entry_count: int) -> int:
    if entry_count == 0:
        return 0

    content_height = (
        EVENT_LOG_TITLE_HEIGHT
        + entry_count * (EVENT_LOG_LINE_HEIGHT * 3)
        + entry_count * EVENT_LOG_ENTRY_GAP
    )

    return EVENT_LOG_PADDING_TOP + content_height + EVENT_LOG_PADDING_BOTTOM


def draw_event_log_panel(frame):
    if not event_logs:
        return

    entry_count = len(event_logs)
    panel_height = _calc_event_log_panel_height(entry_count)

    base = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)).convert("RGBA")

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
    state = get_or_create_track_state(track_id)

    was_active_before = is_abnormal_active(track_id, frame_idx)

    result = evaluate_anomaly_rules(track_id, frame_idx)

    if result is not None:
        state.last_weaving_frame = frame_idx

    if not is_abnormal_active(track_id, frame_idx):
        return

    label = result[1] if result is not None else WEAVING_REASON_KOR
    draw_warning(frame, box, track_id, label)

    if result is not None and not was_active_before:
        add_event_log(track_id, WARNING_TITLE_KOR)

    if result is None:
        return

    event_type, label = result

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