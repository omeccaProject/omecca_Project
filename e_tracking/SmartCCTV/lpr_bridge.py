"""e_tracking(이상운전 감지) ↔ d_lpr(번호판 인식) 다리.

왜 이 파일이 있는가
----------------------------------------------------------------
realtime_anomaly.py 는 이미 YOLO + ByteTrack 으로 차량 박스와 track_id 를
프레임마다 뽑고 있다. 번호판을 읽으려고 차량 검출을 한 번 더 돌릴 이유가
없다 — 그 박스를 그대로 d_lpr(박지원 담당) 의 LPR 파이프라인에 넘기면 된다.

이 모듈은 그 전달만 담당한다.

    realtime_anomaly.py  ──(차량 박스 + 프레임)──▶  LPRPipeline  ──▶ 확정 번호판
                         ◀──(track_id 로 조회)───

지키는 것
----------------------------------------------------------------
- anomaly_detection.py 는 한 줄도 건드리지 않는다. 이 모듈은 그 바깥에서
  "이미 나온 박스" 만 받아 쓴다.
- d_lpr 쪽 코드도 수정하지 않는다. 공개 API(`LPRPipeline.process` /
  `confirmed_plate`)만 호출한다.
- d_lpr 이 없거나 모델·EasyOCR 이 설치돼 있지 않으면 조용히 꺼진 상태로
  동작한다(`available == False`). 번호판을 못 읽는다고 이상운전 탐지
  자체가 멈추면 안 되기 때문이다.

번호판은 한 프레임 OCR 로 확정하지 않는다. 같은 track 의 여러 프레임을 모아
가중 다수결로 확정한다(d_lpr `LPRPipeline.TrackVote`). 그래서 `update()` 를
여러 프레임에 걸쳐 계속 먹여야 `plate_of()` 가 값을 돌려주기 시작한다.
"""

from __future__ import annotations

import os
import sys
import time

# 이 파일 → e_tracking/SmartCCTV/ → e_tracking/ → 프로젝트 루트
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_THIS_DIR, "..", ".."))
_D_LPR_DIR = os.path.join(_PROJECT_ROOT, "d_lpr")

# 기본 번호판 검출 가중치. 없으면 d_lpr 이 알아서 CV 폴백으로 내려간다.
DEFAULT_PLATE_WEIGHTS = os.path.join(_D_LPR_DIR, "models", "plate_det.pt")

# 매 프레임 모든 차량에 OCR 을 돌리면 실시간 처리가 무너진다. track 당
# 이만큼의 호출 간격을 둔다(다수결에 필요한 표는 그래도 충분히 모인다).
DEFAULT_INTERVAL = 5


