"""
realtime_anomaly.py
================================================================
실시간 UTIC CCTV(HLS) 4개 + 발표용 Forza 데모 영상(MP4) 4개를
"하나의 공통 AI 엔진"(YOLO + ByteTrack + anomaly_detection.py의
detect_weaving 판정 로직)으로 처리한다.

절대 원칙 (지켜야 할 것)
----------------------------------------------------------------
- anomaly_detection.py의 함수(detect, update_track, detect_weaving,
  evaluate_anomaly_rules, is_abnormal_active, handle_anomaly, draw_warning,
  draw_event_log_panel 등)와 상수(VEHICLE_CLASSES, CONF_THRESHOLD,
  HOLD_WARNING_SECONDS, WEAVING_* 등)는 이 파일에서 단 한 줄도 수정하지
  않는다. import해서 그대로 호출/참조만 한다.
- track.py는 이번 통합과 무관하다 (번호판 기반 "관심 차량" 추적 + Kalman
  필터 보간 기능으로, anomaly_detection.py의 weaving 탐지와는 완전히
  다른 기능이고, anomaly_detection.py 자신도 "track.py와 독립적"이라고
  명시하고 있다). 그래서 이 파일은 track.py를 사용하지 않는다. 삭제하지도
  않았다.
- 일반 차량은 화면에 아무것도 그리지 않는다 - 이건 이미 anomaly_detection.py의
  handle_anomaly()가 원래 그렇게 동작한다(이상운전 상태가 아니면 draw_warning을
  아예 호출하지 않음). 그래서 이 파일도 별도로 "정상 차량 박스"를 그리는 코드를
  추가하지 않았다 - handle_anomaly()를 그대로 쓰기만 하면 요구사항이 자동으로 지켜진다.

왜 멀티프로세스인가 (구조 설명)
----------------------------------------------------------------
1. anomaly_detection.py는 track_states / event_logs / track_to_plate /
   HOLD_WARNING_FRAMES 를 "모듈 전역 변수"로 갖고 있다. 영상이 1개일 때는
   문제없지만, 8개 영상을 동시에 처리하면 서로 다른 영상의 궤적/이벤트가
   하나의 전역 상태에 뒤섞인다.
2. model.track(..., persist=True)는 ByteTrack 추적 상태를 YOLO 모델
   "객체 내부"에 저장한다. 여러 영상이 모델 하나를 공유하면 ID 체계 자체가
   섞인다.
3. cv2.imshow를 여러 스레드에서 동시에 호출하면(특히 Windows에서) 불안정할
   수 있다.

세 문제 모두 "영상마다 완전히 별도의 OS 프로세스"로 처리하면 자동으로
해결된다 - 프로세스마다 Python 인터프리터/모듈 전역 상태/모델 인스턴스가
전부 독립적이기 때문에, anomaly_detection.py를 건드리지 않고 그대로
import해서 써도 서로 섞이지 않는다.

지도 연동 (server/ + web/map.js와 실제로 연결됨)
----------------------------------------------------------------
이상운전이 감지될 때마다 이벤트를 아래 두 곳에 동시에 보낸다.

1. "ai_map_events.log"에 한 줄씩 append (기존과 동일 - 디버깅/기록용)
2. server/server.js가 새로 노출하는 POST /api/map/events 로 HTTP 전송
   → server.js가 즉시 ws://localhost:4000/events 에 연결된 모든 브라우저
     (web/map.js의 AiWebSocketListener)로 broadcast
   → map.js가 EventManager.triggerAiEvent()(실제 CCTV) 또는
     EventManager.triggerDemoEvent()(Forza 데모)를 자동 호출해서
     지도 마커 이동 + trajectory 누적을 실시간으로 반영한다.

이 파일(Python)은 map.js 파일을 직접 열거나 수정하지 않는다 - 항상 서버를
경유한다. server/routes/mapEvents.js 참고.

MAP_SERVER_EVENTS_URL로 대상 서버를 바꿀 수 있다. 서버가 꺼져 있어도
(POST가 실패해도) AI 탐지 자체(YOLO/ByteTrack/이상운전 판정, cv2 창 표시)는
전혀 영향을 받지 않는다 - push_event_to_server()가 예외를 전부 안에서
삼키기 때문이다 (다만 첫 실패 시 콘솔에 1회 경고는 출력한다).

전송 payload 형식 (섹션 11 규격 + map.js가 화면에 쓰는 부가 필드):

    데모(Forza):
    {
      "source_type": "DEMO",
      "source_id": "A",
      "global_vehicle_id": "DEMO-DRUNK-001",
      "vehicle_id": "DEMO-DRUNK-001",
      "location_name": "보라매역",
      "timestamp": 1737600000.123,
      "time_str": "18:25:12",
      "latitude": 37.49976,
      "longitude": 126.92007,
      "anomaly": true,
      "event_type": "ABNORMAL_DRIVING",
      "track_id": 3,                     # 이 영상 안에서의 ByteTrack ID (참고용, 지도 이동에는 안 씀)
      "reason": "지그재그 주행",
      "plate": null,
      "confidence": null,
      "video_position_px": {"x": 512, "y": 300}   # 참고용 픽셀 좌표 (지도 좌표 아님)
    }

    실제 CCTV(UTIC):
    {
      "source_type": "UTIC",
      "source_id": "L010263",
      "vehicle_id": "L010263-3",          # "{cam_id}-{ByteTrack track_id}"
      "location_name": "이수역",
      "timestamp": 1737600000.123,
      "time_str": "18:25:12",
      "latitude": 37.4846,
      "longitude": 126.9824,
      "anomaly": true,
      "event_type": "ABNORMAL_DRIVING",
      "track_id": 3,
      "reason": "지그재그 주행",
      "plate": null,
      "confidence": null,
      "video_position_px": {"x": 512, "y": 300}
    }

실행 방법
----------------------------------------------------------------
    python realtime_anomaly.py

ACTIVE_CAMERA_IDS / ACTIVE_DEMO_IDS 로 어떤 소스를 켤지 조절한다.
기본값은 이수역(L010263) 1개만 켜져 있다 (STEP 8: 먼저 1개로 검증).
각 영상마다 별도 창이 뜬다. 창에서 ESC를 누르면 그 영상만 종료된다.
"""

