import os
import cv2
import time
import math
import threading
import requests

from collections import deque
from datetime import datetime
from pathlib import Path

import numpy as np
import torch
from dotenv import load_dotenv
from ultralytics import YOLO
from PIL import Image, ImageDraw, ImageFont


# ============================================================
# 1. 기본 경로
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

VIDEO_DIR = BASE_DIR / "videos"

MODEL_PATH = BASE_DIR / "yolo11s.pt"

TRACKER_CONFIG = BASE_DIR / "bytetrack_custom.yaml"


# ============================================================
# 2. .env
# ============================================================

load_dotenv(BASE_DIR / ".env")

_GATEWAY_URL_RAW = os.getenv(
    "GATEWAY_URL",
    "http://localhost:8080"
)

_GATEWAY_BASE_URL = _GATEWAY_URL_RAW.rstrip("/")

if _GATEWAY_BASE_URL.endswith("/api/cctv/detections"):
    GATEWAY_URL = _GATEWAY_BASE_URL
    _GATEWAY_HOST_ONLY = _GATEWAY_BASE_URL[: -len("/api/cctv/detections")]
else:
    GATEWAY_URL = _GATEWAY_BASE_URL + "/api/cctv/detections"
    _GATEWAY_HOST_ONLY = _GATEWAY_BASE_URL

JOURNEY_URL = _GATEWAY_HOST_ONLY + "/api/cctv/journey"

GATEWAY_API_KEY = os.getenv(
    "GATEWAY_API_KEY"
)


if not GATEWAY_API_KEY:

    raise RuntimeError(
        "❌ GATEWAY_API_KEY가 .env에 없습니다."
    )


# ============================================================
# 3. GPU / CPU 설정
# ============================================================

USE_GPU = False


if USE_GPU:

    DEVICE = 0

else:

    DEVICE = "cpu"


# ============================================================
# 4. 실제 CCTV 설정
# ============================================================

CCTV_CONFIG = {

    "CCTV-A": {

        "camId": "L010111",

        "video":
            VIDEO_DIR / "음주운전1.mp4",

    },

    "CCTV-B": {

        "camId": "L010271",

        "video":
            VIDEO_DIR / "음주운전2.mp4",

    },

    "CCTV-C": {

        "camId": "L010128",

        "video":
            VIDEO_DIR / "음주운전3.mp4",

    },

    "CCTV-D": {

        "camId": "L010481",

        "video":
            VIDEO_DIR / "음주운전4.mp4",

    },

}


# ============================================================
# 5. YOLO 설정
# ============================================================

CONF_THRESH = 0.30

IMG_SIZE = 640


VEHICLE_CLASSES = [

    2,
    3,
    5,
    7,

]


# ============================================================
# 6. 이상운전 판단 설정
# ============================================================

HISTORY_MAXLEN = 25

MIN_HISTORY_FOR_ANALYSIS = 4

NOISE_DX_PX = 2.0

MIN_LATERAL_RANGE_PX = 10

MIN_TOTAL_LATERAL_MOVEMENT = 20

MIN_DIRECTION_REVERSALS = 1

SUSTAIN_FRAMES = 1

FORCE_ALERT_AFTER_SECONDS = 3.0


# ============================================================
# 7. API 전송 주기
# ============================================================

DETECTION_SEND_INTERVAL = 0.10


# ============================================================
# 7-1. 관제 UI 설정 (신규 - 화면 표시 전용, AI/Journey 로직과 무관)
# ============================================================
# 이 섹션의 값을 바꿔도 YOLO/ByteTrack/이상운전 판정/Journey/Spring Boot 전송
# 결과는 전혀 달라지지 않는다 - 순수하게 "화면에 어떻게 그릴지"만 다룬다.

# [중요] 다른 팀원의 번호판 인식(LPR) 모듈이 아직 연결되지 않았다 - 그래서 번호판
# 값을 여기서 지어내지 않는다. main()의 plate_by_camera[camera_name] 딕셔너리에
# { track_id: "12가5680" } 형태로 값이 채워지면 그 값을 그대로 표시하고, 없으면
# 아래 문구를 그대로 표시한다.
PLATE_UNKNOWN_LABEL = "차량번호 확인 중"

# 한글이 렌더링 가능한 시스템 폰트를 순서대로 찾아본다(요구사항: 맑은 고딕 → 나눔고딕
# → 기타 순). 하나도 없으면 PIL 기본 폰트로 대체되며, 이 경우에도 프로그램 자체는
# 계속 실행된다 - 한글 렌더링 실패가 YOLO/영상 처리에 영향을 주지 않는다.
KOREAN_FONT_CANDIDATES = [
    "malgun.ttf",  # Windows 기본 한글 폰트(맑은 고딕)
    "C:/Windows/Fonts/malgun.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",  # 나눔고딕
    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
    "/System/Library/Fonts/Supplemental/AppleGothic.ttf",  # macOS
]

_korean_font_cache = {}


def _get_korean_font(size):
    """지정한 크기의 한글 폰트를 캐싱해서 반환한다(매 프레임 새로 로드하면 느려짐).
    폰트를 하나도 못 찾아도 예외를 던지지 않고 PIL 기본 폰트로 대체한다."""
    if size in _korean_font_cache:
        return _korean_font_cache[size]

    font = None
    for path in KOREAN_FONT_CANDIDATES:
        try:
            font = ImageFont.truetype(path, size)
            break
        except OSError:
            continue

    if font is None:
        print("[경고] 한글 폰트를 찾지 못해 기본 폰트로 대체합니다 - 한글이 깨져 보일 수 있습니다.")
        font = ImageFont.load_default()

    _korean_font_cache[size] = font
    return font


def draw_korean_texts(frame_bgr, texts):
    """
    cv2.putText는 한글을 렌더링하지 못하므로(각모/물음표로 깨짐), 프레임 전체를
    PIL 이미지로 한 번만 변환해서 요청된 텍스트를 전부 그린 뒤 다시 OpenCV(BGR)
    배열로 변환해서 반환한다.

    texts: [{"text": str, "org": (x,y), "size": int, "color_bgr": (b,g,r)}, ...]
    한 프레임당 이 변환을 여러 번 하면(텍스트마다 한 번씩) 느려지므로, 한 프레임에
    그릴 한글 텍스트를 전부 모아서 "한 번만" 변환한다(요구사항: 성능 유지).
    """
    if not texts:
        return frame_bgr

    img_pil = Image.fromarray(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(img_pil)

    for t in texts:
        font = _get_korean_font(t.get("size", 18))
        b, g, r = t.get("color_bgr", (255, 255, 255))
        draw.text(t["org"], t["text"], font=font, fill=(r, g, b))

    return cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)


