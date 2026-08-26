import os

# [환경] Windows + conda 환경에서 torch/numpy(MKL)와 OpenCV 등이 각자 자기
# OpenMP 런타임(libiomp5md.dll)을 들고 들어와서 충돌하는 경우가 있다
# ("OMP: Error #15: Initializing libiomp5md.dll, but found ... already
# initialized"). 이 스크립트는 멀티스레드 수치 연산 결과의 미세한 오차가
# 문제될 상황이 아니라서(순차적으로 YOLO 추론 -> OCR -> 후처리), 아래처럼
# 허용해도 안전하다 - Intel 공식 에러 메시지가 권장하는 우회법이기도 하다.
# cv2/numpy/torch를 import하기 "전에" 설정해야 의미가 있다.
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import cv2
import time
import math
import threading
import requests
import uuid

from collections import deque
from datetime import datetime
from pathlib import Path

import numpy as np
import torch
from dotenv import load_dotenv
from ultralytics import YOLO
from PIL import Image, ImageDraw, ImageFont
from lpr_bridge import PlateReader


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
TARGETS_URL = _GATEWAY_HOST_ONLY + "/api/targets"

# [테스트용] easyocr 미설치라 실제 OCR이 안 될 때, 매칭->Journey 파이프라인만
# 먼저 검증하기 위한 스위치. True로 두면 진짜 영상 번호판 대신 아래 풀에서
# 무작위로 고른 값이 "인식된 번호판"으로 나온다 (콘솔에 [LPR-TEST]로 어떤
# 차량에 어떤 번호가 붙었는지 찍어준다 - 그 번호를 관심 대상으로 등록하면 됨).
# easyocr 설치(pip install easyocr torch) 후에는 False로 되돌리면 된다.
LPR_TEST_MOCK = False
# 풀을 1개만 둔 이유: d_lpr의 다수결 확정(TrackVote, vote_window=5)이 최근 5번
# 인식 중 80% 이상 같은 값이어야 확정되는데, 무작위로 여러 개 중에서 고르면
# 우연히 4/5가 같은 값이 나올 때까지 오래 걸린다(테스트 목적엔 너무 느림).
# 1개만 넣으면 거의 즉시 확정된다 - 대신 카메라에 잡히는 차량 전부가 이
# 번호판으로 "인식"된다(진짜 OCR이 아니라 배선 확인용이라는 점 유의).
LPR_TEST_MOCK_PLATES = ["12가3456"]

# [신규: "test_suspicious_driving.py를 돌려도 대시보드 이벤트 리스트/화면 중앙 알림
# 팝업/PDF 리포트가 하나도 안 뜬다"] 지금까지 이 스크립트는 JOURNEY_URL(지도 위 차량
# 이동/팝업)과 GATEWAY_URL(CCTV 화면의 초록/빨강 박스 오버레이)에만 데이터를 보냈다.
# 그런데 대시보드의 "이벤트" 리스트·화면 중앙 알림 팝업·PDF 리포트는 전부 세 번째로
# 완전히 별개인 "공통 이벤트 스키마"(b_gateway의 POST /api/events, b_dashboard의
# useEventSocket이 구독)로만 굴러간다 - 이 스크립트가 여태 그 endpoint를 호출한 적이
# 없어서, 실제 음주운전 판정이 지도/CCTV 화면엔 보여도 이벤트 리스트·알림 팝업·리포트
# 쪽에서는 존재 자체를 몰랐다. 아래 EVENTS_URL/send_ai_event()가 그 빠진 연결을 채운다.
EVENTS_URL = _GATEWAY_HOST_ONLY + "/api/events"

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
# [수정: "음주운전이랑 관심대상은 서로 다른, 완전히 별개의 기능이다 - 하나로
# 합쳐서 우선순위로 고르는 게 아니라 둘 다 동시에 따로 동작해야 한다"] 이전
# 버전은 두 트리거를 하나의 공유 Journey/카메라 경로에 합쳐서 "같은 프레임에
# 겹치면 음주운전 우선"으로 처리했는데, 이는 잘못된 설계였다 - 실제로는:
#   - 음주운전(DUI): 보라매역 → 장승배기 → 상도 → 한강대교남단, 실시간 폴리라인
#     그리기만 하고 사각지대/재등장 연출 없음 (REAL_JOURNEY_LOGIC.md 확정본).
#   - 관심 대상(TARGET): 이대역 → 신촌 → (동교동삼거리, 사각지대) → 합정역 →
#     양화대교북단, 동교동삼거리에서 마커가 사라졌다가 5초 후 합정역에서
#     재등장 + 폴리라인 조금 더 그리는 연출 포함.
# 이 둘은 완전히 독립된 Journey다 - 동시에 활성 상태일 수 있고, 서로 전혀
# 간섭하지 않는다. 아래는 그래서 각자의 카메라 위치/순서를 따로 갖고, main()
# 에서 VehicleJourney 인스턴스도 dui_journey/target_journey 두 개로 따로 만든다.
# 프론트엔드(map.js)는 STOMP payload의 "reason" 필드("DUI"|"TARGET")로 어느
# 쪽 마커/폴리라인/알림 카드를 갱신할지 구분한다 - 같은 4개 camId
# (L010111/L010271/L010128/L010481)를 두 시나리오가 각자 다른 실제 장소로
# 라벨링해서 쓰는 것뿐이므로(같은 데모 카메라 4대 영상을 재활용), 이름/좌표가
# 서로 달라도 문제없다.

DUI_CAMERA_LOCATIONS = {
    # 경로: 보라매역 -> 장승배기 -> 상도 -> 한강대교남단 (원본 음주운전 데모 경로,
    # main 브랜치 기준 - 실제 UTIC camId/좌표와 정확히 일치한다)
    "L010111": {"name": "보라매역",     "lat": 37.49976, "lng": 126.92007},
    "L010271": {"name": "장승배기",     "lat": 37.5052,  "lng": 126.93955},
    "L010128": {"name": "상도",         "lat": 37.50303, "lng": 126.9478},
    "L010481": {"name": "한강대교남단", "lat": 37.51346, "lng": 126.95552},
}
DUI_CAMERA_ORDER = list(DUI_CAMERA_LOCATIONS.keys())