import os
import sys
import json
import time
import multiprocessing as mp
from queue import Empty

import cv2
import torch
from ultralytics import YOLO

try:
    import requests  # server/server.js로 이벤트를 POST하기 위해서만 사용 (requirements.txt에 추가함)
except ImportError:
    requests = None  # requests가 없어도 AI 탐지 자체는 그대로 동작해야 하므로 여기서 죽지 않는다

# anomaly_detection.py를 프로젝트 루트에서 그대로 import한다 (수정 없음).
# 이 파일이 어디서 실행되든 anomaly_detection.py를 찾을 수 있도록,
# 이 스크립트 자신이 있는 폴더를 sys.path에 추가해둔다.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)


# ================================================================
# 1) 실제 UTIC CCTV 4개
#    web/data/utic-video-sources.json / utic-cameras-seoul.json에 이미
#    등록되어 있는 값을 그대로 옮겨왔다 (새로 만들지 않음).
# ================================================================
CAMERA_SOURCES = {
    "L010263": {
        "name": "이수역",
        "type": "HLS",
        "url": "https://strm1.spatic.go.kr/live/76.stream/chunklist_w1824089310.m3u8",
        "lat": 37.4846,
        "lng": 126.9824,
    },
    "L010117": {
        "name": "사당역",
        "type": "HLS",
        "url": "https://strm1.spatic.go.kr/live/75.stream/chunklist_w902267922.m3u8",
        "lat": 37.47688,
        "lng": 126.98136,
    },
    "L010018": {
        "name": "경남아파트",
        "type": "HLS",
        "url": "https://strm2.spatic.go.kr/live/243.stream/chunklist_w575481354.m3u8",
        "lat": 37.47492,
        "lng": 127.00186,
    },
    "L010055": {
        "name": "까치고개",
        "type": "HLS",
        "url": "https://strm1.spatic.go.kr/live/73.stream/chunklist_w2053157549.m3u8",
        "lat": 37.47533,
        "lng": 126.96763,
    },
}

# ================================================================
# 2) 발표용 Forza 데모 영상 4개
#    좌표 출처: web/data/utic-cameras-seoul.json (이 프로젝트에 이미 있는 실제
#    UTIC CCTV 좌표 데이터). "보라매역/장승배기/상도/한강대교남단"이라는 이름을
#    가진 실제 UTIC 카메라 레코드를 그대로 찾아서 그 위경도를 썼다 - 임의로
#    추측한 값이 아니다 (아래 각 줄의 cam_id는 그 좌표가 나온 실제 레코드).
#      A: cam_id L010111 (보라매역)     lat 37.49976 / lng 126.92007
#      B: cam_id L010271 (장승배기)     lat 37.5052  / lng 126.93955
#      C: cam_id L010128 (상도)         lat 37.50303 / lng 126.9478
#      D: cam_id L010481 (한강대교남단) lat 37.51346 / lng 126.95552
#    주의: 이 cam_id들은 "좌표를 빌려온 실제 카메라"일 뿐, Forza 영상이 그
#    카메라의 실시간 스트림이라는 뜻은 아니다. web/map.js도 데모 이벤트에서는
#    이 cam_id의 영상(HLS)으로 전환하지 않고 지도 마커만 그 위치로 옮긴다.
# ================================================================
DEMO_VEHICLE_ID = "DEMO-DRUNK-001"  # A→B→C→D 전체에서 "같은 차량"으로 취급할 데모 전용 전역 ID

DEMO_SOURCES = {
    "A": {"name": "보라매역", "type": "VIDEO", "path": "videos/forza_A.mp4", "lat": 37.49976, "lng": 126.92007, "order": 1, "ref_cam_id": "L010111"},
    "B": {"name": "장승배기", "type": "VIDEO", "path": "videos/forza_B.mp4", "lat": 37.5052, "lng": 126.93955, "order": 2, "ref_cam_id": "L010271"},
    "C": {"name": "상도", "type": "VIDEO", "path": "videos/forza_C.mp4", "lat": 37.50303, "lng": 126.9478, "order": 3, "ref_cam_id": "L010128"},
    "D": {"name": "한강대교남단", "type": "VIDEO", "path": "videos/forza_D.mp4", "lat": 37.51346, "lng": 126.95552, "order": 4, "ref_cam_id": "L010481"},
}