def _draw_corner_accents(frame, x1, y1, x2, y2, color, length=14, thickness=3):
    """bbox 네 모서리에 'ㄴ'자 형태의 강조선을 그린다 - 관제 시스템의 Detection Box
    느낌을 준다. 사각형 전체를 두껍게 그리는 것보다 차량을 덜 가린다."""
    for (cx, cy, dx, dy) in [
        (x1, y1, 1, 1), (x2, y1, -1, 1), (x1, y2, 1, -1), (x2, y2, -1, -1),
    ]:
        cv2.line(frame, (cx, cy), (cx + dx * length, cy), color, thickness)
        cv2.line(frame, (cx, cy), (cx, cy + dy * length), color, thickness)


def _draw_glow_rect(frame, x1, y1, x2, y2, color, pulse_phase, pad=6, alpha_base=0.25, alpha_amp=0.15):
    """이상운전 차량 bbox 바깥쪽에 은은하게 번지는 느낌의 사각형을 얹어서 Glow
    효과를 흉내낸다(실제 가우시안 블러는 매 프레임 비용이 커서 쓰지 않는다 - 요구사항:
    FPS 저하 방지). pulse_phase(0~2π)로 알파값을 아주 약하게 출렁이게 해서 옅은
    Pulse 느낌만 준다 - 차량을 가릴 정도로 과하게는 하지 않는다(요구사항: 차량을
    가리는 수준의 Glow 금지)."""
    alpha = alpha_base + alpha_amp * (0.5 + 0.5 * np.sin(pulse_phase))
    overlay = frame.copy()
    cv2.rectangle(overlay, (x1 - pad, y1 - pad), (x2 + pad, y2 + pad), color, thickness=pad)
    cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)


# ============================================================
# 8. GPU 확인
# ============================================================

def check_device():

    print()
    print("=" * 70)
    print("AI DEVICE CHECK")
    print("=" * 70)

    print(
        "USE_GPU :",
        USE_GPU
    )

    print(
        "CUDA available :",
        torch.cuda.is_available()
    )

    if USE_GPU:

        if not torch.cuda.is_available():

            print()
            print(
                "❌ GPU를 사용할 수 없습니다."
            )

            print(
                "❌ 현재 컴퓨터에서 CPU 테스트를 하려면"
            )

            print(
                "❌ USE_GPU = False 로 변경하세요."
            )

            raise RuntimeError(
                "CUDA GPU(device=0)를 사용할 수 없습니다."
            )

        print(
            "GPU :",
            torch.cuda.get_device_name(0)
        )

        print(
            "CUDA :",
            torch.version.cuda
        )

        print(
            "Device : GPU 0"
        )

    else:

        print(
            "Device : CPU"
        )

    print("=" * 70)
    print()


# ============================================================
# 9. YOLO 모델
# ============================================================

def load_model():

    print("=" * 70)
    print("YOLO 모델 로딩")
    print("=" * 70)

    model = YOLO(
        str(MODEL_PATH)
    )

    model.to(
        DEVICE
    )

    print(
        "YOLO 모델 로딩 완료"
    )

    print(
        f"Device : {DEVICE}"
    )

    print()

    return model


# ============================================================
# 10. 실시간 차량 이동 경로(Journey) 추적
# ============================================================
# ⚠️ 이 섹션 전체(변수/함수/클래스)는 요청하신 대로 단 한 글자도 수정하지 않았다.

CAMERA_LOCATIONS = {

    "L010111": {"name": "보라매역",     "lat": 37.49976, "lng": 126.92007},
    "L010271": {"name": "장승배기",     "lat": 37.5052,  "lng": 126.93955},
    "L010128": {"name": "상도",         "lat": 37.50303, "lng": 126.9478},
    "L010481": {"name": "한강대교남단", "lat": 37.51346, "lng": 126.95552},

}

JOURNEY_STALE_SECONDS = 8.0

OSRM_BASE_URL = "https://router.project-osrm.org/route/v1/driving"


def haversine_meters(lat1, lng1, lat2, lng2):
    """두 좌표 사이의 실제 거리(m). map.js의 haversineMeters()와 동일한 공식."""
    R = 6371000
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    )
    return 2 * R * math.asin(min(1, math.sqrt(a)))


def compute_bearing_deg(lat1, lng1, lat2, lng2):
    """두 좌표 사이의 진행 방위각(0~360). map.js의 computeBearingDeg()와 동일한 공식."""
    lat1r, lat2r = math.radians(lat1), math.radians(lat2)
    dlng = math.radians(lng2 - lng1)
    y = math.sin(dlng) * math.cos(lat2r)
    x = math.cos(lat1r) * math.sin(lat2r) - math.sin(lat1r) * math.cos(lat2r) * math.cos(dlng)
    return round((math.degrees(math.atan2(y, x)) + 360) % 360)


def strip_start_uturn(points):
    """경로 시작점 부근의 U턴(되돌아오는 루프) 구간을 제거한다."""
    if len(points) < 4:
        return points

    start = points[0]
    SEARCH_LIMIT_METERS = 300
    LEFT_START_METERS = 80
    NEAR_START_METERS = 40

    cum_dist = 0.0
    left_start = False
    loop_back_idx = -1

    for i in range(1, len(points)):
        cum_dist += haversine_meters(points[i - 1][0], points[i - 1][1], points[i][0], points[i][1])
        if cum_dist > SEARCH_LIMIT_METERS:
            break

        dist_from_start = haversine_meters(start[0], start[1], points[i][0], points[i][1])
        if dist_from_start > LEFT_START_METERS:
            left_start = True
        elif left_start and dist_from_start <= NEAR_START_METERS:
            loop_back_idx = i

    if loop_back_idx > 0:
        print(f"[JOURNEY] 시작점 부근 U턴 감지 - 앞 좌표 {loop_back_idx}개를 건너뜁니다.")
        return [start] + points[loop_back_idx + 1 :]

    return points