class PlateReader:
    """차량 박스를 받아 번호판을 읽고, track_id 로 되돌려 준다.

    프로세스마다 하나씩 만든다. realtime_anomaly.py 가 소스(영상)마다 완전히
    독립된 프로세스로 도는 구조라, 이 객체도 그 안에서만 살면 track_id 가
    다른 영상과 섞이지 않는다.
    """

    def __init__(self, weights: str | None = None, mock: bool = False,
                 interval: int = DEFAULT_INTERVAL, log_prefix: str = "[LPR]"):
        self.available = False
        self.log_prefix = log_prefix
        self.interval = max(1, int(interval))
        self._pipeline = None
        self._last_call: dict[tuple[str, int], int] = {}
        self._calls = 0

        try:
            self._pipeline = self._build(weights, mock)
            self.available = self._pipeline is not None
        except Exception as e:  # d_lpr 미설치/의존성 부족 등 — 여기서 죽지 않는다
            print(f"{log_prefix} 번호판 인식을 켜지 못했습니다({type(e).__name__}: {e}). "
                  f"이상운전 탐지는 그대로 진행합니다.")
            self.available = False

    # ------------------------------------------------------------------
    def _build(self, weights: str | None, mock: bool):
        if _D_LPR_DIR not in sys.path:
            # append 로 붙인다 - insert(0) 로 앞에 두면 d_lpr 의 일반적인 모듈명
            # (`app` 등)이 이 프로세스의 다른 import 를 가릴 수 있다.
            sys.path.append(_D_LPR_DIR)

        from app.lpr.detector import PlateDetector          # noqa: E402
        from app.lpr.pipeline import LPRPipeline            # noqa: E402
        from app.lpr.recognizer import PlateRecognizer      # noqa: E402
        from app.core.schemas import BBox, Detection, ObjectClass  # noqa: E402

        self._BBox = BBox
        self._Detection = Detection
        self._ObjectClass = ObjectClass

        if mock:
            print(f"{self.log_prefix} MOCK 모드 — 더미 번호판입니다(실제 번호 아님).")
            return LPRPipeline(detector=PlateDetector(mock=True),
                               recognizer=PlateRecognizer(mock=True))

        path = weights or DEFAULT_PLATE_WEIGHTS
        if os.path.exists(path):
            print(f"{self.log_prefix} 번호판 검출 모델 사용: {os.path.basename(path)}")
        else:
            path = None
            print(f"{self.log_prefix} 번호판 검출 가중치 없음 → CV 폴백으로 진행합니다.")

        # easyocr 가 없으면 d_lpr 의 PlateRecognizer 가 조용히 Mock 으로 내려간다.
        # 에러가 안 나서 "가짜 번호판인 줄 모르고" 넘어가기 쉬우므로 여기서 경고한다.
        try:
            import easyocr  # noqa: F401
        except ImportError:
            print(f"{self.log_prefix} ⚠ easyocr 미설치 → 번호판이 **더미 값**으로 나갑니다"
                  f"(실제 번호 아님). 실제 인식: pip install easyocr torch")

        return LPRPipeline(detector=PlateDetector(weights=path, mock=False),
                           recognizer=PlateRecognizer(mock=False))

    # ------------------------------------------------------------------
    def update(self, cam_id: str, track_id: int, xyxy, frame,
               frame_no: int = 0, ts: float | None = None) -> None:
        """차량 박스 1개를 파이프라인에 먹인다.

        `xyxy` 는 (x1, y1, x2, y2) 정수 튜플 — realtime_anomaly.py 의
        `box.xyxy[0]` 에서 나온 값을 그대로 넘기면 된다.

        이미 번호판이 확정된 track, 또는 아직 호출 간격이 안 된 track 은
        건너뛴다. 어떤 예외가 나도 밖으로 던지지 않는다 — 번호판 때문에
        탐지 루프가 멈추는 일은 없어야 한다.
        """
        if not self.available or frame is None:
            return

        key = (cam_id, int(track_id))
        if self._pipeline.confirmed_plate(cam_id, int(track_id)):
            return  # 이미 확정됨 - 더 읽을 필요 없다
        if frame_no - self._last_call.get(key, -10**9) < self.interval:
            return
        self._last_call[key] = frame_no

        x1, y1, x2, y2 = (int(v) for v in xyxy)
        det = self._Detection(
            cam_id=cam_id,
            track_id=int(track_id),
            # ad.VEHICLE_CLASSES 로 이미 차량만 걸러진 박스라서 CAR 로 넘긴다.
            # LPR 파이프라인은 "차량인가" 만 보고 세부 차종은 쓰지 않는다.
            cls=self._ObjectClass.CAR,
            bbox=self._BBox(x1, y1, x2, y2),
            timestamp=ts if ts is not None else time.time(),
            frame_no=int(frame_no),
        )
        try:
            self._pipeline.process(det, frame=frame)
            self._calls += 1
        except Exception:
            pass  # 한 프레임 실패는 다음 프레임에서 만회된다

    # ------------------------------------------------------------------
    def plate_of(self, cam_id: str, track_id: int) -> str | None:
        """확정된 번호판. 아직 확정 전이면 None."""
        if not self.available:
            return None
        try:
            return self._pipeline.confirmed_plate(cam_id, int(track_id)) or None
        except Exception:
            return None

    def confidence_of(self, cam_id: str, track_id: int) -> float | None:
        if not self.available:
            return None
        try:
            conf = self._pipeline.confidence_of(cam_id, int(track_id))
            return round(float(conf), 4) if conf else None
        except Exception:
            return None

    def prune(self, now: float | None = None, ttl_sec: float = 300.0) -> None:
        """오래된 track 정리. 장시간(며칠) 돌 때 메모리가 계속 늘지 않게 한다."""
        if not self.available:
            return
        try:
            self._pipeline.prune(ttl_sec=ttl_sec, now=now)
        except Exception:
            pass
        if len(self._last_call) > 5000:
            self._last_call.clear()

    @property
    def stats(self) -> dict:
        if not self.available:
            return {"available": False}
        out = {"available": True, "calls": self._calls}
        try:
            out.update(self._pipeline.stats)
        except Exception:
            pass
        return out