# ================================================================
# 3) 이번에 실제로 켤 소스
#
#    [중요 - 아키텍처 변경] Forza A/B/C/D는 더 이상 이 파일(cv2.imshow 창)로
#    보여주지 않는다. 이제는 웹사이트에서 CCTV(보라매역/장승배기/상도/
#    한강대교남단)를 클릭하면 그 영상이 웹사이트의 <video> 태그에서 직접
#    재생되고, export_forza_track_logs.py가 미리 분석해 둔 결과를
#    web/map.js가 재생 시점에 맞춰 캔버스에 그린다 (H4642 테스트 카메라에
#    쓰던 방식과 동일 - anomaly-track-log.json 참고). 그래서 ACTIVE_DEMO_IDS는
#    기본값을 빈 리스트로 둔다. Python 창 4개를 굳이 다시 띄워서 리허설하고
#    싶을 때만 아래에 "A"/"B"/"C"/"D"를 채워 넣으면 된다(기존 기능은
#    삭제하지 않고 그대로 남겨뒀다).
#
#    실제 CCTV 4개(이수역/사당역/경남아파트/까치고개)는 지금까지와 동일하게
#    이 파일로 라이브 분석한다 - 아래에 채워 넣으면 된다.
#    예: ACTIVE_CAMERA_IDS = list(CAMERA_SOURCES.keys())
#
#    RUN_MODE는 ACTIVE_DEMO_IDS를 쓸 때만 의미가 있다 (요구사항 9번):
#      "PARALLEL"      - A/B/C/D를 각각 독립 프로세스+독립 창으로 동시 실행.
#      "DEMO_SEQUENCE" - 창 하나에서 A→B→C→D를 순서대로 이어서 재생.
# ================================================================
ACTIVE_CAMERA_IDS = []
ACTIVE_DEMO_IDS = ["A"]  # Forza 데모는 이제 웹사이트 클릭으로 재생된다 - 리허설용으로만 필요시 채울 것
RUN_MODE = "PARALLEL"  # "PARALLEL"(병렬 A/B/C/D 동시 실행) 또는 "DEMO_SEQUENCE"(A→B→C→D 순차 실행)

SHOW_WINDOWS = True  # 발표 환경에서 창이 너무 많으면 필요한 소스만 SHOW_WINDOWS 개별 제어로 확장 가능
DRAW_TEST_HUD = True  # MODE/AI FPS/camera_id/이상운전 차량 수 표시 - 최종 웹 UI에 들어갈 때는 False로 분리 가능

EVENT_LOG_PATH = os.path.join(_THIS_DIR, "ai_map_events.log")  # 지도 연동용 이벤트를 한 줄씩 append (기록/디버깅용)

# server/server.js가 노출하는 이벤트 수신 엔드포인트. server/routes/mapEvents.js가
# 이 경로로 받은 이벤트를 ws://localhost:4000/events에 연결된 모든 브라우저(map.js)로
# 그대로 broadcast한다. 서버 포트를 바꿨다면 여기도 같이 바꿔야 한다.
MAP_SERVER_EVENTS_URL = "http://localhost:4000/api/map/events"
MAP_SERVER_TIMEOUT_SEC = 1.0  # 서버가 느리거나 꺼져 있어도 AI 처리 루프가 멈추지 않도록 짧게 잡는다


# ================================================================
# 4) GPU / CPU 자동 설정
#    하드코딩하지 않고 torch.cuda.is_available()로 자동 감지한다.
# ================================================================
def detect_mode_settings():
    if torch.cuda.is_available():
        return {
            "mode": "GPU",
            "device": 0,
            "model_path": "yolo11m.pt",  # anomaly_detection.py 기존 설정과 동일한 모델
            "imgsz": 640,
            "process_every": 1,
            "gpu_name": torch.cuda.get_device_name(0),
        }
    return {
        "mode": "CPU",
        "device": "cpu",
        "model_path": "yolo11s.pt",  # test_hls_yolo.py에서 검증한 CPU용 경량 모델
        "imgsz": 320,
        "process_every": 3,
        "gpu_name": None,
    }