TARGET_CAMERA_LOCATIONS = {
    # 경로: 이대역 -> 신촌 -> (동교동삼거리, 카메라 없음/비감지 구간) -> 합정역
    # -> 양화대교북단 (관심 대상 차량 추적 데모 경로 - 실제 UTIC camId와는 이름이
    # 어긋나 있지만, 동교동삼거리 사각지대 연출이 이 라인 기준으로 만들어져 있다)
    "L010111": {"name": "이대역",       "lat": 37.55667, "lng": 126.94583},
    "L010271": {"name": "신촌",         "lat": 37.5596,  "lng": 126.9366},
    "L010128": {"name": "합정역",       "lat": 37.54917, "lng": 126.91361},
    "L010481": {"name": "양화대교북단", "lat": 37.5462,  "lng": 126.9125},
}
TARGET_CAMERA_ORDER = list(TARGET_CAMERA_LOCATIONS.keys())

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


def get_multi_point_road_route(cam_ids, cache, camera_locations):
    """[신규: 사용자 요청 - "폴리라인이 도로 위에 완벽하게 그려져서 한 번에 끝나게
    해달라, 구간별로 나눠서 그리는 로직은 다 지워달라"]

    예전엔 카메라 사이를 한 구간씩(보라매역→장승배기, 장승배기→상도, ...) 따로따로
    OSRM에 물어서 순서대로 이어붙였다. 이러면 지도 쪽에서 구간이 도착할 때마다
    차량 아이콘이 그 구간을 실제로 "운전해서 지나가는" 애니메이션을 큐에 쌓아
    재생했는데, 여러 구간이 한꺼번에 도착하면(=이 스크립트처럼 여러 카메라를 순식간에
    따라잡을 때) 그 큐가 파이썬을 이미 끈 뒤에도 한참 재생되며 이상한 지그재그
    모양으로 보이는 문제가 있었다.

    이제는 카메라 여러 대(cam_ids, CAMERA_ORDER 순서 그대로)를 OSRM "다중 경유지"
    요청 딱 한 번으로 물어서, 전체 경로를 완성된 하나의 좌표 리스트로 받는다.
    프론트엔드는 이 결과를 그대로 한 번에 그리기만 하면 되므로, 구간별 분할/애니메이션
    큐/뒤늦은 재생 문제가 원천적으로 없다.
    """
    if requests is None or len(cam_ids) < 2:
        return None

    key = tuple(cam_ids)
    if key in cache:
        return cache[key]

    locs = [camera_locations.get(cid) for cid in cam_ids]
    if any(loc is None for loc in locs):
        return None

    straight = [(loc["lat"], loc["lng"]) for loc in locs]

    coords_param = ";".join(f"{loc['lng']},{loc['lat']}" for loc in locs)
    url = f"{OSRM_BASE_URL}/{coords_param}?overview=full&geometries=geojson"

    try:
        res = requests.get(url, timeout=8)
        res.raise_for_status()
        data = res.json()
        coords = data["routes"][0]["geometry"]["coordinates"]  # [[lng,lat], ...]
        path = [(lat, lng) for lng, lat in coords]
        path = strip_start_uturn(path)
        cache[key] = path
        return path
    except Exception as e:
        print(f"[JOURNEY] OSRM 다중 경유지 경로 조회 실패 - 직선으로 대체합니다: {e}")
        cache[key] = straight
        return straight


class VehicleJourney:
    """지금 관제 지도에 표시 중인 "하나의 여정" 상태.

    [수정: "음주운전이랑 관심대상은 서로 다른, 완전히 별개의 기능이다"] 이제
    VehicleJourney 인스턴스는 처음 만들어질 때부터 자신이 어떤 시나리오인지
    (kind="DUI"|"TARGET")와 자신만의 카메라 위치/순서(camera_locations/
    camera_order)를 고정해서 갖는다 - main()에서 dui_journey/target_journey
    두 개를 따로 만들고, 서로의 상태를 절대 건드리지 않는다(우선순위/전환
    로직 없음 - 둘 다 동시에 active=True일 수 있다).
    """

    def __init__(self, kind, camera_locations, camera_order):
        self.kind = kind  # "DUI" | "TARGET" - 이 여정이 끝날 때까지 고정.
        self.camera_locations = camera_locations
        self.camera_order = camera_order

        self.active = False
        self.last_cam_id = None
        self.last_seen_at = 0.0
        self.points = []
        self.road_cache = {}
        # [수정: "DUI도 알림팝업/이벤트/PDF 리포트에 차량 번호가 나오게 해달라"]
        # 여정이 시작된 카메라에서 인식된 번호판을 저장해둔다 - TARGET은
        # target_matched_vehicles(등록된 관심 차량과 매칭된 것) 기준, DUI는
        # plate_by_camera(LPR이 인식한 아무 번호판) 기준이다. 시작 시점에
        # 아직 OCR이 안 됐으면 None으로 두고, 다음 프레임들에서 값이 생기는
        # 대로 채워 넣는다(update_journey_for_frame 참고) - 한 번 채워지면
        # 여정이 끝날 때까지 그대로 유지한다(같은 차량이므로 번호판이 바뀔 일은
        # 없음).
        self.plate = None
        # kind와 동일한 값을 그대로 담아서 send_journey_update()의 payload로
        # 내보낸다 - map.js가 payload.reason으로 알림 팝업 문구를 고른다.
        self.reason = kind
        # [신규] "카메라 지날 때마다 알림 팝업/이벤트가 계속 뜬다" - 한 여정(같은 차량이
        # 경로를 지나가는 동안) 전체를 통틀어 알림을 딱 한 번만 보내기 위한 플래그.
        # 여정이 처음 시작될 때(=첫 카메라에서 이상운전이 확정된 순간) True로 바뀌고,
        # 여정이 끝나야(reset) 다시 False가 된다. (DUI 전용 - TARGET 여정은 쓰지 않음)
        self.alert_sent = False
        # [신규: "DUI 이벤트에도 나중에 확정되는 번호판을 채워 넣게 해달라"]
        # send_ai_event()가 DUI 이벤트를 처음 만들 때 돌려주는 event_track_id를
        # 여기 저장해둔다 - 번호판이 나중에(다음 카메라에서) 확정되면
        # update_event_plate()가 이 trackId로 이미 떠 있는 그 이벤트의
        # meta.plateNumber만 채워 넣는다(TARGET은 send_ai_event를 쓰지 않으므로
        # 항상 None으로 남는다).
        self.event_track_id = None
        self._journey_pending = False

    def reset(self):
        self.active = False
        self.last_cam_id = None
        self.last_seen_at = 0.0
        self.points = []
        self.plate = None
        self.reason = self.kind
        self._journey_pending = False
        self.alert_sent = False
        self.event_track_id = None