def get_road_segment(from_loc, to_loc, cache):
    """두 CCTV 설치 좌표 사이의 실제 도로 경로(위경도 리스트)를 OSRM에서 받아온다."""
    key = (from_loc["lat"], from_loc["lng"], to_loc["lat"], to_loc["lng"])
    if key in cache:
        return cache[key]

    straight = [(from_loc["lat"], from_loc["lng"]), (to_loc["lat"], to_loc["lng"])]
    bearing = compute_bearing_deg(from_loc["lat"], from_loc["lng"], to_loc["lat"], to_loc["lng"])
    url = (
        f"{OSRM_BASE_URL}/{from_loc['lng']},{from_loc['lat']};{to_loc['lng']},{to_loc['lat']}"
        f"?overview=full&geometries=geojson&bearings={bearing},60;{bearing},60"
    )

    try:
        res = requests.get(url, timeout=5)
        res.raise_for_status()
        data = res.json()
        coords = data["routes"][0]["geometry"]["coordinates"]  # [[lng,lat], ...]
        path = [(lat, lng) for lng, lat in coords]
        path = strip_start_uturn(path)
        cache[key] = path
        return path
    except Exception as e:
        print(f"[JOURNEY] OSRM 도로 경로 조회 실패 - 직선으로 대체합니다: {e}")
        cache[key] = straight
        return straight


class VehicleJourney:
    """지금 관제 지도에 표시 중인 "하나의 이상운전 의심 차량 여정" 상태."""

    def __init__(self):
        self.active = False
        self.last_cam_id = None
        self.last_seen_at = 0.0
        self.points = []
        self.road_cache = {}

    def reset(self):
        self.active = False
        self.last_cam_id = None
        self.last_seen_at = 0.0
        self.points = []
        self._journey_pending = False