# ================================================================
# 5) 최신 프레임만 유지하는 그래버 (test_hls_yolo.py와 동일한 패턴)
#    HLS/로컬 mp4 모두 cv2.VideoCapture로 동일하게 다룰 수 있어서
#    소스 타입에 상관없이 그대로 재사용한다.
#
#    [진단 결과 - 이번에 실제로 발견/재현한 버그]
#    기존 코드는 EOF(영상 끝)를 처리하지 않았다: cap.read()가 ret=False를
#    반환하면 그냥 0.05초 자고 다시 시도할 뿐이었다. 로컬 mp4는 "언젠가
#    끝나는" 소스인데, 백그라운드 스레드(_loop)가 실시간 속도 제한 없이
#    "디코딩할 수 있는 만큼 최대한 빨리" 읽기 때문에, forza_B.mp4(168프레임,
#    24fps = 약 7초)처럼 짧은 클립은 메인 루프가 YOLO 모델 로딩을 끝내고
#    첫 프레임을 가져가기도 전에 이미 끝까지 다 읽혀버릴 수 있다(실제로
#    이 프로젝트의 forza_B.mp4로 재현 확인: 3초 안에 168프레임 전부 디코딩
#    완료). 그 뒤로는 cap.read()가 계속 ret=False만 반환하므로
#    get_latest()가 계속 None을 돌려주고, source_worker의 while 루프는
#    "if frame is None: continue"에 걸려 cv2.imshow를 다시는 호출하지
#    않는다 - 결과적으로 화면에 "아무것도 안 나오거나(또는 마지막 프레임에
#    멈춘 채) 다시는 갱신되지 않는" 것으로 보인다.
#
#    아래 두 가지를 추가해서 고쳤다 (HLS 동작은 그대로 유지 - is_local_file
#    이 아니면 두 기능 모두 적용하지 않는다):
#      1) loop_video=True면 EOF에서 프레임 0으로 되감아 계속 재생한다.
#      2) pace_to_fps=True면 영상 자체의 fps에 맞춰 프레임 사이에 sleep을
#         넣어서, 사람이 보기에 실제 재생 속도(예: 7초짜리는 7초)로
#         재생되게 한다. (이게 없으면 디코딩이 실시간보다 훨씬 빨라서
#         메인 루프가 따라잡지 못하고 프레임을 대량으로 건너뛰게 된다.)
# ================================================================
class LatestFrameGrabber:
    def __init__(self, source, loop_video=False, pace_to_fps=False, log_prefix=""):
        self.source = source
        self.log_prefix = log_prefix
        self.is_local_file = not str(source).lower().startswith("http")
        self.loop_video = loop_video and self.is_local_file  # HLS(라이브)는 되감기 개념이 없으므로 무시
        self.pace_to_fps = pace_to_fps and self.is_local_file
        self.ended = False  # EOF에 도달했고(loop_video=False) 더 이상 새 프레임이 없음 - DEMO_SEQUENCE가 "다음 영상으로" 넘어갈 때 사용

        # ---- 섹션 5/6: 파일 존재 여부를 먼저 확인 (로컬 파일일 때만 의미 있음) ----
        if self.is_local_file:
            exists = os.path.isfile(source)
            print(f"{log_prefix} file exists: {exists}  path={source}")
            if not exists:
                raise RuntimeError(f"영상 파일을 찾을 수 없습니다: {source}")

        # ---- 로컬 mp4는 Windows에서 기본 백엔드(MSMF/DSHOW)가 특정 코덱/가변
        #      프레임레이트 mp4를 제대로 못 여는 경우가 잘 알려져 있다. FFMPEG
        #      백엔드를 먼저 명시적으로 시도하고, 실패하면 기본 백엔드로
        #      한 번 더 시도한다 (HLS URL은 원래 방식 그대로 - 여기서 바꾸지 않는다).
        if self.is_local_file:
            self.cap = cv2.VideoCapture(source, cv2.CAP_FFMPEG)
            if not self.cap.isOpened():
                print(f"{log_prefix} CAP_FFMPEG로 열기 실패 - 기본 백엔드로 재시도합니다.")
                self.cap = cv2.VideoCapture(source)
        else:
            self.cap = cv2.VideoCapture(source)

        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # 지원되는 백엔드에서만 의미 있음 (참고용)

        # ---- 섹션 7: VideoCapture.isOpened() 확인 ----
        opened = self.cap.isOpened()
        print(f"{log_prefix} VideoCapture opened: {opened}")

        self.fps = self.cap.get(cv2.CAP_PROP_FPS)
        if not self.fps or self.fps <= 1:
            self.fps = 30.0  # HLS 라이브 스트림 등 fps를 못 주는 경우 기본값

        import threading
        self._threading = threading
        self._lock = threading.Lock()
        self._latest_frame = None
        self._frame_seq = 0
        self._running = False
        self._thread = None

    def start(self):
        if not self.cap.isOpened():
            raise RuntimeError(f"영상을 열 수 없습니다: {self.source}")

        # ---- 섹션 7: 첫 프레임을 실제로 읽어서 확인 (버려지지 않고 _latest_frame으로 그대로 쓰인다) ----
        ret, frame = self.cap.read()
        print(f"{self.log_prefix} First frame read: {ret}")
        if ret:
            h, w = frame.shape[:2]
            print(f"{self.log_prefix} resolution: {w}x{h}  fps(meta)={self.fps:.1f}")
            with self._lock:
                self._latest_frame = frame
                self._frame_seq = 1
        else:
            print(f"{self.log_prefix} 경고: 첫 프레임을 읽지 못했습니다 (파일은 열렸지만 디코딩 실패 가능성).")

        self._running = True
        self._thread = self._threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self

    def _loop(self):
        frame_interval = 1.0 / self.fps if self.pace_to_fps else 0.0
        last_read_time = time.time()

        while self._running:
            ret, frame = self.cap.read()

            if not ret:
                if self.loop_video:
                    # 로컬 mp4 전용: 끝에 도달하면 처음(프레임 0)으로 되감아 계속 재생한다.
                    self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                # HLS는 원래대로(일시적 네트워크 끊김일 수 있으므로 재시도),
                # 되감기를 쓰지 않는 로컬 파일은 여기서 "끝났다"고 표시하고 스레드를 종료한다.
                if self.is_local_file:
                    if not self.ended:
                        print(f"{self.log_prefix} 영상 재생 종료 (EOF)")
                    self.ended = True
                    return  # 더 이상 읽을 게 없으므로 스레드 종료 (get_latest()는 계속 마지막 프레임을 유지)
                time.sleep(0.05)
                continue

            if self.pace_to_fps:
                elapsed = time.time() - last_read_time
                remaining = frame_interval - elapsed
                if remaining > 0:
                    time.sleep(remaining)
                last_read_time = time.time()

            with self._lock:
                self._latest_frame = frame
                self._frame_seq += 1

    def get_latest(self, last_seen_seq):
        with self._lock:
            if self._latest_frame is None or self._frame_seq == last_seen_seq:
                return None, last_seen_seq
            frame = self._latest_frame.copy()
            seq = self._frame_seq
        return frame, seq

    def stop(self):
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        self.cap.release()


