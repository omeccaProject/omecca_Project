import os
import cv2
import time
import requests

from collections import deque
from datetime import datetime
from pathlib import Path

import numpy as np
import torch
from dotenv import load_dotenv
from ultralytics import YOLO


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

# [버그 수정: "HTTP 404 No static resource ."] .env.example(e_tracking/SmartCCTV)에는
# GATEWAY_URL=http://localhost:8080 처럼 "경로 없이 호스트만" 적혀 있다(다른 스크립트들이
# 그 뒤에 자기 endpoint를 붙여쓰는 공용 관례) - 그런데 이 os.getenv 기본값은
# "/api/cctv/detections"까지 포함된 완전한 URL이라, .env에 값이 있으면 그 값이
# 그대로 GATEWAY_URL이 되어 fallback의 경로 부분이 통째로 사라졌다(→ POST가 그냥
# "http://localhost:8080/"로 나가서 404). .env에 경로가 있든 없든 항상 올바른
# endpoint로 붙게 정규화한다.
_GATEWAY_URL_RAW = os.getenv(
    "GATEWAY_URL",
    "http://localhost:8080"
)

_GATEWAY_BASE_URL = _GATEWAY_URL_RAW.rstrip("/")

if _GATEWAY_BASE_URL.endswith("/api/cctv/detections"):
    GATEWAY_URL = _GATEWAY_BASE_URL
else:
    GATEWAY_URL = _GATEWAY_BASE_URL + "/api/cctv/detections"

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

# GPU 컴퓨터에서 실행할 때
# True  → GPU 0번
# False → CPU

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

        "camId": "L010480",

        "video":
            VIDEO_DIR / "음주운전4.mp4",

    },

}


# ============================================================
# 5. YOLO 설정
# ============================================================

CONF_THRESH = 0.30

IMG_SIZE = 640


# COCO
#
# 2 = car
# 3 = motorcycle
# 5 = bus
# 7 = truck

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

# [민감화] 빨간 박스가 더 빨리 뜨도록 임계값을 낮췄다(요청: "빨간색 바운딩박스 씌우는거
# 더 빠르게 할 수 없을까"). 원래 값은 각각 6 / 18 / 35 / 2 였음 - 너무 오래 지켜봐야
# "지그재그"로 판정돼서 화면에 빨간 박스가 늦게 떴다. 값을 낮출수록 더 작은 움직임에도
# 민감하게 반응하니, 오탐(진짜 정상 주행인데 빨간색)이 너무 잦아지면 다시 살짝 올릴 것.
MIN_HISTORY_FOR_ANALYSIS = 4

NOISE_DX_PX = 2.0

MIN_LATERAL_RANGE_PX = 10

MIN_TOTAL_LATERAL_MOVEMENT = 20

MIN_DIRECTION_REVERSALS = 1

SUSTAIN_FRAMES = 1

# [신규] 지그재그 패턴이 안 잡히더라도, 차량이 화면에 처음 등장한 뒤 이 시간(초)이
# 지나면 무조건 관심차량(빨간 박스)으로 강제 전환한다 - 데모 시연용 안전장치.
# 실제 지그재그가 먼저 잡히면 그 즉시 빨간색이 되고, 이 타이머는 트리거되지 않는다.
FORCE_ALERT_AFTER_SECONDS = 3.0


# ============================================================
# 7. API 전송 주기
# ============================================================

DETECTION_SEND_INTERVAL = 0.10


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

    # --------------------------------------------------------
    # GPU
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # CPU
    # --------------------------------------------------------

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
# 10. CCTV 영상 연결
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
# 11. YOLO + ByteTrack
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
# 12. 차량 중심점
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
# 13. 차량 이동 기록
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
# 14. 이상운전 패턴 분석
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
# 15. 이상운전 차량 판정
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
# 16. Spring Boot Detection API 전송
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
# 16-1. 대시보드 실시간 박스 오버레이 전송
# ============================================================
#
# [버그 수정: "카메라 관리로 등록한 CCTV 화면에 바운딩박스가 안 씌워짐"]
# 위 send_detection()은 "이 차량이 이상운전으로 확정됐다"는 판정 결과(lateralRange 등)를
# 보내는 별개의 payload라서, b_gateway의 CctvDetectionController가 기대하는
# {camId, frameWidth, frameHeight, detections:[{trackId, bbox}]} 스키마와 다르다 -
# 그래서 이 스크립트는 지금까지 대시보드 오버레이 캔버스(CctvOverlayCanvas,
# /topic/cctv/detections 구독)가 필요로 하는 데이터를 한 번도 보낸 적이 없었다.
# (test_hls_yolo.py의 send_frame_detections()와 정확히 동일한 스키마 - 계약 유지)
#
# 이건 이상운전 판정과 무관하게 "이 프레임에 지금 보이는 차량 전체"를 매 프레임
# 한 번씩(카메라당) 보내면 되므로, DETECTION_SEND_INTERVAL 쓰로틀링과 별개로 둔다.

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
            # 음주운전(지그재그 주행 등) 의심으로 확정된 차량이면 true - 대시보드가
            # 이 값을 보고 박스를 초록 대신 빨간색으로 그린다.
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
        # 성공 로그는 매 프레임 찍으면 콘솔이 도배되므로 생략(실패했을 때만 남김).
    except requests.exceptions.RequestException as e:
        print(f"[박스 오버레이 네트워크 오류] {e}")


# ============================================================
# 17. 차량 Bounding Box
# ============================================================

def draw_vehicle(

    frame,

    track_id,

    info,

    history,

    is_suspicious

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
# 18. CCTV 헤더
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
# 19. 4분할 화면
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
# 20. MAIN
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


    # ========================================================
    # 이벤트
    # ========================================================

    events = []


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

                    is_suspicious

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


            display_frames[
                camera_name
            ] = frame


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