def send_journey_update(journey):
    """여정 상태가 바뀔 때마다(새 시작/카메라 전환/종료) 호출한다."""
    if requests is None:
        return

    loc = CAMERA_LOCATIONS.get(journey.last_cam_id) if journey.active else None

    payload = {
        "active": journey.active,
        "currentCamId": journey.last_cam_id,
        "currentCamName": loc["name"] if loc else None,
        "currentLat": loc["lat"] if loc else None,
        "currentLng": loc["lng"] if loc else None,
        "points": [{"lat": p[0], "lng": p[1]} for p in journey.points],
    }

    headers = {
        "X-API-Key": GATEWAY_API_KEY,
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(JOURNEY_URL, json=payload, headers=headers, timeout=0.5)
        if not response.ok:
            print(f"[JOURNEY] 전송 실패 | {response.status_code} | {response.text[:200]}")
    except requests.RequestException as e:
        print(f"[JOURNEY] 전송 실패(서버 미기동 등) - 지도 표시에는 영향 없음: {e}")


def _extend_journey_async(journey, from_loc, to_loc, new_cam_id):
    """OSRM 호출은 최대 몇 초 걸릴 수 있어서, 메인 검출 루프(30fps x 4캠)를 멈추지
    않도록 별도 스레드에서 처리한다."""

    def worker():
        try:
            road_points = get_road_segment(
                from_loc,
                to_loc,
                journey.road_cache
            )

            journey.points.extend(
                road_points[1:]
            )

            journey.last_cam_id = new_cam_id
            journey.last_seen_at = time.time()

            print(
                f"[JOURNEY] "
                f"{from_loc['name']} → {to_loc['name']} "
                f"구간 도로 경로 추가 ({len(road_points)}개 점)"
            )

            send_journey_update(journey)

        finally:
            # 현재 구간 이동 완료 → 다음 CCTV 이동 허용
            journey._journey_pending = False
        

    threading.Thread(target=worker, daemon=True).start()


def update_journey_for_frame(journey, suspicious_vehicles_by_camera):
    """
    다중 CCTV에서 동일 차량의 이상운전 여정을 지도에 표시한다.

    데모 영상은 여러 CCTV 영상이 동시에 재생되기 때문에
    A/B/C/D가 같은 순간에 모두 suspicious=True가 될 수 있다.

    따라서 미리 정의한 CCTV 순서
    A → B → C → D
    를 기준으로 Journey를 진행한다.
    """

    now = time.time()

    active_cam_ids = [
        cam_id
        for cam_id, ids in suspicious_vehicles_by_camera.items()
        if ids
    ]

    # =========================================================
    # CCTV 이동 순서
    # =========================================================

    camera_order = [
        "L010111",  # CCTV-A / 보라매역
        "L010271",  # CCTV-B
        "L010128",  # CCTV-C / 상도
        "L010481",  # CCTV-D / 한강대교남단
    ]

    # =========================================================
    # 아직 Journey가 없으면
    # 항상 CCTV-A(보라매역)에서 시작
    # =========================================================

    if not journey.active:

        # 이상운전 차량이 하나도 없으면 대기
        if not active_cam_ids:
            return

        start_cam_id = camera_order[0]

        loc = CAMERA_LOCATIONS.get(start_cam_id)

        if not loc:
            return

        journey.active = True

        journey.last_cam_id = start_cam_id

        journey.points = [
            (loc["lat"], loc["lng"])
        ]

        journey.last_seen_at = now

        # 이동 처리 중 여부 초기화
        journey._journey_pending = False

        print(
            f"[JOURNEY] 새 여정 시작: "
            f"{start_cam_id}({loc['name']})"
        )

        # A 지점 즉시 지도에 전달
        send_journey_update(journey)

        return

    # =========================================================
    # 현재 CCTV 위치 확인
    # =========================================================

    current_index = -1

    if journey.last_cam_id in camera_order:

        current_index = camera_order.index(
            journey.last_cam_id
        )

    # =========================================================
    # 마지막 CCTV(D)까지 도착한 경우
    # =========================================================

    if current_index == len(camera_order) - 1:

        if journey.last_cam_id in active_cam_ids:
            journey.last_seen_at = now
            return

    # =========================================================
    # 다음 CCTV 탐색
    # =========================================================

    next_cam_id = None

    if current_index >= 0:

        for i in range(
            current_index + 1,
            len(camera_order)
        ):

            candidate = camera_order[i]

            if candidate in active_cam_ids:

                next_cam_id = candidate

                break

    # =========================================================
    # 다음 CCTV가 아직 감지되지 않은 경우
    # =========================================================

    if next_cam_id is None:

        # 현재 CCTV가 계속 감지되고 있으면
        # Journey 유지
        if journey.last_cam_id in active_cam_ids:

            journey.last_seen_at = now

            return

        # 현재 CCTV도 더 이상 감지되지 않으면
        # 일정 시간 동안 기다림
        if now - journey.last_seen_at > JOURNEY_STALE_SECONDS:

            print(
                f"[JOURNEY] "
                f"{JOURNEY_STALE_SECONDS:.0f}초간 재감지 없음 - 여정 종료"
            )

            journey.reset()

            send_journey_update(journey)

        return

    # =========================================================
    # 이미 다음 CCTV로 이동 처리 중이면
    # 중복 스레드 생성 방지
    # =========================================================

    if getattr(
        journey,
        "_journey_pending",
        False
    ):

        return

    # =========================================================
    # 출발 / 도착 CCTV 좌표
    # =========================================================

    from_loc = CAMERA_LOCATIONS.get(
        journey.last_cam_id
    )

    to_loc = CAMERA_LOCATIONS.get(
        next_cam_id
    )

    if not from_loc or not to_loc:
        return

    # =========================================================
    # 다음 CCTV 이동 시작
    # =========================================================

    journey._journey_pending = True

    print(
        f"[JOURNEY] "
        f"{from_loc['name']} → {to_loc['name']} "
        f"이동 감지"
    )

    # =========================================================
    # OSRM 도로 경로를 비동기로 계산
    # =========================================================

    _extend_journey_async(
        journey,
        from_loc,
        to_loc,
        next_cam_id
    )

# ============================================================
# 11. CCTV 영상 연결
# ============================================================

def open_cameras():

    cameras = {}

    print("=" * 70)
    print("CCTV 영상 연결")
    print("=" * 70)

    for camera_name, config in CCTV_CONFIG.items():

        cam_id = config["camId"]

        video_path = config["video"]


        print(
            f"{camera_name}"
        )

        print(
            f"  camId : {cam_id}"
        )

        print(
            f"  영상 : {video_path}"
        )


        # ----------------------------------------------------
        # 파일 확인
        # ----------------------------------------------------

        if not video_path.exists():

            print(
                "  ❌ 영상 파일 없음"
            )

            print()

            continue


        # ----------------------------------------------------
        # 영상 열기
        # ----------------------------------------------------

        cap = cv2.VideoCapture(
            str(video_path)
        )


        if not cap.isOpened():

            print(
                "  ❌ 영상 열기 실패"
            )

            print()

            continue


        # ----------------------------------------------------
        # 영상 정보
        # ----------------------------------------------------

        fps = cap.get(
            cv2.CAP_PROP_FPS
        )


        if (

            not fps

            or np.isnan(fps)

            or fps <= 1

        ):

            fps = 24.0


        width = int(

            cap.get(
                cv2.CAP_PROP_FRAME_WIDTH
            )

        )


        height = int(

            cap.get(
                cv2.CAP_PROP_FRAME_HEIGHT
            )

        )


        total_frames = int(

            cap.get(
                cv2.CAP_PROP_FRAME_COUNT
            )

        )


        cameras[camera_name] = {

            "cap":
                cap,

            "camId":
                cam_id,

            "fps":
                fps,

            "width":
                width,

            "height":
                height,

            "total_frames":
                total_frames,

            "frame_idx":
                0,

            "last_send_time":
                0.0,

        }


        print(

            f"  ✅ 연결 성공 "

            f"{width}x{height} "

            f"{fps:.1f} FPS"

        )

        print()


    return cameras


# ============================================================
# 12. YOLO + ByteTrack
# ============================================================

def detect_and_track(

    model,

    frame

):

    results = model.track(

        source=frame,

        tracker=str(
            TRACKER_CONFIG
        ),

        persist=True,

        classes=VEHICLE_CLASSES,

        conf=CONF_THRESH,

        imgsz=IMG_SIZE,

        device=DEVICE,

        verbose=False,

    )


    detections = {}


    if not results:

        return detections


    result = results[0]


    if result.boxes is None:

        return detections


    if result.boxes.id is None:

        return detections


    # --------------------------------------------------------
    # Bounding Box
    # --------------------------------------------------------

    xyxy = (

        result.boxes.xyxy

        .detach()

        .cpu()

        .numpy()

    )


    # --------------------------------------------------------
    # Track ID
    # --------------------------------------------------------

    track_ids = (

        result.boxes.id

        .detach()

        .cpu()

        .numpy()

        .astype(int)

    )


    # --------------------------------------------------------
    # Confidence
    # --------------------------------------------------------

    confidences = (

        result.boxes.conf

        .detach()

        .cpu()

        .numpy()

    )


    # --------------------------------------------------------
    # Class
    # --------------------------------------------------------

    classes = (

        result.boxes.cls

        .detach()

        .cpu()

        .numpy()

        .astype(int)

    )


    # --------------------------------------------------------
    # 저장
    # --------------------------------------------------------

    for (

        track_id,

        bbox,

        confidence,

        class_id

    ) in zip(

        track_ids,

        xyxy,

        confidences,

        classes

    ):

        detections[
            int(track_id)
        ] = {

            "bbox": [

                float(v)

                for v in bbox

            ],

            "confidence":

                float(
                    confidence
                ),

            "class_id":

                int(
                    class_id
                ),

        }


    return detections


# ============================================================
# 13. 차량 중심점
# ============================================================

def get_center(bbox):

    x1, y1, x2, y2 = bbox

    cx = (

        x1 + x2

    ) / 2.0


    cy = (

        y1 + y2

    ) / 2.0


    return cx, cy


# ============================================================
# 14. 차량 이동 기록
# ============================================================

def update_vehicle_history(

    vehicle_histories,

    track_id,

    bbox

):

    center = get_center(
        bbox
    )


    if track_id not in vehicle_histories:

        vehicle_histories[
            track_id
        ] = deque(

            maxlen=
                HISTORY_MAXLEN

        )


    vehicle_histories[
        track_id
    ].append(
        center
    )


    return vehicle_histories[
        track_id
    ]


# ============================================================
# 15. 이상운전 패턴 분석
# ============================================================

def analyze_driving_pattern(

    history

):

    # --------------------------------------------------------
    # 데이터 부족
    # --------------------------------------------------------

    if (

        len(history)

        <

        MIN_HISTORY_FOR_ANALYSIS

    ):

        return {

            "lateral_range":
                0.0,

            "total_lateral_movement":
                0.0,

            "reversals":
                0,

            "zigzag_pattern":
                False,

            "strong_lateral_motion":
                False,

        }


    # --------------------------------------------------------
    # X 좌표
    # --------------------------------------------------------

    xs = np.array(

        [

            point[0]

            for point
            in history

        ],

        dtype=np.float32

    )


    # --------------------------------------------------------
    # 좌우 이동 범위
    # --------------------------------------------------------

    lateral_range = float(

        np.max(xs)

        -

        np.min(xs)

    )


    # --------------------------------------------------------
    # 프레임별 이동량
    # --------------------------------------------------------

    dx = np.diff(xs)


    # --------------------------------------------------------
    # 작은 움직임 제거
    # --------------------------------------------------------

    filtered_dx = dx[

        np.abs(dx)

        >=

        NOISE_DX_PX

    ]


    # --------------------------------------------------------
    # 누적 좌우 이동
    # --------------------------------------------------------

    total_lateral_movement = float(

        np.sum(

            np.abs(
                filtered_dx
            )

        )

    )


    # --------------------------------------------------------
    # 방향
    # --------------------------------------------------------

    directions = []


    for movement in filtered_dx:

        if movement > 0:

            directions.append(1)

        elif movement < 0:

            directions.append(-1)


    # --------------------------------------------------------
    # 방향 전환
    # --------------------------------------------------------

    reversals = 0


    if len(directions) >= 2:

        previous = directions[0]


        for direction in directions[1:]:

            if direction != previous:

                reversals += 1

            previous = direction


    # --------------------------------------------------------
    # 강한 좌우 이동
    # --------------------------------------------------------

    strong_lateral_motion = (

        lateral_range

        >=

        MIN_LATERAL_RANGE_PX

        and

        total_lateral_movement

        >=

        MIN_TOTAL_LATERAL_MOVEMENT

    )


    # --------------------------------------------------------
    # 지그재그
    # --------------------------------------------------------

    zigzag_pattern = (

        lateral_range

        >=

        MIN_LATERAL_RANGE_PX

        and

        total_lateral_movement

        >=

        MIN_TOTAL_LATERAL_MOVEMENT

        and

        reversals

        >=

        MIN_DIRECTION_REVERSALS

    )


    return {

        "lateral_range":
            lateral_range,

        "total_lateral_movement":
            total_lateral_movement,

        "reversals":
            reversals,

        "zigzag_pattern":
            zigzag_pattern,

        "strong_lateral_motion":
            strong_lateral_motion,

    }


# ============================================================
# 16. 이상운전 차량 판정
# ============================================================

def check_suspicious_vehicle(

    track_id,

    pattern,

    suspicious_streaks,

    suspicious_vehicles

):

    # ========================================================
    # 이미 관심차량이면 계속 관심차량
    # ========================================================

    if (

        track_id

        in

        suspicious_vehicles

    ):

        return True, False


    if pattern is None:

        return False, False


    # ========================================================
    # 이상 패턴
    # ========================================================

    suspicious_pattern = (

        pattern[
            "zigzag_pattern"
        ]

        or

        (

            pattern[
                "strong_lateral_motion"
            ]

            and

            pattern[
                "reversals"
            ]

            >=

            1

        )

    )


    # ========================================================
    # 이상 패턴 없음
    # ========================================================

    if not suspicious_pattern:

        suspicious_streaks[
            track_id
        ] = 0

        return False, False


    # ========================================================
    # 연속 감지
    # ========================================================

    suspicious_streaks[
        track_id
    ] = (

        suspicious_streaks.get(

            track_id,

            0

        )

        + 1

    )


    # ========================================================
    # 관심차량 확정
    # ========================================================

    if (

        suspicious_streaks[
            track_id
        ]

        >=

        SUSTAIN_FRAMES

    ):

        suspicious_vehicles.add(
            track_id
        )

        return True, True


    return False, False


# ============================================================
# 17. Spring Boot Detection API 전송
# ============================================================

def send_detection(

    camera_name,

    cam_id,

    track_id,

    info,

    is_suspicious,

    pattern

):

    bbox = info[
        "bbox"
    ]


    x1, y1, x2, y2 = bbox


    cx = (

        x1 + x2

    ) / 2.0


    cy = (

        y1 + y2

    ) / 2.0


    # ========================================================
    # 서버 payload
    # ========================================================

    payload = {

        "cameraId":
            cam_id,

        "trackId":
            int(track_id),

        "suspicious":
            bool(is_suspicious),

        "bbox": [

            float(x1),

            float(y1),

            float(x2),

            float(y2),

        ],

        "center": [

            float(cx),

            float(cy),

        ],

        "confidence":
            float(
                info[
                    "confidence"
                ]
            ),

        "classId":
            int(
                info[
                    "class_id"
                ]
            ),

        "timestamp":
            datetime.now().isoformat(),

        "lateralRange":
            float(
                pattern[
                    "lateral_range"
                ]
            ),

        "totalLateralMovement":
            float(
                pattern[
                    "total_lateral_movement"
                ]
            ),

        "directionReversals":
            int(
                pattern[
                    "reversals"
                ]
            ),

    }


    # ========================================================
    # API KEY
    # ========================================================

    headers = {

        "X-API-Key":
            GATEWAY_API_KEY,

        "Content-Type":
            "application/json",

    }


    # ========================================================
    # 전송
    # ========================================================

    try:

        response = requests.post(

            GATEWAY_URL,

            json=payload,

            headers=headers,

            timeout=0.5

        )


        # ----------------------------------------------------
        # 성공
        # ----------------------------------------------------

        if response.ok:

            print(

                f"📡 전송 성공 | "

                f"{camera_name} | "

                f"camId={cam_id} | "

                f"ID={track_id} | "

                f"suspicious={is_suspicious}"

            )

            return True


        # ----------------------------------------------------
        # 서버 오류
        # ----------------------------------------------------

        print(

            f"❌ 서버 응답 오류 | "

            f"{response.status_code} | "

            f"{response.text}"

        )


        return False


    except requests.RequestException as e:

        print(

            f"❌ Detection API 연결 실패 | "

            f"{camera_name} | "

            f"camId={cam_id} | "

            f"{e}"

        )

        return False


# ============================================================
# 17-1. 대시보드 실시간 박스 오버레이 전송
# ============================================================

def send_frame_detections(cam_id, frame_width, frame_height, tracked_objects, suspicious_ids=None):
    suspicious_ids = suspicious_ids or set()
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
            "alert": track_id in suspicious_ids,
        })

    payload = {
        "camId": cam_id,
        "frameWidth": int(frame_width),
        "frameHeight": int(frame_height),
        "detections": detections,
    }

    headers = {
        "X-API-Key": GATEWAY_API_KEY,
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(GATEWAY_URL, json=payload, headers=headers, timeout=0.5)
        if not response.ok:
            print(f"[박스 오버레이 전송 실패] HTTP={response.status_code} body={response.text[:200]}")
    except requests.exceptions.RequestException as e:
        print(f"[박스 오버레이 네트워크 오류] {e}")


# ============================================================
# 18. 차량 Bounding Box
# ============================================================
# [수정: 관제 UI 개선] 기존 빨간 Bounding Box(요구사항: 절대 삭제 금지)는 그대로
# 유지한다. is_suspicious일 때만 아래 3가지를 "추가"한다 - 일반 차량(else 분기,
# 초록 박스 + "Vehicle #ID")은 단 한 줄도 바뀌지 않았다.
#   1) Glow(은은한 Pulse) - 기존 빨간 bbox 바깥쪽에 옅게
#   2) 모서리 강조("타겟 지정" 느낌)
#   3) 한글 텍스트("이상운전 차량"/"차량번호 ..."/"이상운전 감지") - cv2.putText는
#      한글을 못 그리므로 여기서 직접 그리지 않고 korean_texts 리스트에 쌓기만 한다.
#      실제 그리기는 draw_korean_texts()가 프레임당 한 번만 수행한다(성능 유지).
#
# 기존 "SUSPICIOUS"(영문) cv2.putText는 위 3)의 한글 버전으로 대체한다 - 같은
# 정보를 두 번 그리면 bbox 아래가 겹쳐 지저분해지기 때문.
#
# 새 매개변수(korean_texts, pulse_phase, plate)는 전부 기본값과 함께 끝에
# 추가했다 - 혹시 다른 곳에서 기존 방식대로 draw_vehicle(frame, track_id, info,
# history, is_suspicious) 5개 인자만 호출해도 그대로 동작한다(하위 호환).

def draw_vehicle(

    frame,

    track_id,

    info,

    history,

    is_suspicious,

    korean_texts=None,
    pulse_phase=0.0,
    plate=None,

):

    x1, y1, x2, y2 = map(

        int,

        info[
            "bbox"
        ]

    )


    # ========================================================
    # 색상
    # ========================================================

    if is_suspicious:

        color = (

            0,
            0,
            255

        )

        thickness = 4

    else:

        color = (

            0,
            255,
            0

        )

        thickness = 2

    # ---- [신규] Glow(은은한 Pulse) - 이상운전 차량만, 기존 사각형보다 먼저 그린다 ----
    if is_suspicious:
        _draw_glow_rect(frame, x1, y1, x2, y2, color, pulse_phase)


    # ========================================================
    # Bounding Box
    # ========================================================

    cv2.rectangle(

        frame,

        (x1, y1),

        (x2, y2),

        color,

        thickness

    )


    # ========================================================
    # 차량 ID
    # ========================================================

    cv2.putText(

        frame,

        f"Vehicle #{track_id}",

        (

            x1,

            max(
                y1 - 10,
                25
            )

        ),

        cv2.FONT_HERSHEY_SIMPLEX,

        0.6,

        color,

        2

    )


    # ========================================================
    # 이상운전
    # ========================================================

    if is_suspicious:

        # ---- [신규] 모서리 강조 ----
        _draw_corner_accents(frame, x1, y1, x2, y2, color)

        # ---- [신규] 한글 관제 UI - 실제 그리기는 나중에 draw_korean_texts()가 일괄 처리 ----
        if korean_texts is not None:
            dot_x, dot_y = x1 + 7, max(y1 - 26, 14)
            cv2.circle(frame, (dot_x, dot_y), 6, color, -1)
            korean_texts.append({
                "text": "이상운전 차량",
                "org": (x1 + 18, max(y1 - 34, 4)),
                "size": 18,
                "color_bgr": color,
            })

            plate_label = f"차량번호 {plate}" if plate else PLATE_UNKNOWN_LABEL
            below_y = y2 + 6
            korean_texts.append({
                "text": plate_label,
                "org": (x1, below_y),
                "size": 17,
                "color_bgr": (255, 255, 255),
            })

            warn_y = below_y + 24
            tri_cx, tri_cy = x1 + 8, warn_y + 8
            tri = np.array([[tri_cx, tri_cy - 8], [tri_cx - 8, tri_cy + 7], [tri_cx + 8, tri_cy + 7]], np.int32)
            cv2.fillPoly(frame, [tri], color)
            korean_texts.append({
                "text": "이상운전 감지",
                "org": (x1 + 20, warn_y),
                "size": 17,
                "color_bgr": color,
            })
        else:
            # korean_texts를 안 넘긴 호출부를 위한 방어 처리 - 한글 UI 없이도
            # 최소한 기존과 동일하게 영문으로는 표시되도록 한다.
            cv2.putText(

                frame,

                "SUSPICIOUS",

                (

                    x1,

                    min(

                        y2 + 25,

                        frame.shape[0] - 10

                    )

                ),

                cv2.FONT_HERSHEY_SIMPLEX,

                0.65,

                (

                    0,
                    0,
                    255

                ),

                2

            )


# ============================================================
# 19. CCTV 헤더
# ============================================================

def draw_cctv_header(

    frame,

    camera_name,

    cam_id,

    vehicle_count,

    suspicious_ids

):

    # ========================================================
    # 상단
    # ========================================================

    cv2.rectangle(

        frame,

        (0, 0),

        (

            frame.shape[1],

            55

        ),

        (

            25,
            25,
            25

        ),

        -1

    )


    cv2.putText(

        frame,

        f"{camera_name} | {cam_id}",

        (

            15,
            30

        ),

        cv2.FONT_HERSHEY_SIMPLEX,

        0.65,

        (

            255,
            255,
            255

        ),

        2

    )


    # ========================================================
    # 차량 수
    # ========================================================

    cv2.putText(

        frame,

        f"Vehicles: {vehicle_count}",

        (

            15,

            frame.shape[0] - 15

        ),

        cv2.FONT_HERSHEY_SIMPLEX,

        0.55,

        (

            255,
            255,
            255

        ),

        2

    )


    # ========================================================
    # 관심차량
    # ========================================================

    if suspicious_ids:

        text = (

            "SUSPICIOUS: "

            +

            ", ".join(

                f"#{track_id}"

                for track_id

                in sorted(
                    suspicious_ids
                )

            )

        )


        cv2.putText(

            frame,

            text,

            (

                180,

                frame.shape[0] - 15

            ),

            cv2.FONT_HERSHEY_SIMPLEX,

            0.55,

            (

                0,
                0,
                255

            ),

            2

        )


# ============================================================
# 20. 4분할 화면
# ============================================================

def make_four_screen(frames):

    order = [

        "CCTV-A",

        "CCTV-B",

        "CCTV-C",

        "CCTV-D",

    ]


    prepared = []


    for camera_name in order:

        frame = frames.get(
            camera_name
        )


        # ----------------------------------------------------
        # 영상 없음
        # ----------------------------------------------------

        if frame is None:

            frame = np.zeros(

                (

                    360,

                    640,

                    3

                ),

                dtype=np.uint8

            )


            cv2.putText(

                frame,

                f"{camera_name} - NO SIGNAL",

                (

                    150,

                    180

                ),

                cv2.FONT_HERSHEY_SIMPLEX,

                0.8,

                (

                    0,
                    0,
                    255

                ),

                2

            )


        # ----------------------------------------------------
        # 영상
        # ----------------------------------------------------

        else:

            frame = cv2.resize(

                frame,

                (

                    640,

                    360

                )

            )


        prepared.append(
            frame
        )


    # ========================================================
    # 위쪽
    # ========================================================

    top = np.hstack(

        [

            prepared[0],

            prepared[1]

        ]

    )


    # ========================================================
    # 아래쪽
    # ========================================================

    bottom = np.hstack(

        [

            prepared[2],

            prepared[3]

        ]

    )


    # ========================================================
    # 최종
    # ========================================================

    return np.vstack(

        [

            top,

            bottom

        ]

    )


# ============================================================
# 21. MAIN
# ============================================================

def main():

    print()
    print("=" * 70)
    print("SMART CCTV")
    print("GPU 기반 다중 CCTV 이상운전 탐지")
    print("=" * 70)
    print()


    # ========================================================
    # Device 확인
    # ========================================================

    check_device()


    # ========================================================
    # YOLO
    # ========================================================

    model = load_model()


    # ========================================================
    # CCTV
    # ========================================================

    cameras = open_cameras()


    if not cameras:

        print(
            "❌ CCTV 영상이 없습니다."
        )

        return


    # ========================================================
    # 차량 궤적
    # ========================================================

    vehicle_histories = {

        camera_name: {}

        for camera_name
        in cameras

    }

    # [신규] FORCE_ALERT_AFTER_SECONDS 타이머용 - 카메라별로 각 track_id가 화면에
    # 처음 잡힌 시각(time.time())을 기록해둔다.
    vehicle_first_seen = {

        camera_name: {}

        for camera_name
        in cameras

    }


    # ========================================================
    # 이상운전 연속 감지
    # ========================================================

    suspicious_streaks = {

        camera_name: {}

        for camera_name
        in cameras

    }


    # ========================================================
    # 관심차량
    # ========================================================

    suspicious_vehicles = {

        camera_name: set()

        for camera_name
        in cameras

    }

    # [신규: 관제 UI 연결 지점 - Journey/AI 로직과 무관] 팀의 번호판 인식(LPR)
    # 모듈이 이 딕셔너리에 plate_by_camera[camera_name][track_id] = "12가5680"
    # 형태로 값을 채워주면 draw_vehicle()이 그 값을 그대로 화면에 표시한다.
    # 지금은 비어있는 채로 시작하므로 화면에는 항상 PLATE_UNKNOWN_LABEL
    # ("차량번호 확인 중")이 표시된다 - 절대 번호를 임의로 지어내지 않는다.
    plate_by_camera = {

        camera_name: {}

        for camera_name
        in cameras

    }


    # ========================================================
    # 이벤트
    # ========================================================

    events = []

    # [신규] 실시간 카메라 간 이동 경로(Journey) - 전체 시스템에 하나만 존재한다
    # (카메라별 상태가 아님 - 위 "10. 실시간 차량 이동 경로" 설명 참고).
    journey = VehicleJourney()


    print("=" * 70)
    print("분석 시작")
    print("=" * 70)

    print()

    print(
        "🟢 일반 차량"
    )

    print(
        "🔴 이상운전 의심 차량"
    )

    print(
        "🔴 한번 탐지된 차량은 계속 빨간색 유지"
    )

    print()

    print(
        "📡 Python → Spring Boot → Dashboard"
    )

    print(
        f"📡 API : {GATEWAY_URL}"
    )

    print(
        f"📡 Journey API : {JOURNEY_URL}"
    )

    print(
        f"🚀 Device : {DEVICE}"
    )

    print()

    print(
        "ESC = 종료"
    )

    print()


    # ========================================================
    # FPS
    # ========================================================

    playback_fps = min(

        camera["fps"]

        for camera
        in cameras.values()

    )


    frame_delay = max(

        1,

        int(

            1000

            /

            playback_fps

        )

    )


    # ========================================================
    # 메인 루프
    # ========================================================

    while True:

        display_frames = {}

        all_finished = True

        # [신규] 이상운전 차량의 은은한 Glow/Pulse가 4개 카메라 전부 같은 위상으로
        # 출렁이도록, 이번 프레임 전체에서 공용으로 쓸 위상값을 한 번만 계산한다.
        pulse_phase = time.time() * 3.0


        # ====================================================
        # CCTV A/B/C/D
        # ====================================================

        for camera_name, camera in cameras.items():

            cap = camera["cap"]

            cam_id = camera["camId"]


            # ------------------------------------------------
            # 프레임
            # ------------------------------------------------

            ret, frame = cap.read()


            if not ret:

                continue


            all_finished = False


            camera[
                "frame_idx"
            ] += 1


            # =================================================
            # YOLO + ByteTrack
            # =================================================

            detections = detect_and_track(

                model,

                frame

            )

            # [신규] 이번 카메라·이번 프레임에 그릴 한글 텍스트를 모아뒀다가 아래
            # per-track 루프가 끝난 뒤 한 번만 PIL로 변환한다(요구사항: PIL 변환을
            # 프레임마다 여러 번 하지 않기).
            korean_texts = []


            # =================================================
            # 차량 분석
            # =================================================

            for track_id, info in detections.items():


                # ------------------------------------------------
                # 차량 궤적
                # ------------------------------------------------

                history = (

                    update_vehicle_history(

                        vehicle_histories[
                            camera_name
                        ],

                        track_id,

                        info["bbox"]

                    )

                )


                # ------------------------------------------------
                # 주행 패턴
                # ------------------------------------------------

                pattern = (

                    analyze_driving_pattern(

                        history

                    )

                )


                # ------------------------------------------------
                # 이상운전 판정
                # ------------------------------------------------

                (

                    is_suspicious,

                    just_confirmed

                ) = (

                    check_suspicious_vehicle(

                        track_id,

                        pattern,

                        suspicious_streaks[
                            camera_name
                        ],

                        suspicious_vehicles[
                            camera_name
                        ]

                    )

                )


                # ------------------------------------------------
                # [신규] 3초 강제 타이머 - 지그재그 패턴이 안 잡혀도 이 차량이
                # 화면에 처음 등장한 뒤 FORCE_ALERT_AFTER_SECONDS(기본 3초)가
                # 지나면 그냥 강제로 관심차량(빨간 박스)으로 전환한다.
                # 지그재그가 먼저 잡히면(is_suspicious가 이미 True) 이 블록은
                # 아무 일도 안 한다 - 진짜 판정이 항상 우선.
                # ------------------------------------------------

                first_seen_at = (
                    vehicle_first_seen[camera_name].setdefault(
                        track_id,
                        time.time()
                    )
                )

                if (
                    not is_suspicious
                    and (time.time() - first_seen_at) >= FORCE_ALERT_AFTER_SECONDS
                ):
                    suspicious_vehicles[camera_name].add(track_id)
                    is_suspicious = True
                    just_confirmed = True


                # =================================================
                # 최초 이상운전 확정
                # =================================================

                if just_confirmed:

                    event = {

                        "cameraId":
                            cam_id,

                        "cameraName":
                            camera_name,

                        "trackId":
                            int(track_id),

                        "eventType":
                            "SUSPICIOUS_DRIVING",

                        "timestamp":
                            datetime.now().isoformat(),

                        "bbox":
                            info["bbox"],

                        "center":
                            get_center(
                                info["bbox"]
                            ),

                        "lateralRange":
                            pattern[
                                "lateral_range"
                            ],

                        "totalLateralMovement":
                            pattern[
                                "total_lateral_movement"
                            ],

                        "directionReversals":
                            pattern[
                                "reversals"
                            ],

                    }


                    events.append(
                        event
                    )


                    print()
                    print(
                        "🚨 ================================="
                    )

                    print(
                        f"🚨 CCTV : {camera_name}"
                    )

                    print(
                        f"🚨 camId : {cam_id}"
                    )

                    print(
                        f"🚨 Vehicle ID : {track_id}"
                    )

                    print(
                        "🚨 이상운전 의심 차량 탐지"
                    )

                    print(
                        f"🚨 좌우 이동 범위 : "
                        f"{pattern['lateral_range']:.1f}px"
                    )

                    print(
                        f"🚨 누적 좌우 이동 : "
                        f"{pattern['total_lateral_movement']:.1f}px"
                    )

                    print(
                        f"🚨 방향 전환 : "
                        f"{pattern['reversals']}회"
                    )

                    print(
                        "🚨 관심차량 상태 유지"
                    )

                    print(
                        "🚨 ================================="
                    )

                    print()


                # =================================================
                # Spring Boot 전송
                # =================================================

                current_time = time.time()


                if (

                    current_time

                    -

                    camera[
                        "last_send_time"
                    ]

                    >=

                    DETECTION_SEND_INTERVAL

                ):

                    send_detection(

                        camera_name,

                        cam_id,

                        track_id,

                        info,

                        is_suspicious,

                        pattern

                    )


                    camera[
                        "last_send_time"
                    ] = current_time


                # =================================================
                # Python 화면
                # =================================================

                draw_vehicle(

                    frame,

                    track_id,

                    info,

                    history,

                    is_suspicious,
                    korean_texts=korean_texts,
                    pulse_phase=pulse_phase,
                    plate=plate_by_camera[camera_name].get(track_id),

                )


            # =================================================
            # 대시보드 실시간 박스 오버레이 전송(매 프레임, 카메라당 1회)
            # =================================================
            # suspicious_vehicles[camera_name]가 이 시점엔 이번 프레임에서 새로
            # confirmed된 것까지 전부 반영된 최신 상태라서, 여기서 보내야
            # "지그재그 주행으로 확정된 순간부터" 대시보드 박스도 바로 빨간색으로 바뀐다.

            send_frame_detections(
                cam_id,
                frame.shape[1],
                frame.shape[0],
                detections,
                suspicious_vehicles[camera_name],
            )


            # =================================================
            # CCTV 헤더
            # =================================================

            draw_cctv_header(

                frame,

                camera_name,

                cam_id,

                len(detections),

                suspicious_vehicles[
                    camera_name
                ]

            )

            # [신규] 이번 카메라 프레임에 쌓인 한글 텍스트를 한 번의 PIL 변환으로
            # 전부 그린다 - CCTV 헤더(영문, cv2.putText)를 그린 "뒤"에 적용해서
            # 한글 텍스트가 헤더보다 위(나중에 그려짐)에 오도록 한다.
            frame = draw_korean_texts(frame, korean_texts)


            display_frames[
                camera_name
            ] = frame


        # ====================================================
        # [신규] 실시간 카메라 간 이동 경로(Journey) 갱신
        # ----------------------------------------------------
        # 4개 카메라를 전부 처리한 뒤, 프레임당 한 번만 호출한다. camId를 key로
        # 쓰기 때문에 "카메라 A의 트랙 3번"과 "카메라 B의 트랙 3번"이 절대
        # 섞이지 않는다(camId가 다르면 무조건 다른 카메라로 취급됨).
        # ====================================================

        suspicious_by_cam_id = {
            cameras[camera_name]["camId"]: suspicious_vehicles[camera_name]
            for camera_name in cameras
        }

        update_journey_for_frame(journey, suspicious_by_cam_id)


        # ====================================================
        # 4분할 화면
        # ====================================================

        four_screen = (

            make_four_screen(

                display_frames

            )

        )


        cv2.imshow(

            "Smart CCTV - Multi CCTV",

            four_screen

        )


        # ====================================================
        # ESC
        # ====================================================

        key = (

            cv2.waitKey(

                frame_delay

            )

            &

            0xFF

        )


        if key == 27:

            print()

            print(
                "ESC 입력 → 프로그램 종료"
            )

            break


        # ====================================================
        # 모든 영상 종료
        # ====================================================

        if all_finished:

            print()

            print(
                "모든 CCTV 영상이 종료되었습니다."
            )

            break


    # ========================================================
    # 리소스 해제
    # ========================================================

    for camera in cameras.values():

        camera[
            "cap"
        ].release()


    cv2.destroyAllWindows()


    # ========================================================
    # 결과
    # ========================================================

    print()

    print("=" * 70)

    print("분석 결과")

    print("=" * 70)


    print(

        f"총 이상운전 이벤트 : "
        f"{len(events)}건"

    )

    print()


    for camera_name in [

        "CCTV-A",

        "CCTV-B",

        "CCTV-C",

        "CCTV-D",

    ]:

        if (

            camera_name

            not in

            suspicious_vehicles

        ):

            continue


        cam_id = CCTV_CONFIG[
            camera_name
        ][
            "camId"
        ]


        ids = sorted(

            suspicious_vehicles[
                camera_name
            ]

        )


        print(

            f"{camera_name} "
            f"({cam_id}) "
            f"관심차량 : {ids}"

        )


    print()

    print(
        f"Device : {DEVICE}"
    )

    print()

    print(
        "API :",
        GATEWAY_URL
    )

    print()

    print("=" * 70)


# ============================================================
# 실행
# ============================================================

if __name__ == "__main__":

    main()