class FpsMeter:
    def __init__(self, window=30):
        from collections import deque
        self._times = deque(maxlen=window)

    def tick(self):
        self._times.append(time.time())

    @property
    def fps(self):
        if len(self._times) < 2:
            return 0.0
        return (len(self._times) - 1) / (self._times[-1] - self._times[0])


def draw_test_hud(frame, source_id, name, mode, ai_fps, anomaly_count):
    text = f"[{source_id}] {name}   MODE:{mode}   AI:{ai_fps:.1f}FPS   Anomaly:{anomaly_count}"
    cv2.putText(frame, text, (12, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 4, cv2.LINE_AA)
    cv2.putText(frame, text, (12, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)


# ================================================================
# 6) 소스 1개의 "한 프레임 처리" 루프 - source_worker(병렬/TEST 모드)와
#    run_demo_sequence(순차 발표 모드) 둘 다 이 함수 하나를 그대로 재사용한다.
#    YOLO/ByteTrack 호출 코드를 두 곳에 복사해서 중복 구현하지 않기 위해
#    분리했다 (요구사항: "YOLO/ByteTrack 중복 구현 금지").
#
#    반환값: "ESC"(사용자가 창에서 ESC를 눌러 중단) 또는 "EOF"(이 소스의
#    재생이 자연스럽게 끝남 - loop_video=False인 로컬 mp4에서만 발생).
#    HLS나 loop_video=True인 로컬 mp4는 이 함수가 스스로 끝나지 않는다
#    (외부에서 멈춰야 한다 - 예: 전체 프로세스 종료).
# ================================================================
def run_source_loop(
    source_id, name, config, is_demo, model, ad, mode_settings,
    window_name, show_window, event_queue,
    loop_video, pace_to_fps, reset_tracker_on_first_frame=True,
):
    source_path = config["url"] if config["type"] == "HLS" else os.path.normpath(
        os.path.join(_THIS_DIR, config["path"])
    )

    def map_event_handler(event):
        now = time.time()
        vehicle_id = DEMO_VEHICLE_ID if is_demo else f"{source_id}-{event.track_id}"
        # 섹션 11 규격(source_type/source_id/latitude/longitude/anomaly 등) +
        # map.js EventManager가 이벤트 카드/팝업에 쓰는 부가 필드(reason/track_id/plate/confidence)
        payload = {
            "source_type": "DEMO" if is_demo else "UTIC",
            "source_id": source_id,
            "global_vehicle_id": DEMO_VEHICLE_ID if is_demo else None,
            "vehicle_id": vehicle_id,
            "location_name": name,
            "timestamp": now,
            "time_str": time.strftime("%H:%M:%S", time.localtime(now)),
            "latitude": config["lat"],
            "longitude": config["lng"],
            "anomaly": True,
            "event_type": "ABNORMAL_DRIVING",
            "track_id": event.track_id,
            "reason": event.message,
            "plate": None,  # 이 파이프라인은 번호판을 인식하지 않는다 (D 모듈 담당) - 값을 지어내지 않는다
            "confidence": None,  # detect_weaving()은 규칙 기반 판정이라 수치형 신뢰도가 없다
            "video_position_px": {"x": event.position[0], "y": event.position[1]},
        }
        event_queue.put(payload)

    ad.register_event_handler(map_event_handler)

    log_prefix = f"[DEMO {source_id}]" if is_demo else f"[UTIC {source_id}]"

    try:
        grabber = LatestFrameGrabber(
            source_path, loop_video=loop_video, pace_to_fps=pace_to_fps, log_prefix=log_prefix
        ).start()
    except Exception as e:
        print(f"{log_prefix} 영상 연결 실패: {e}")
        return "FAILED"

    # 이 소스의 실제 fps로 HOLD_WARNING_FRAMES를 계산한다 (영상마다 다를 수 있음).
    # ad.HOLD_WARNING_SECONDS(초 단위 설정값)는 그대로 재사용하고, 프레임 환산만 다시 한다.
    src_fps = grabber.fps
    ad.HOLD_WARNING_FRAMES = max(1, round(ad.HOLD_WARNING_SECONDS * src_fps))

    ai_fps_meter = FpsMeter()
    frame_idx = 0
    process_counter = 0
    last_seq = 0
    anomaly_count_seen = 0
    first_inference_frame = True  # 새 영상의 첫 추론 프레임은 persist=False로 넘겨서 이전 영상의 ByteTrack 상태를 이어받지 않게 한다

    print(f"{log_prefix} {name} 시작 ({config['type']}, fps={src_fps:.1f}, mode={mode_settings['mode']}, loop={loop_video}, pace={pace_to_fps})")

    status = "EOF"
    try:
        while True:
            frame, seq = grabber.get_latest(last_seen_seq=last_seq)
            if frame is None:
                if grabber.ended and not loop_video:
                    status = "EOF"
                    break
                time.sleep(0.005)
                continue
            last_seq = seq
            frame_idx += 1
            process_counter += 1

            annotated = frame.copy()

            if process_counter % mode_settings["process_every"] == 0:
                # ad.detect()는 imgsz/device를 받지 않는 얇은 래퍼라, GPU/CPU별 설정을
                # 반영하기 위해 동일한 호출을 여기서 그대로 반복한다 - 로직(무엇을 검출/추적
                # 하는가)은 ad.VEHICLE_CLASSES / ad.CONF_THRESHOLD를 그대로 가져다 쓰고,
                # 판정 로직 함수 자체는 전혀 새로 만들지 않았다.
                use_persist = not (reset_tracker_on_first_frame and first_inference_frame)
                results = model.track(
                    frame,
                    tracker="bytetrack.yaml",
                    classes=ad.VEHICLE_CLASSES,
                    conf=ad.CONF_THRESHOLD,
                    imgsz=mode_settings["imgsz"],
                    device=mode_settings["device"],
                    persist=use_persist,
                    verbose=False,
                )
                first_inference_frame = False
                ai_fps_meter.tick()

                boxes = results[0].boxes
                if boxes is not None:
                    for box in boxes:
                        if box.id is None:
                            continue
                        x1, y1, x2, y2 = map(int, box.xyxy[0])
                        center = ((x1 + x2) // 2, (y1 + y2) // 2)
                        track_id = int(box.id[0])

                        ad.update_track(track_id, center, frame_idx)  # 원본 그대로
                        ad.handle_anomaly(annotated, (x1, y1, x2, y2), track_id, frame_idx, src_fps)  # 원본 그대로

                        if ad.is_abnormal_active(track_id, frame_idx):
                            anomaly_count_seen = len(
                                [tid for tid, st in ad.track_states.items() if ad.is_abnormal_active(tid, frame_idx)]
                            )

                ad.draw_event_log_panel(annotated)  # 원본 그대로 (좌측 상단 이벤트 로그 패널)

            if DRAW_TEST_HUD:
                draw_test_hud(annotated, source_id, name, mode_settings["mode"], ai_fps_meter.fps, anomaly_count_seen)

            if show_window:
                cv2.imshow(window_name, annotated)
                if cv2.waitKey(1) & 0xFF == 27:
                    status = "ESC"
                    break
    finally:
        grabber.stop()
        ad._event_handlers.remove(map_event_handler)  # 이 소스 전용 핸들러만 제거 (console_event_handler 등은 유지)
        print(f"{log_prefix} {name} 종료 ({status})")

    return status


# ================================================================
# 6B) 소스 1개를 "독립 프로세스"로 처리하는 진입점 (병렬/TEST 모드).
#    anomaly_detection.py는 여기서 import한다 (프로세스마다 독립된
#    모듈 인스턴스가 생기므로, 전역 상태가 다른 소스와 섞이지 않는다).
#    실제 프레임 처리 로직은 위 run_source_loop()를 그대로 호출한다.
# ================================================================
def source_worker(source_id, config, is_demo, mode_settings, event_queue, show_window):
    import anomaly_detection as ad  # 프로세스 전용 독립 인스턴스 - 절대 수정하지 않고 그대로 사용

    name = config["name"]
    log_prefix = f"[DEMO {source_id}]" if is_demo else f"[UTIC {source_id}]"

    ad.register_event_handler(ad.console_event_handler)  # 기존 콘솔 로그도 그대로 유지

    try:
        model = YOLO(mode_settings["model_path"])
    except Exception as e:
        print(f"{log_prefix} YOLO 모델 로딩 실패: {e}")
        return

    window_name = f"{'[DEMO] ' if is_demo else ''}{name} ({source_id})"

    # TEST/병렬 모드: 로컬 Forza mp4(VIDEO)는 재생이 끝나도 창이 멈춘 채로
    # 보이면 "안 되는 건지 끝난 건지" 헷갈리므로, 계속 반복 재생(loop_video=True)
    # 하면서 실제 재생 속도(pace_to_fps=True)로 보여준다. HLS는 원래부터
    # 라이브 스트림이라 두 옵션 모두 LatestFrameGrabber 내부에서 자동 무시된다.
    run_source_loop(
        source_id, name, config, is_demo, model, ad, mode_settings,
        window_name, show_window, event_queue,
        loop_video=(config["type"] == "VIDEO"),
        pace_to_fps=(config["type"] == "VIDEO"),
        reset_tracker_on_first_frame=True,
    )

    if show_window:
        cv2.destroyWindow(window_name)


# ================================================================
# 6C) Forza A→B→C→D 순차 발표 모드 (요구사항 9번 "② DEMO SEQUENCE 모드").
#    독립 프로세스 4개가 아니라, 하나의 프로세스/하나의 창/하나의 YOLO
#    모델 인스턴스로 A를 끝까지 재생 → B → C → D를 순서대로 이어서
#    재생한다. Global Vehicle ID(DEMO_VEHICLE_ID)는 처음부터 끝까지
#    동일하게 유지된다 (source_worker의 map_event_handler와 동일한 로직을
#    run_source_loop 내부에서 공유해서 쓰므로 payload 형식은 완전히 같다).
#
#    각 영상 사이에는 reset_tracker_on_first_frame=True로 호출해서, B의
#    첫 추론 프레임은 A의 ByteTrack 상태를 이어받지 않고 새로 시작한다
#    (영상이 바뀌었는데 이전 영상의 추적 ID/박스 위치를 그대로 이어가면
#    엉뚱한 오탐이 생길 수 있기 때문 - model.track(persist=False)로 리셋).
# ================================================================
REPEAT_SEQUENCE = False  # True로 바꾸면 D 재생이 끝난 뒤 다시 A부터 무한 반복한다 (전시 부스용)


def run_demo_sequence(mode_settings, event_queue, show_window):
    import anomaly_detection as ad  # 이 프로세스 전용 독립 인스턴스

    ad.register_event_handler(ad.console_event_handler)

    try:
        model = YOLO(mode_settings["model_path"])
    except Exception as e:
        print(f"[DEMO SEQUENCE] YOLO 모델 로딩 실패: {e}")
        return

    window_name = f"[DEMO SEQUENCE] 이상운전 시연 - {DEMO_VEHICLE_ID}"
    ordered_sources = sorted(DEMO_SOURCES.items(), key=lambda kv: kv[1]["order"])

    print(f"[DEMO SEQUENCE] 시작: {' → '.join(k for k, _ in ordered_sources)}  (global_vehicle_id={DEMO_VEHICLE_ID})")

    while True:
        for source_id, config in ordered_sources:
            status = run_source_loop(
                source_id, config["name"], config, True, model, ad, mode_settings,
                window_name, show_window, event_queue,
                loop_video=False,  # 시퀀스 모드에서는 한 번 끝까지 재생하고 다음 영상으로 넘어간다
                pace_to_fps=True,  # 실제 재생 시간(예: 7초)만큼 보여준다
                reset_tracker_on_first_frame=True,
            )
            if status == "ESC":
                if show_window:
                    cv2.destroyWindow(window_name)
                print("[DEMO SEQUENCE] 사용자가 ESC로 중단했습니다.")
                return
        if not REPEAT_SEQUENCE:
            break
        print("[DEMO SEQUENCE] A→B→C→D 재생 완료 - REPEAT_SEQUENCE=True이므로 처음부터 다시 시작합니다.")

    if show_window:
        cv2.destroyWindow(window_name)
    print("[DEMO SEQUENCE] 종료")


# ================================================================
# 7) 이벤트 집계 프로세스 - 여러 source_worker가 event_queue에 넣는
#    이벤트를 받아서 콘솔에 출력하고, EVENT_LOG_PATH에 한 줄씩 append하고,
#    MAP_SERVER_EVENTS_URL(server/server.js)로 POST해서 실시간으로
#    web/map.js에 broadcast되게 한다.
#
#    이벤트를 보내는 지점을 이 프로세스 하나로 모아둔 이유는 source_worker와
#    동일하다 - 소스 8개(실제 CCTV 4 + Forza 4)가 각자 서버로 요청을 보내는
#    대신, 한 곳에서만 requests.post를 호출하면 서버 쪽 부하와 로그가
#    훨씬 단순해진다.
# ================================================================
def push_event_to_server(payload, warned_flag):
    """MAP_SERVER_EVENTS_URL로 이벤트를 POST한다. 서버가 꺼져있거나 requests가
    없어도 예외를 여기서 전부 삼켜서, 지도 연동 실패가 AI 탐지 자체를
    멈추게 하지 않는다. 반복적으로 콘솔을 어지럽히지 않도록 경고는 1회만 출력한다.
    warned_flag는 길이 1짜리 list를 넘겨서 클로저 밖에서도 상태를 유지한다.
    """
    if requests is None:
        if not warned_flag[0]:
            print("[MAP EVENT] requests 패키지가 없어 서버로 전송하지 않습니다 (pip install requests).")
            warned_flag[0] = True
        return False
    try:
        res = requests.post(MAP_SERVER_EVENTS_URL, json=payload, timeout=MAP_SERVER_TIMEOUT_SEC)
        if res.status_code >= 400:
            print(f"[MAP EVENT] 서버가 이벤트를 거부했습니다 ({res.status_code}): {res.text[:200]}")
            return False
        return True
    except Exception as e:
        if not warned_flag[0]:
            print(f"[MAP EVENT] 지도 서버({MAP_SERVER_EVENTS_URL}) 연결 실패 - server/server.js가 실행 중인지 확인하세요. ({e})")
            print("[MAP EVENT] (이 경고는 1회만 표시됩니다. AI 탐지 자체는 계속 정상 진행됩니다.)")
            warned_flag[0] = True
        return False


def event_aggregator(event_queue, stop_event):
    warned_flag = [False]
    with open(EVENT_LOG_PATH, "a", encoding="utf-8") as f:
        while not stop_event.is_set():
            try:
                payload = event_queue.get(timeout=0.5)
            except Empty:
                continue
            line = json.dumps(payload, ensure_ascii=False)
            print(f"[MAP EVENT] {line}")
            f.write(line + "\n")
            f.flush()
            push_event_to_server(payload, warned_flag)


def main():
    mode_settings = detect_mode_settings()
    print("=" * 60)
    print(f"MODE: {mode_settings['mode']}")
    if mode_settings["gpu_name"]:
        print(f"GPU: {mode_settings['gpu_name']}")
    print(f"MODEL: {mode_settings['model_path']}  IMG_SIZE: {mode_settings['imgsz']}  PROCESS_EVERY: {mode_settings['process_every']}")
    print(f"실행할 실제 CCTV: {ACTIVE_CAMERA_IDS or '없음'}")
    print(f"RUN_MODE: {RUN_MODE}")
    if RUN_MODE == "PARALLEL":
        print(f"실행할 Forza 데모(병렬): {ACTIVE_DEMO_IDS or '없음'}")
    else:
        print(f"실행할 Forza 데모(순차): {' → '.join(k for k, _ in sorted(DEMO_SOURCES.items(), key=lambda kv: kv[1]['order']))}")
    print(f"지도 이벤트 로그: {EVENT_LOG_PATH}")
    print("=" * 60)

    demo_will_run = bool(ACTIVE_DEMO_IDS) if RUN_MODE == "PARALLEL" else True
    if not ACTIVE_CAMERA_IDS and not demo_will_run:
        print("ACTIVE_CAMERA_IDS / ACTIVE_DEMO_IDS가 둘 다 비어있습니다. 실행할 소스가 없습니다.")
        return

    event_queue = mp.Queue()
    stop_event = mp.Event()

    processes = []

    agg_proc = mp.Process(target=event_aggregator, args=(event_queue, stop_event), daemon=True)
    agg_proc.start()
    processes.append(agg_proc)

    for cam_id in ACTIVE_CAMERA_IDS:
        if cam_id not in CAMERA_SOURCES:
            print(f"경고: CAMERA_SOURCES에 없는 cam_id({cam_id}) - 건너뜁니다.")
            continue
        p = mp.Process(
            target=source_worker,
            args=(cam_id, CAMERA_SOURCES[cam_id], False, mode_settings, event_queue, SHOW_WINDOWS),
        )
        p.start()
        processes.append(p)

    if RUN_MODE == "DEMO_SEQUENCE":
        # ② DEMO SEQUENCE 모드: 창 하나 + 프로세스 하나에서 A→B→C→D를 순서대로 재생.
        # ACTIVE_DEMO_IDS는 이 모드에서는 쓰지 않는다 (DEMO_SOURCES 전체를 order 순으로 재생).
        p = mp.Process(
            target=run_demo_sequence,
            args=(mode_settings, event_queue, SHOW_WINDOWS),
        )
        p.start()
        processes.append(p)
    else:
        # ① PARALLEL(DEBUG/TEST) 모드: ACTIVE_DEMO_IDS에 있는 것만 각각 독립 프로세스로 실행.
        for demo_id in ACTIVE_DEMO_IDS:
            if demo_id not in DEMO_SOURCES:
                print(f"경고: DEMO_SOURCES에 없는 demo_id({demo_id}) - 건너뜁니다.")
                continue
            p = mp.Process(
                target=source_worker,
                args=(demo_id, DEMO_SOURCES[demo_id], True, mode_settings, event_queue, SHOW_WINDOWS),
            )
            p.start()
            processes.append(p)

    try:
        # 소스 프로세스들이 (창에서 ESC를 눌러) 끝날 때까지 대기한다.
        for p in processes[1:]:  # processes[0]은 daemon 집계 프로세스라 제외
            p.join()
    except KeyboardInterrupt:
        print("Ctrl+C 감지 - 종료합니다.")
    finally:
        stop_event.set()
        for p in processes:
            if p.is_alive():
                p.terminate()


if __name__ == "__main__":
    # Windows에서 multiprocessing을 쓸 때 반드시 필요한 가드.
    main()