def send_journey_update(journey):
    """여정 상태가 바뀔 때마다(새 시작/카메라 전환/종료) 호출한다."""
    if requests is None:
        return

    loc = journey.camera_locations.get(journey.last_cam_id) if journey.active else None

    payload = {
        "active": journey.active,
        "currentCamId": journey.last_cam_id,
        "currentCamName": loc["name"] if loc else None,
        "currentLat": loc["lat"] if loc else None,
        "currentLng": loc["lng"] if loc else None,
        "points": [{"lat": p[0], "lng": p[1]} for p in journey.points],
        # [신규] 알림 팝업에 차량 번호까지 표시하기 위해 전달한다. 아직 OCR로
        # 확정되지 않았으면 None - 프론트엔드(map.js)가 "차량번호 확인 중"으로
        # 대체 표시한다.
        "plate": journey.plate if journey.active else None,
        # [긴급 수정: "TARGET 여정이 끝나면 DUI 마커/폴리라인이 갑자기 지워지고
        # TARGET은 안 지워진 채로 남는다" 버그] 예전엔 journey.active가 False인
        # "여정 종료" payload에서만 reason을 None으로 보냈다. 그런데
        # map.js는 `payload.reason === "TARGET" ? "TARGET" : "DUI"`로 어느
        # 트랙(marker/폴리라인/alertManager/prevCamId)을 정리할지 판단하므로,
        # reason이 None으로 오면 실제로는 TARGET 여정이 끝난 것이어도 무조건
        # "DUI" 트랙이 정리 대상으로 오판됐다 - TARGET이 종료될 때마다 엉뚱하게
        # DUI 마커가 사라지고 DUI 폴리라인이 지워지며, 정작 TARGET 자신의
        # 마커/폴리라인/알림 카드는 하나도 정리되지 않고 화면에 남아있었다.
        # active 여부와 무관하게 reason(=journey.kind, "DUI"|"TARGET")은 항상
        # 그대로 보낸다 - 프론트엔드가 종료 payload도 정확히 자기 트랙으로
        # 라우팅할 수 있어야 한다.
        "reason": journey.reason,
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


# [신규] "이벤트/알림 팝업이 뜨는 순간 캡처 이미지도 이미 들어가 있어야 한다" -
# e_tracking/SmartCCTV/realtime_anomaly.py의 CAPTURES_DIR/save_capture()/
# frame_buffer/BEFORE_CAPTURE_SECONDS 패턴을 그대로 재사용한다(요구사항: 로직 중복
# 구현 금지). "전" 캡처는 사건 확정 직전 BEFORE_CAPTURE_SECONDS초 동안 카메라별로
# 계속 채워둔 frame_buffer의 가장 오래된 프레임, "후"는 확정된 바로 이 프레임이다.
# 예전에는 이 값들이 없어서 send_ai_event()가 frameRefBefore/frameRefAfter 없이
# 이벤트를 만들었고, 대시보드는 사용자가 이벤트 카드를 클릭해야만(브라우저 쪽
# scheduleBeforeAfterCapture) 뒤늦게 캡처를 채워 넣었다 - 그래서 알림 팝업이 뜨는
# "그 순간"에는 항상 캡처가 비어 있었다.
CAPTURES_DIR = os.path.join(
    str(BASE_DIR), "..", "..", "b_dashboard", "public", "captures"
)
os.makedirs(CAPTURES_DIR, exist_ok=True)

BEFORE_CAPTURE_SECONDS = 2.0


def save_capture(frame, source_id, tag):
    """프레임을 b_dashboard/public/captures/에 JPEG로 저장하고 대시보드가 바로
    쓸 수 있는 "/captures/<파일명>.jpg" 상대 경로를 돌려준다. 저장 실패(frame이
    없거나 imwrite 실패) 시 None을 돌려주며, 이 경우 send_ai_event()는 그냥
    frameRefBefore/After를 비워서 보낸다(예전과 동일하게 동작 - 새 기능이
    실패해도 이벤트 자체는 계속 올라간다)."""
    if frame is None:
        print(f"[CAPTURE] {source_id}/{tag}: frame이 없어 캡쳐를 저장하지 않습니다.")
        return None

    filename = f"{uuid.uuid4().hex}.jpg"
    filepath = os.path.join(CAPTURES_DIR, filename)

    ok = cv2.imwrite(filepath, frame)
    if not ok:
        print(f"[CAPTURE] {source_id}/{tag}: 캡쳐 이미지 저장 실패 ({filepath})")
        return None

    return f"/captures/{filename}"


def send_ai_event(
    cam_id,
    camera_name,
    track_id,
    bbox_xyxy,
    pattern,
    frame_ref_before=None,
    frame_ref_after=None,
):
    """[신규] 음주운전(지그재그) 패턴이 처음 확정된 순간(just_confirmed) 딱 한 번 호출된다.

    b_gateway의 "공통 이벤트 스키마" POST /api/events로 보낸다 - 이게 있어야 대시보드
    오른쪽 "이벤트" 리스트에 카드가 쌓이고, App.jsx가 화면 정중앙 알림 팝업을 띄우고,
    "📄 PDF 리포트 생성" 버튼도 동작한다(EventCreateRequest 참고: camId/eventType/
    objectClass/occurredAt만 필수, 나머지는 선택). eventType은 b_dashboard/src/
    constants.js의 VEHICLE_TRACK_EVENT_TYPES에 이미 등록돼 있는 "DUI_PATTERN"을 쓴다.

    trackId는 map.js가 나중에 이 이벤트를 클릭했을 때 사건 전/후 캡처 이미지를
    PATCH /api/events/by-track/{trackId}/captures로 이어붙이는 매칭 키로도 쓰이므로,
    같은 세션 안에서 다른 이벤트와 절대 안 겹치게 "카메라ID-트랙ID-타임스탬프"로 만든다
    (YOLO track_id는 카메라별로 작은 정수라서 그냥 쓰면 다른 차/다른 카메라와 충돌한다).
    """
    if requests is None:
        return None

    # DUI 확정 이벤트 전용(just_confirmed 블록에서만 호출됨) - DUI 경로 기준.
    loc = DUI_CAMERA_LOCATIONS.get(cam_id)
    x1, y1, x2, y2 = bbox_xyxy
    event_track_id = f"{cam_id}-{track_id}-{int(time.time() * 1000)}"

    payload = {
        "camId": cam_id,
        "trackId": event_track_id,
        "eventType": "DUI_PATTERN",
        "objectClass": "VEHICLE",
        "bbox": [int(x1), int(y1), int(x2 - x1), int(y2 - y1)],
        "occurredAt": datetime.now().isoformat(timespec="milliseconds"),
        "location": {"lat": loc["lat"], "lng": loc["lng"]} if loc else None,
        # [신규] 아래 두 필드가 채워져 있으면 대시보드는 이벤트가 처음 뜨는 순간부터
        # "이미지 없음" 대신 실제 사건 전/후 캡처를 바로 보여준다(EventCreateRequest에
        # 이미 있던 선택 필드 - 지금까지는 아무도 채워서 보낸 적이 없었을 뿐).
        "frameRefBefore": frame_ref_before,
        "frameRefAfter": frame_ref_after,
        "meta": {
            "source": "ai",
            "detailType": "car",
            "cameraName": loc["name"] if loc else camera_name,
            "reason": "차선 지그재그·급가감속 패턴 감지",
            "trajectoryFeatures": True,
            "lateralRange": pattern.get("lateral_range"),
            "totalLateralMovement": pattern.get("total_lateral_movement"),
            "directionReversals": pattern.get("reversals"),
        },
    }

    headers = {
        "X-API-Key": GATEWAY_API_KEY,
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(EVENTS_URL, json=payload, headers=headers, timeout=1.0)
        if response.ok:
            print(f"🚨 [AI EVENT] 대시보드 이벤트 전송 성공 | camId={cam_id} | trackId={event_track_id}")
        else:
            print(f"❌ [AI EVENT] 전송 실패 | {response.status_code} | {response.text[:200]}")
    except requests.RequestException as e:
        print(f"❌ [AI EVENT] 전송 실패(서버 미기동 등) - CCTV/지도 표시엔 영향 없음: {e}")

    return event_track_id


def update_event_plate(event_track_id, plate):
    """[신규] DUI 이벤트가 이미 대시보드에 떠 있는 상태에서 번호판이 나중에
    LPR로 확정되면, 새 이벤트를 만드는 대신 이미 떠 있는 그 이벤트의
    meta.plateNumber만 채워 넣는다 - b_gateway의 PATCH
    /api/events/by-track/{trackId}/plate(EventController/EventService에
    새로 추가) 사용. 실패해도(게이트웨이 미기동 등) 지도/CCTV 표시엔 영향 없다.
    """
    if requests is None or not event_track_id:
        return
    headers = {
        "X-API-Key": GATEWAY_API_KEY,
        "Content-Type": "application/json",
    }
    try:
        response = requests.patch(
            f"{EVENTS_URL}/by-track/{event_track_id}/plate",
            json={"plate": plate},
            headers=headers,
            timeout=1.0,
        )
        if response.ok:
            print(f"🔢 [AI EVENT] 번호판 갱신 성공 | trackId={event_track_id} | plate={plate}")
        else:
            print(f"❌ [AI EVENT] 번호판 갱신 실패 | {response.status_code} | {response.text[:200]}")
    except requests.RequestException as e:
        print(f"❌ [AI EVENT] 번호판 갱신 실패(서버 미기동 등): {e}")


def _advance_journey_to(journey, target_cam_id):
    """[신규: 사용자 요청 - "중앙 화면 알림 팝업이 뜨면 폴리라인도 바로 그려지게
    해달라" + "폴리라인이 도로 위에 완벽하게 그려져서 한 번에 끝나게 해달라, 구간별로
    나눠서 애니메이션처럼 그리던 로직은 다 지워달라"]

    여정을 target_cam_id까지 진행시키는 단 하나의 함수 - 이전엔 "한 구간씩 감지될
    때마다 그 구간만 이어붙이는" 정상 흐름과 "알림이 뜬 카메라까지 한 번에 따라잡는"
    흐름이 서로 다른 함수(각각 _extend_journey_async / fast_forward_journey_to)로
    나뉘어 있었고, 둘 다 "구간을 하나씩 OSRM에 물어서 순서대로 이어붙이는" 방식이었다.
    그런데 지도 쪽(map.js)은 구간이 도착할 때마다 차량 아이콘이 그 구간을 실제로
    "운전해서 지나가는" 애니메이션을 큐에 쌓아 재생했고, 이 스크립트처럼 여러 구간이
    한꺼번에 확정되면 그 큐가 파이썬을 이미 끈 뒤에도 한참 재생되며 지그재그로 겹쳐
    그려지는 문제가 있었다.

    이제는 딱 한 가지 방식만 남긴다: (여정이 아직 시작 안 한 채로 호출되는 경우엔
    - 지금은 update_journey_for_frame()이 시작을 항상 먼저 처리하므로 실질적으로
    발생하지 않는다 - CAMERA_ORDER[0]에서 시작시키는 폴백만 남겨뒀다) journey가
    현재 있는 지점부터 target_cam_id까지 CAMERA_ORDER 순서를 그대로(중간 지점을
    절대 건너뛰지 않고) 우선 직선으로 즉시 한 번에 이어그려서 바로 눈에 보이게
    한 다음, 여정 시작점부터 target_cam_id까지 전체 구간을 OSRM "다중 경유지"
    요청 딱 한 번으로 물어서 완성된 전체 경로를 받아 폴리라인을 통째로 딱 한 번만
    교체한다. 구간별 분할도, 애니메이션 큐도, 뒤늦은 재생도 전부 없앴다 - 화면에는
    "즉시 직선이 뜨고, 잠시 후 도로 모양으로 한 번에 딱 맞춰지는" 두 단계만 존재한다.
    """
    camera_order = journey.camera_order
    camera_locations = journey.camera_locations

    if target_cam_id not in camera_order:
        return

    target_index = camera_order.index(target_cam_id)

    if not journey.active:
        start_loc = camera_locations.get(camera_order[0])
        if not start_loc:
            return
        journey.active = True
        journey.last_cam_id = camera_order[0]
        journey.points = [(start_loc["lat"], start_loc["lng"])]
        journey.last_seen_at = time.time()
        journey._journey_pending = False

    current_index = (
        camera_order.index(journey.last_cam_id)
        if journey.last_cam_id in camera_order
        else 0
    )

    if target_index <= current_index:
        # 이미 지나왔거나 같은 지점 - 새로 할 일이 없다.
        journey.last_seen_at = time.time()
        return

    if getattr(journey, "_journey_pending", False):
        # 이미 다른 구간을 진행 중이면(예: 방금 다른 카메라에서도 알림이 떴음)
        # 그 작업이 끝날 때까지 기다린다 - 동시에 두 번 진행시키지 않는다.
        return

    # 1) camera_order[0](여정 시작점)부터 target_cam_id까지 좌표 그대로 직선으로
    #    즉시 이어그려서 바로 눈에 보이게 한다 (실제 도로 경로는 아래 2)에서
    #    한 번에 교체됨).
    start_loc = camera_locations[camera_order[0]]
    straight_points = [(start_loc["lat"], start_loc["lng"])]
    for i in range(1, target_index + 1):
        loc = camera_locations.get(camera_order[i])
        if loc:
            straight_points.append((loc["lat"], loc["lng"]))

    journey.points = straight_points
    journey.last_cam_id = target_cam_id
    journey.last_seen_at = time.time()
    journey._journey_pending = True

    send_journey_update(journey)

    # 2) 여정 시작점부터 target_cam_id까지 전체 구간을 OSRM 다중 경유지 요청
    #    "한 번"으로 계산해서, 완성되면 폴리라인 전체를 한 번에 교체한다.
    cam_ids = camera_order[: target_index + 1]

    def worker():
        try:
            road_points = get_multi_point_road_route(cam_ids, journey.road_cache, camera_locations)
            if road_points:
                journey.points = road_points
                journey.last_seen_at = time.time()
                print(
                    f"[JOURNEY:{journey.kind}] {camera_locations[cam_ids[0]]['name']} → "
                    f"{camera_locations[cam_ids[-1]]['name']} 전체 경로를 "
                    f"실제 도로 경로로 교체 ({len(road_points)}개 점)"
                )
                send_journey_update(journey)
        finally:
            journey._journey_pending = False

    threading.Thread(target=worker, daemon=True).start()


def update_journey_for_frame(
    journey,
    active_vehicles_by_camera,
    plate_by_cam_id=None,
    gate_ready=True,
):
    """
    다중 CCTV에서 동일 차량의 여정(journey.kind에 따라 음주운전 의심 또는
    등록된 관심 차량 매칭 중 하나)을 지도에 표시한다.

    [신규: "음주운전 폴리라인이 마지막 지점까지 다 그려지기 전에는 관심대상
    여정이 시작되면 안 된다"] gate_ready=False면(TARGET 호출 시 dui_journey가
    아직 마지막 카메라까지 도달/완주하지 않은 경우) 이 여정이 "아직 시작 전"일
    때만 시작을 보류한다 - 이미 시작된 여정은 그대로 진행된다(중간에 멈추지
    않음). 번호판이 이미 등록/매칭돼 있어도 이 여정은 gate_ready가 True가 될
    때까지 카메라 감지를 그냥 무시하고 대기만 한다.

    [수정: "음주운전이랑 관심대상은 서로 다른, 완전히 별개의 기능이다"] 이
    함수는 이제 단일 신호 소스만 받는다 - journey는 처음 만들어질 때부터
    kind("DUI"|"TARGET")가 고정돼 있으므로, 여기서 트리거를 합치거나
    우선순위를 매길 필요가 없다. main()이 dui_journey/target_journey 각각에
    대해 이 함수를 프레임마다 한 번씩(총 두 번) 따로 호출한다.

    데모 영상은 여러 CCTV 영상이 동시에 재생되기 때문에
    A/B/C/D가 같은 순간에 모두 활성화될 수 있다.

    따라서 journey.camera_order를 기준으로 Journey를 진행한다.

    active_vehicles_by_camera: {camId: {track_id, ...}} - 이 journey.kind를
    트리거하는 조건(DUI면 지그재그 확정, TARGET이면 번호판 매칭)을 만족하는
    차량들.

    plate_by_cam_id: {camId: 번호판} 형태 - 그 카메라에서 현재 인식된 번호판.
    TARGET 호출 시엔 target_matched_vehicles(등록된 관심 차량과 매칭된 것)
    기준이고, DUI 호출 시엔 plate_by_camera(LPR이 인식한 아무 번호판, 등록
    여부 무관) 기준이다 - 호출부(main 루프)가 각자 맞는 딕셔너리를 넘긴다.

    [신규: "음주운전 알림팝업/이벤트/PDF 리포트에도 인식한 차량 번호가 나오게
    해달라"] 예전엔 이 값이 TARGET 여정에서만 journey.plate를 채우는 데
    쓰였다(DUI는 번호판을 아예 안 씀) - 이제 DUI 여정도 똑같이 이 값으로
    journey.plate를 채우고, 처음 채워지는 순간 update_event_plate()로 이미
    떠 있는 DUI 이벤트(대시보드 알림팝업/이벤트 카드/PDF 리포트)의 번호판도
    갱신한다.
    """

    now = time.time()

    active_cam_ids = [
        cam_id
        for cam_id, ids in active_vehicles_by_camera.items()
        if ids
    ]

    # =========================================================
    # CCTV 이동 순서
    # =========================================================

    camera_order = journey.camera_order
    camera_locations = journey.camera_locations

    # =========================================================
    # 아직 Journey가 없으면
    # [수정: "여정이 마지막 카메라(D)에서 시작해서 바로 멈춰버린다"] 예전에는
    # camera_order 중 "이번 프레임에 활성화된 아무 카메라"를 시작점으로 삼았다.
    # 그런데 데모 영상 4개는 서로 독립적으로 재생되기 때문에, 실제로는 마지막
    # 카메라(D, camera_order[-1])의 감지 조건이 A/B/C보다 먼저 걸리는 경우가
    # 흔했다 - 그러면 여정이 마지막 지점에서 시작해버리고, "다음 카메라"가
    # 없으므로 그 즉시 영구히 멈춘다(폴리라인이 1개 좌표에서 더 안 자람).
    # 여정은 반드시 camera_order[0](DUI=보라매역/TARGET=이대역)에서만 시작해야
    # 한다 - 다른 카메라가 먼저 활성화돼도 무시하고, camera_order[0]이 활성화될
    # 때까지 대기한다.
    # =========================================================

    if not journey.active:

        # [신규: "DUI 폴리라인이 마지막 지점까지 다 그려진 뒤에야 TARGET 여정을
        # 시작하자"] 아직 gate가 안 열렸으면(=DUI가 아직 마지막 카메라까지
        # 도달/완주하지 못함) 번호판이 매칭돼 있어도 이번 프레임엔 시작하지
        # 않고 계속 대기한다. main()에서 dui_journey의 진행 상태를 보고 이
        # 값을 계산해서 넘겨준다(TARGET 호출에만 해당 - DUI 호출은 항상 True).
        if not gate_ready:
            return

        # 이번 프레임에 트리거할 게 하나도 없으면 대기
        if not active_cam_ids:
            return

        if camera_order[0] not in active_cam_ids:
            # 시작 카메라(camera_order[0])가 아직 활성화되지 않았다 - 다른
            # 카메라(예: 마지막 카메라)가 먼저 활성화됐더라도 그걸로 시작하지
            # 않고 계속 대기한다.
            return

        start_cam_id = camera_order[0]

        loc = camera_locations.get(start_cam_id)

        if not loc:
            return

        journey.active = True

        journey.last_cam_id = start_cam_id

        journey.points = [
            (loc["lat"], loc["lng"])
        ]

        journey.last_seen_at = now

        # [수정: "DUI도 번호판이 알림팝업/이벤트/PDF 리포트에 나오게"] 시작
        # 카메라에서 이미 번호판이 인식돼 있으면(DUI/TARGET 공통, 아직 OCR
        # 전이면 None으로 두고 아래 진행 분기에서 채워질 수 있다) 바로 채워
        # 넣는다.
        journey.plate = plate_by_cam_id.get(start_cam_id) if plate_by_cam_id else None
        if journey.plate:
            update_event_plate(journey.event_track_id, journey.plate)

        # 이동 처리 중 여부 초기화
        journey._journey_pending = False

        print(
            f"[JOURNEY:{journey.kind}] 새 여정 시작: "
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
    # [수정: "DUI도 번호판이 나오게"] 시작 시점엔 아직 OCR이 안 돼서 번호판을
    # 못 채웠을 수 있다 - DUI/TARGET 공통으로, 지금 카메라에서 번호판이
    # 인식됐는데 journey.plate가 아직 비어 있으면 채워 넣고, 지도 위 여정
    # payload(폴리라인 팝업)뿐 아니라 DUI라면 이미 떠 있는 대시보드 이벤트의
    # 번호판도 즉시 갱신한다(다음 카메라 전환까지 기다리지 않는다).
    # =========================================================

    if (
        not journey.plate
        and plate_by_cam_id
        and journey.last_cam_id in plate_by_cam_id
    ):
        journey.plate = plate_by_cam_id[journey.last_cam_id]
        print(
            f"[JOURNEY:{journey.kind}] 번호판 확인됨(진행 중 갱신): {journey.plate}"
        )
        send_journey_update(journey)
        update_event_plate(journey.event_track_id, journey.plate)

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
    # [유지: 사용자 요청 - "폴리라인이 이상한 곳을 그리고 있다, 정해진 순서대로
    # 그리게 해달라"] current_index 다음부터 순서상 "가장 먼저 발견되는 활성
    # 카메라"로 바로 건너뛰지 않는다. 4대 카메라는 각자 독립된 영상이라 재생
    # 타이밍이 서로 다르기 때문에, 중간 카메라를 건너뛰면 지도 위 경로가 정해진
    # 순서를 벗어난 이상한 길로 그려진다. 바로 다음 순번의 카메라 하나만
    # 확인해서, 그 카메라가 아직 활성화되지 않았으면 기다리고(아래 "다음 CCTV가
    # 아직 감지되지 않은 경우" 블록에서 처리), 순서를 건너뛰지 않는다.

    next_cam_id = None

    if (
        current_index >= 0
        and current_index + 1 < len(camera_order)
    ):

        candidate = camera_order[current_index + 1]

        if candidate in active_cam_ids:

            next_cam_id = candidate

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
                f"[JOURNEY:{journey.kind}] "
                f"{JOURNEY_STALE_SECONDS:.0f}초간 재감지 없음 - 여정 종료"
            )

            journey.reset()

            send_journey_update(journey)

        return

    # =========================================================
    # 다음 CCTV 이동 - _advance_journey_to() 하나로 통일 (즉시 직선 이어그리기 +
    # 전체 구간 OSRM 다중 경유지 요청 한 번으로 도로 경로 완성, 구간별 분할 없음).
    # 이미 진행 중이면(_journey_pending) 함수 안에서 스스로 무시한다.
    # =========================================================

    _advance_journey_to(journey, next_cam_id)


# ============================================================
# 10-1. 등록된 관심 차량(번호판) 매칭  [신규]
# ------------------------------------------------------------
# d_lpr(번호판 인식)이 읽어낸 번호판을, b_gateway에 등록된 관심 대상(Target,
# targetType=VEHICLE, status=ACTIVE)의 plateNumber와 대조한다.
# 일치하면 그 track_id는 "이상운전 여부와 무관하게" 위 10번 섹션의 Journey를
# 트리거하는 대상이 된다 - main()의 target_matched_vehicles에 채워 넣고,
# update_journey_for_frame()에 넘기는 dict를 suspicious_vehicles 대신 이걸로
# 바꾸는 방식이다(10번 섹션 함수 자체는 한 글자도 건드리지 않는다).
# ============================================================

TARGET_POLL_INTERVAL_SEC = 10.0

_target_cache = {"plates": {}, "fetched_at": 0.0}


def normalize_plate(raw):
    """공백 제거 정도만 한다 - TargetsPanel(프론트) 입력값과 d_lpr 인식값
    양쪽 다 지역명 없이 "12가3456" 형태로 다룬다는 전제가 이미 있어서(V2 LPR
    테이블 주석 참고), 추가 정규화는 하지 않는다."""
    return (raw or "").replace(" ", "").strip()


def refresh_target_plates(force=False):
    """활성(ACTIVE) 차량 관심대상의 번호판 -> {targetId, label} 맵을 갱신한다.
    TARGET_POLL_INTERVAL_SEC마다 한 번만 실제로 조회하고, 그 사이엔 캐시를
    그대로 돌려준다(프레임마다 호출해도 API를 매번 때리지 않기 위함).

    실패해도 예외를 던지지 않는다 - 관심 대상 조회가 안 된다고 이상운전
    탐지/Journey 전체가 멈추면 안 된다는 이 파일 전체의 원칙과 동일하다."""
    now = time.time()
    if not force and now - _target_cache["fetched_at"] < TARGET_POLL_INTERVAL_SEC:
        return _target_cache["plates"]

    headers = {"X-API-Key": GATEWAY_API_KEY}
    try:
        response = requests.get(
            TARGETS_URL,
            params={"status": "ACTIVE", "size": 200},
            headers=headers,
            timeout=2,
        )
        response.raise_for_status()
        data = response.json()

        plates = {}
        for t in data.get("content", []):
            if t.get("targetType") != "VEHICLE":
                continue
            plate = normalize_plate(t.get("plateNumber"))
            if plate:
                plates[plate] = {"targetId": t.get("id"), "label": t.get("label")}

        _target_cache["plates"] = plates
        _target_cache["fetched_at"] = now

    except requests.RequestException as e:
        print(f"[TARGET] 관심 대상 조회 실패(다음 주기에 재시도) - {e}")

    return _target_cache["plates"]

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

            # [신규] 사건 "전" 캡처용 최근 프레임 버퍼 - 이 카메라의 실제 fps 기준
            # BEFORE_CAPTURE_SECONDS초 분량만 들고 있는다(오래된 프레임은 deque가
            # 자동으로 버림). realtime_anomaly.py의 frame_buffer와 동일한 패턴.
            "frame_buffer":
                deque(maxlen=max(1, round(fps * BEFORE_CAPTURE_SECONDS))),

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

    # [수정: "음주운전이랑 관심대상은 서로 다른, 완전히 별개의 기능이다"] 전체
    # 시스템에 Journey가 하나만 있는 게 아니라, DUI/TARGET 각각 자신만의 카메라
    # 경로를 가진 완전히 독립된 인스턴스 두 개가 동시에 존재한다 (위 "10. 실시간
    # 차량 이동 경로" 설명 참고). 서로 active/points/marker가 절대 섞이지 않는다.
    dui_journey = VehicleJourney("DUI", DUI_CAMERA_LOCATIONS, DUI_CAMERA_ORDER)
    target_journey = VehicleJourney("TARGET", TARGET_CAMERA_LOCATIONS, TARGET_CAMERA_ORDER)

    # [신규] 번호판 인식(LPR) - 프로세스 전체에서 공유하는 단일 인스턴스.
    # (cam_id, track_id) 쌍으로 내부적으로 구분하므로 카메라 4개가 공유해도 안전하다.
    if LPR_TEST_MOCK:
        plate_reader = PlateReader(mock=True, mock_plates=LPR_TEST_MOCK_PLATES)
    else:
        plate_reader = PlateReader()

    # 어떤 (카메라, track_id)에 어떤 번호판이 확정됐는지 한 번만 찍기 위한
    # 기록 - 확정 후에는 매 프레임 값이 나와서 그대로 찍으면 로그가 도배된다.
    _lpr_test_logged = set()

    # [신규] 카메라별 "이번에 등록된 관심 차량과 매칭된 track_id -> 매칭정보" 기록.
    # suspicious_vehicles와 같은 모양(카메라명을 key로 갖는 dict)으로 맞췄다.
    target_matched_vehicles = {
        camera_name: {}
        for camera_name
        in cameras
    }


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

            # [신규] 사건 "전" 캡처용 - 매 프레임마다 채워둔다 (realtime_anomaly.py와
            # 동일한 패턴). YOLO 추론 전에 원본 프레임을 그대로 넣어야
            # 박스/텍스트가 그려지지 않은 깨끗한 캡처가 된다.
            camera["frame_buffer"].append(frame.copy())


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
                # [신규] 번호판 인식 + 등록된 관심 차량 매칭
                # ------------------------------------------------

                x1, y1, x2, y2 = info["bbox"]

                plate_reader.update(
                    cam_id,
                    track_id,
                    (x1, y1, x2, y2),
                    frame,
                    camera["frame_idx"],
                )

                confirmed_plate = plate_reader.plate_of(cam_id, track_id)

                if confirmed_plate:

                    _log_key = (camera_name, track_id)
                    if _log_key not in _lpr_test_logged:
                        _lpr_test_logged.add(_log_key)
                        _tag = "LPR-TEST" if LPR_TEST_MOCK else "LPR"
                        print(
                            f"🔎 [{_tag}] {camera_name} track={track_id} "
                            f"plate={confirmed_plate} -> 이 번호판을 "
                            f"'관심 대상 관리'에 등록하면 🎯 매칭이 뜹니다."
                        )

                    plate_by_camera[camera_name][track_id] = confirmed_plate

                    matched_target = refresh_target_plates().get(
                        normalize_plate(confirmed_plate)
                    )

                    if matched_target and track_id not in target_matched_vehicles[camera_name]:

                        target_matched_vehicles[camera_name][track_id] = {
                            "plate": confirmed_plate,
                            "targetId": matched_target["targetId"],
                            "label": matched_target["label"],
                        }

                        print(
                            f"🎯 [TARGET] 등록된 관심 차량 감지 | "
                            f"{camera_name} | plate={confirmed_plate} | "
                            f"targetId={matched_target['targetId']}"
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
                # [삭제됨: 사용자 요청 - "계속 엉뚱한 알림이 뜬다, 저거 그냥 없애"]
                # 예전엔 지그재그 패턴이 전혀 안 잡혀도 차량이 화면에 등장한 뒤
                # FORCE_ALERT_AFTER_SECONDS(3초)만 지나면 무조건 강제로
                # 관심차량(빨간 박스) + DUI_PATTERN 이벤트를 만들었다. 그래서 카메라
                # 4대 모두 영상을 켤 때마다(또는 새로 재생될 때마다) 실제 이상운전
                # 여부와 무관하게 3초 뒤 항상 알림 팝업/이벤트가 떴다 - 이게 바로
                # "엉뚱한 곳에 알림이 생겨서 포커싱된다"의 원인이었다. 이제는 아래
                # check_suspicious_vehicle()의 진짜 지그재그·급가감속 패턴 판정
                # 결과(is_suspicious/just_confirmed)만 그대로 쓴다 - 강제 타이머는
                # 더 이상 개입하지 않는다.
                # ------------------------------------------------


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

                    # [신규: 사용자 요청 - "알림 팝업이 카메라 지날 때마다 뜬다, 처음
                    # 잡혔을 때 한 번만 뜨게 해달라"] 지금까지는 카메라마다 각자
                    # 독립적으로 지그재그 패턴을 판정하기 때문에, 같은 차량이
                    # 보라매역→장승배기→상도→한강대교남단으로 이어지는 한 여정 동안
                    # 카메라 4대 모두에서 just_confirmed가 각각 따로 발생해서 대시보드
                    # 알림 팝업/이벤트가 카메라 수만큼 반복해서 떴다. 이제는 이번 여정
                    # (dui_journey)에서 이미 한 번 보냈으면(dui_journey.alert_sent) 이후
                    # 카메라들에서는 send_ai_event를 다시 호출하지 않는다 - 지도 위
                    # 여정 추적(update_journey_for_frame)과 CCTV 박스 오버레이는
                    # 이 플래그와 무관하게 그대로 계속된다.
                    if dui_journey.alert_sent:
                        print(
                            f"ℹ️  {camera_name}: 같은 여정에서 이미 알림을 보냈으므로 "
                            "이벤트를 다시 만들지 않습니다 (여정 추적은 계속됩니다)."
                        )
                    else:
                        dui_journey.alert_sent = True

                        # [유지] 예전엔 여기서 곧바로 _advance_journey_to(dui_journey,
                        # cam_id)를 호출해서 "중앙 화면 알림 팝업이 뜨는 것과 같은
                        # 프레임에 폴리라인도 나타나게" 했었다. 지금도 여기서 직접
                        # 진행시키지 않는다 - 대신 이 프레임(같은 루프 안에서 카메라를
                        # 모두 처리한 뒤) 끝에서 호출되는 update_journey_for_frame()이
                        # suspicious_by_cam_id에 이 cam_id가 포함된 걸 보고 즉시
                        # 진행시킨다("같은 프레임에 반영된다"는 요구사항은 그대로
                        # 만족한다). dui_journey.kind는 생성 시점부터 항상 "DUI"로
                        # 고정돼 있으므로 여기서 reason을 따로 바꿔줄 필요는 없다.

                        # [신규] 사건 전/후 캡처를 여기서 동기적으로 저장해서, 이벤트가
                        # 대시보드에 뜨는 "그 순간"에 이미 이미지가 들어있게 한다. "전"은
                        # frame_buffer에서 가장 오래된(=BEFORE_CAPTURE_SECONDS초 전) 프레임,
                        # "후"는 방금 이 track_id가 확정된 지금 이 프레임 그대로.
                        _frame_buffer = camera["frame_buffer"]
                        _before_frame = _frame_buffer[0] if _frame_buffer else None
                        _after_frame = frame.copy() if frame is not None else None
                        _frame_ref_before = save_capture(_before_frame, cam_id, "before")
                        _frame_ref_after = save_capture(_after_frame, cam_id, "after")

                        # [신규] 대시보드 "이벤트" 리스트/화면 중앙 알림 팝업/PDF 리포트로
                        # 이어지는 진짜 백엔드 이벤트 생성 - 위 events.append(event)는 이
                        # 파이썬 프로세스 안에서만 쓰는 내부 로그용 리스트라 대시보드와는
                        # 무관하다(그래서 여태 이벤트가 안 떴다).
                        # [신규] 반환된 event_track_id를 dui_journey에 저장해둔다 - 번호판이
                        # 나중(다음 카메라)에 확정되면 update_event_plate()가 이 trackId로
                        # 이미 떠 있는 이 이벤트의 meta.plateNumber만 채워 넣는다.
                        dui_journey.event_track_id = send_ai_event(
                            cam_id,
                            camera_name,
                            track_id,
                            info["bbox"],
                            pattern,
                            frame_ref_before=_frame_ref_before,
                            frame_ref_after=_frame_ref_after,
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

        target_matched_by_cam_id = {
            cameras[camera_name]["camId"]: set(target_matched_vehicles[camera_name].keys())
            for camera_name in cameras
        }

        # [신규] 알림 팝업에 표시할 번호판 - 카메라별로 매칭된 관심 차량이
        # 여럿이어도(이론상 거의 없음) 하나만 대표로 쓴다. 정확한 번호판
        # 매칭이 아니라 "이 카메라에서 지금 관심 차량이 잡혔다"는 표시 용도이므로
        # 첫 번째 값으로 충분하다.
        plate_by_cam_id = {
            cameras[camera_name]["camId"]: next(
                iter(target_matched_vehicles[camera_name].values())
            )["plate"]
            for camera_name in cameras
            if target_matched_vehicles[camera_name]
        }

        # [신규: "알림팝업/이벤트/PDF 리포트에 인식한 차량번호도 넣어달라"] DUI 여정용
        # 번호판 - target_matched_vehicles(등록된 관심 차량 매칭 결과)가 아니라
        # plate_by_camera(등록 여부와 무관하게 확정된 모든 차량의 번호판)에서, 지금
        # 이 카메라에서 "이상운전으로 잡힌" track_id(suspicious_vehicles[camera_name])와
        # 겹치는 번호판만 골라 쓴다. 여러 개면(이론상 거의 없음) 첫 번째 값으로 대표한다.
        dui_plate_by_cam_id = {}
        for camera_name in cameras:
            for _track_id in suspicious_vehicles[camera_name]:
                _plate = plate_by_camera[camera_name].get(_track_id)
                if _plate:
                    dui_plate_by_cam_id[cameras[camera_name]["camId"]] = _plate
                    break

        # [수정: "음주운전이랑 관심대상은 서로 다른, 완전히 별개의 기능이다"]
        # 두 트리거를 하나로 합치지 않고, 완전히 독립된 두 여정에 각각 한 번씩
        # 따로 갱신한다 - 같은 프레임에 둘 다 활성이어도 서로 전혀 간섭하지
        # 않고 동시에 진행된다.
        #
        # [신규: "음주운전 폴리라인이 마지막 지점(한강대교남단)까지 다 그려진
        # 뒤에야 관심대상 여정이 시작되게 해달라"] TARGET 여정의 "시작"만
        # gate_ready로 막는다 - dui_journey가 CAMERA_ORDER 마지막 카메라까지
        # 도달했고(last_cam_id == 마지막 camId), 그 구간의 실제 도로 경로
        # 교체(_advance_journey_to의 백그라운드 스레드)까지 끝나서
        # _journey_pending이 False가 된 시점이라야 "폴리라인이 다 그려졌다"고
        # 본다. 이미 시작된 TARGET 여정은 이 값과 무관하게 계속 진행된다.
        dui_finished_drawing = (
            dui_journey.last_cam_id == DUI_CAMERA_ORDER[-1]
            and not dui_journey._journey_pending
        )

        update_journey_for_frame(dui_journey, suspicious_by_cam_id, dui_plate_by_cam_id)
        update_journey_for_frame(
            target_journey,
            target_matched_by_cam_id,
            plate_by_cam_id,
            gate_ready=dui_finished_drawing,
        )


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