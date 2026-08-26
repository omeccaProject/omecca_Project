"""위반 감지 실행기 — 불법 유턴 + 신호 위반 (개발 내용 ⑦).

영상 한 편을 넣으면 차량을 잡아 추적하고 두 가지 위반을 찾는다.

  불법 유턴 : 중앙선(노란 실선)을 넘어 진행 방향이 반전된 차량
  신호 위반 : 적색에 정지선을 넘어 진출선까지 통과한 차량

결과는 화면으로 보거나 영상 파일로 저장할 수 있다.
신호 위반을 잡으려면 `draw_roi.py` 에서 정지선(3)·진출선(4)도 그어야 한다.

기본 사용
    python run_uturn.py --video 영상.mp4 --cam CAM-TEST --show

신호까지 반영 (권장)
    python run_uturn.py --video 영상.mp4 --cam CAM-TEST \
        --signal signal_timeline.json --save out/result.mp4

주요 옵션
    --stride N   N프레임마다 1장만 처리 (느리면 2~3으로 올린다)
    --show       실시간 창으로 본다 (q 로 중단)
    --save PATH  판정 결과를 그려 넣은 영상을 저장한다
    --events P   이벤트 JSON 저장 경로 (기본 output/uturn_events.json)
    --lpr        번호판 인식까지 같이 돌린다 (느려진다). 인식된 번호판은
                 게이트웨이 이벤트의 meta.plateNumber 로 실려 대시보드
                 이벤트 리포트의 "차량 번호판" 칸에 뜬다
    --plate-weights PATH  번호판 검출 가중치 (기본 models/plate_det.pt)
    --lpr-mock   모델 없이 더미 번호판으로 흐름만 확인 (실제 번호 아님)
    --plate-hold SEC      번호판 확정 전이면 이만큼 기다렸다 전송 (기본 2초)

준비물
    1) config_zones.json 에 이 카메라의 중앙선이 있어야 한다 → draw_roi.py 로 그린다
    2) 신호 판정을 하려면 signal_timeline.json 이 필요하다 (없으면 금지 구간만 판정)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from collections import deque
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

# [신규] 사건 전/후 캡처 이미지.
#
# a_core(낙하물)와 e_tracking(SmartCCTV, 이상운전)이 이미 쓰고 있는 것과 동일한
# 패턴 - 위반이 잡힌 "그 순간"의 프레임을 "후" 캡처로, 그보다 BEFORE_CAPTURE_SECONDS
# 초 전 프레임을 "전" 캡처로 저장해서 b_dashboard/public/captures/ 에 JPEG로 둔다.
# b_dashboard가 이 폴더를 정적으로 그대로 서빙하므로, 대시보드/리포트는
# "/captures/<uuid>.jpg" 경로만 그대로 쓰면 된다.
PROJECT_ROOT = BASE.parent
CAPTURES_DIR = PROJECT_ROOT / "b_dashboard" / "public" / "captures"
BEFORE_CAPTURE_SECONDS = 2.0


def save_capture(cv2, frame, cam_id: str, tag: str) -> str | None:
    """프레임 1장을 JPEG로 저장하고 "/captures/<uuid>.jpg" 경로를 돌려준다.

    frame이 없거나 저장에 실패해도 None만 돌려주고 예외를 던지지 않는다 -
    캡처 실패가 위반 감지 루프를 멈추면 안 된다.
    """
    if frame is None:
        return None
    CAPTURES_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.jpg"
    filepath = CAPTURES_DIR / filename
    try:
        ok = cv2.imwrite(str(filepath), frame)
    except Exception as e:
        print(f"[CAPTURE] {cam_id}/{tag}: 캡쳐 저장 중 오류: {e}")
        return None
    if not ok:
        print(f"[CAPTURE] {cam_id}/{tag}: 캡쳐 이미지 저장 실패 ({filepath})")
        return None
    return f"/captures/{filename}"

from app.core.schemas import ViolationType                       # noqa: E402
from app.violation.engine import ViolationEngine                 # noqa: E402
from app.core.gateway import GatewayClient                       # noqa: E402
from app.violation.roi import ZoneRegistry                       # noqa: E402
from app.violation.signal_state import (                         # noqa: E402
    PedPhase, SignalPhase, TimelineSignal,
)

# BGR
COLOR = {
    "car": (0, 200, 0),
    "watch": (0, 0, 255),        # 중앙선을 넘어 지켜보는 중 (빨강)
    "violation": (0, 0, 255),
    "center_forbidden": (0, 215, 255),
    "center_allowed": (0, 255, 255),
    "other_line": (200, 200, 200),
}
PHASE_COLOR = {
    SignalPhase.RED: (0, 0, 255),
    SignalPhase.YELLOW: (0, 210, 255),
    SignalPhase.GREEN: (0, 200, 0),
    SignalPhase.LEFT_ARROW: (255, 200, 0),
    SignalPhase.GREEN_LEFT: (255, 200, 0),
    SignalPhase.UNKNOWN: (150, 150, 150),
}
SUBTYPE_KO = {
    "no_sign": "NO U-TURN SIGN",
    "red_light": "RED LIGHT U-TURN",
    "wrong_signal": "WRONG SIGNAL U-TURN",
}

# 이 실행기가 다루는 위반. ⑦ 담당 두 가지를 모두 낸다.
#   엔진은 원래 둘 다 판정하는데, 예전엔 CLI 가 유턴만 걸러 담아
#   신호위반 결과가 조용히 버려지고 있었다.
WATCHED = (ViolationType.ILLEGAL_UTURN, ViolationType.RED_LIGHT)
VTYPE_KO = {
    ViolationType.ILLEGAL_UTURN: "불법 유턴",
    ViolationType.RED_LIGHT: "신호 위반",
}
VTYPE_EN = {
    ViolationType.ILLEGAL_UTURN: "ILLEGAL U-TURN",
    ViolationType.RED_LIGHT: "RED LIGHT VIOLATION",
}


# --------------------------------------------------------------------------
def draw_overlay(cv2, frame, cz, engine, ts, watching, banner):
    for l in cz.lines.values():
        if l.line_type == "center":
            c = COLOR["center_allowed"] if l.uturn_allowed else COLOR["center_forbidden"]
            th = 3
        else:
            c, th = COLOR["other_line"], 2
        cv2.line(frame, tuple(map(int, l.p1)), tuple(map(int, l.p2)), c, th)

    for tid, (bbox, state) in watching.items():
        x1, y1, x2, y2 = bbox.to_xyxy()
        c = COLOR[state]
        cv2.rectangle(frame, (x1, y1), (x2, y2), c, 2 if state == "car" else 3)
        cv2.putText(frame, f"#{tid}", (x1, max(14, y1 - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, c, 2)

    # 상단 상태 표시줄
    h, w = frame.shape[:2]
    cv2.rectangle(frame, (0, 0), (w, 34), (0, 0, 0), -1)
    txt = f"t={ts:5.1f}s  vehicles={len(watching)}  uturn={engine.stats.get('illegal_uturn', 0)}"
    cv2.putText(frame, txt, (10, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)

    if banner:
        label, until = banner
        cv2.rectangle(frame, (0, h - 46), (w, h), (0, 0, 120), -1)
        cv2.putText(frame, label, (12, h - 15), cv2.FONT_HERSHEY_SIMPLEX,
                    0.8, (255, 255, 255), 2)
    return frame


def draw_signal(cv2, frame, signal, cz, ts):
    """현재 신호 상태를 우상단에 표시한다."""
    sig_ids = sorted({l.signal_id for l in cz.lines.values() if l.signal_id})
    x = frame.shape[1] - 250
    y = 55
    for sid in sig_ids:
        ph = signal.phase_at(sid, ts)
        ped = signal.ped_phase_at(sid, ts)
        cv2.circle(frame, (x, y - 5), 9, PHASE_COLOR.get(ph, (150, 150, 150)), -1)
        label = f"{sid}: {ph.value}"
        if ped is not PedPhase.GREEN and ped is not PedPhase.UNKNOWN:
            label += f" / ped {ped.value}"
        elif ped is PedPhase.GREEN:
            label += " / ped green"
        cv2.putText(frame, label, (x + 18, y), cv2.FONT_HERSHEY_SIMPLEX,
                    0.5, (255, 255, 255), 1)
        y += 26


# --------------------------------------------------------------------------
def build_lpr_pipeline(weights: str = "", force_mock: bool = False):
    """실제 학습 모델을 물린 LPR 파이프라인을 만든다.

    `ViolationEngine` 이 인자 없이 만드는 기본 `LPRPipeline()` 은
    config.yaml 의 `lpr.mock`(시연용 더미)을 따르고, 학습해 둔
    `models/plate_det.pt` 도 물지 않는다. 실제 번호판을 읽으려면 검출기와
    인식기를 실사용 설정으로 만들어 넣어 줘야 한다.

    가중치 파일이 없거나 ultralytics/EasyOCR 이 설치돼 있지 않아도 여기서
    죽지 않는다 — `PlateDetector` 는 CV 폴백으로, `PlateRecognizer` 는
    Mock 으로 각자 내려가고 파이프라인은 계속 돈다. 시연 도중 한 부분이
    빠졌다고 위반 감지 전체가 멈추는 것이 더 나쁘기 때문이다.
    """
    from app.lpr.detector import PlateDetector      # noqa: E402
    from app.lpr.pipeline import LPRPipeline        # noqa: E402
    from app.lpr.recognizer import PlateRecognizer  # noqa: E402

    if force_mock:
        print("번호판 인식: MOCK (더미 값 — 실제 번호가 아닙니다)")
        return LPRPipeline(detector=PlateDetector(mock=True),
                           recognizer=PlateRecognizer(mock=True))

    path = Path(weights) if weights else (BASE / "models" / "plate_det.pt")
    if path.exists():
        print(f"번호판 인식: 실제 모델 ({path.name})")
    else:
        print(f"번호판 검출 가중치 없음({path}) → CV 폴백으로 진행합니다.")
        print("  전용 모델을 쓰려면 python install_model.py --check 로 먼저 확인하세요.")

    # easyocr 가 없으면 PlateRecognizer.read() 가 **조용히** Mock 으로 내려간다.
    # 에러가 안 나기 때문에, 대시보드에 그럴듯한 가짜 번호판이 뜨는데도 "실제로
    # 인식되고 있다"고 착각하기 쉽다. 여기서 한 번 크게 알려 준다.
    try:
        import easyocr  # noqa: F401
    except ImportError:
        print("  ⚠ easyocr 미설치 → 번호판 문자는 **더미 값**으로 나갑니다(실제 번호 아님).")
        print("     실제 인식:  pip install easyocr torch  후  python install_model.py --check")

    detector = PlateDetector(weights=str(path) if path.exists() else None, mock=False)
    recognizer = PlateRecognizer(mock=False)
    return LPRPipeline(detector=detector, recognizer=recognizer)

def lerp_point(start, end, ratio):
    return (
        start[0] + (end[0] - start[0]) * ratio,
        start[1] + (end[1] - start[1]) * ratio,
    )


def update_demo_moving_roi(cz, ts, spec):
    start_sec = float(spec["start_sec"])
    end_sec = float(spec["end_sec"])

    if end_sec <= start_sec:
        cz.demo_moving_roi_active = False
        return

    # 이동 구간에서만 RedLightDetector가 이동 ROI 방식으로 계산한다.
    cz.demo_moving_roi_active = start_sec <= ts <= end_sec

    ratio = (ts - start_sec) / (end_sec - start_sec)
    ratio = max(0.0, min(1.0, ratio))

    for line_id, key in (("stop_1", "stop_line"), ("exit_1", "exit_line")):
        line = cz.line(line_id)
        motion = spec.get(key)

        if line is None or motion is None:
            continue

        line.p1 = lerp_point(motion["p1_start"], motion["p1_end"], ratio)
        line.p2 = lerp_point(motion["p2_start"], motion["p2_end"], ratio)


# --------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description="불법 유턴 감지 실행기")
    ap.add_argument("--video", default="", help="입력 영상 (--fake 면 생략 가능)")
    ap.add_argument("--fake", action="store_true",
                    help="합성 영상으로 판정 로직만 점검 (YOLO·영상 불필요)")
    ap.add_argument("--track-log", default="",
                    help="e_tracking(SmartCCTV) 이 만든 추적 JSON 으로 판정 "
                         "(김준호 모듈 결과 사용 · YOLO 불필요)")
    ap.add_argument("--cam", default="CAM-TEST")
    ap.add_argument("--zones", default=str(BASE / "config_zones.json"))
    ap.add_argument("--signal", default="", help="신호 타임라인 JSON (사람이 적은 값)")
    ap.add_argument("--signal-api", action="store_true",
                    help="KLID 실시간 신호 API 사용 (.env 의 SIGNAL_API_KEY)")
    ap.add_argument("--weights", default="yolo11n.pt")
    ap.add_argument("--conf", type=float, default=0.35)
    ap.add_argument("--stride", type=int, default=1)
    ap.add_argument("--imgsz", type=int, default=960)
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--save", default="")
    ap.add_argument("--events", default=str(BASE / "output" / "uturn_events.json"))
    ap.add_argument("--gateway", default="", metavar="URL",
                    help="b_gateway 로도 전송 (예: http://localhost:8080)")
    ap.add_argument("--lpr", action="store_true", help="번호판 인식도 함께 (느림)")
    ap.add_argument("--plate-weights", default="", metavar="PATH",
                    help="번호판 검출 YOLO 가중치. 비워 두면 models/plate_det.pt 를 쓰고, "
                         "그 파일이 없으면 CV 폴백으로 내려간다 (--lpr 일 때만 의미 있음)")
    ap.add_argument("--lpr-mock", action="store_true",
                    help="모델·EasyOCR 없이 더미 번호판으로 화면 흐름만 확인한다 "
                         "(실제 번호가 아니므로 단속/발표 수치에 쓰지 말 것)")
    ap.add_argument("--plate-hold", type=float, default=2.0, metavar="SEC",
                    help="위반이 잡혔는데 번호판이 아직 확정 전이면 이만큼(영상 시각 기준 초) "
                         "기다렸다 전송한다. 0 이면 기다리지 않고 예전처럼 즉시 보낸다")
    ap.add_argument("--mode", choices=["all", "uturn", "signal"], default="all",
                    help="감지 모드 (all: 불법유턴+신호위반, uturn: 불법유턴만, signal: 신호위반만)")
    ap.add_argument(
        "--demo-moving-roi",
        default="",
        metavar="JSON",
        help="1인칭 게임 신호위반 데모 전용 이동 ROI 설정 파일. "
            "정지선/진출선에만 적용하며 불법유턴 ROI에는 적용하지 않음.",
    )
    a = ap.parse_args()

    if a.mode == "uturn":
        watched_types = (ViolationType.ILLEGAL_UTURN,)
    elif a.mode == "signal":
        watched_types = (ViolationType.RED_LIGHT,)
    else:
        watched_types = (ViolationType.ILLEGAL_UTURN, ViolationType.RED_LIGHT)

    # 1인칭 게임 신호위반 데모 전용 이동 ROI 설정
    moving_roi = None

    if a.demo_moving_roi:
        moving_path = Path(a.demo_moving_roi)

        if not moving_path.exists():
            sys.exit(f"이동 ROI 설정 파일이 없습니다: {moving_path}")

        moving_roi = json.loads(moving_path.read_text(encoding="utf-8"))

        if moving_roi.get("camera_id") != a.cam:
            sys.exit(
                "이동 ROI 설정의 camera_id와 --cam 값이 다릅니다. "
                "다른 영상에 적용되는 것을 막기 위해 종료합니다."
            )

        print(f"게임 신호위반 데모 이동 ROI 사용: {moving_path.name}")

    try:
        import cv2
    except ImportError:
        sys.exit("OpenCV 가 필요합니다:  pip install opencv-python")

    if not a.video and not a.fake and not a.track_log:
        sys.exit("--video / --track-log / --fake 중 하나는 지정해야 합니다.")

    # --- ROI ---------------------------------------------------------
    if a.fake:
        from app.violation.synthetic import default_zone_dict
        a.cam = "CAM-FAKE"
        zones = ZoneRegistry.from_dict(default_zone_dict(a.cam))
    else:
        zones = ZoneRegistry.load(a.zones)
    cz = zones.get(a.cam)
    if cz is None:
        sys.exit(f"'{a.cam}' 카메라 설정이 {a.zones} 에 없습니다. "
                 f"먼저 draw_roi.py 로 라인을 그리세요.\n"
                 f"  등록된 카메라: {zones.cam_ids()}")
    # ⑦ 는 두 기능이라 ROI 도 둘 중 하나만 있으면 된다.
    #   중앙선 있음  → 불법 유턴 판정
    #   교차로 있음  → 신호 위반 판정
    centers = cz.center_lines()
    if centers:
        print(f"중앙선 {len(centers)}개: " +
              ", ".join(f"{l.line_id}({'허용' if l.uturn_allowed else '금지'})"
                        for l in centers))
    else:
        print("중앙선 없음 → 불법 유턴은 판정하지 않습니다.")

    if cz.intersections:
        print(f"교차로 {len(cz.intersections)}개: " + ", ".join(cz.intersections))
    else:
        print("교차로(정지선) 없음 → 신호 위반은 판정하지 않습니다.")

    if a.mode == "uturn" and not centers:
        sys.exit(f"'{a.cam}' 에 중앙선 ROI가 없습니다. draw_roi.py 로 중앙선을 먼저 그려주세요.")
    if a.mode == "signal" and not cz.intersections:
        sys.exit(f"'{a.cam}' 에 정지선/교차로 ROI가 없습니다. draw_roi.py 로 정지선(3)/진출선(4)을 먼저 그려주세요.")
    if not centers and not cz.intersections:
        sys.exit(f"'{a.cam}' 에 중앙선도 정지선도 없습니다.\n"
                 f"  draw_roi.py 로 중앙선(1·2) 또는 정지선·진출선(3·4)을 그려 주세요.")

    # --- 신호 --------------------------------------------------------
    api_signal = None
    if a.signal_api:
        from app.violation.signal_klid import KlidSignal

        api_signal = KlidSignal()
        ok, why = api_signal.ready()
        print(f"신호 API: {why}")
        if not ok:
            sys.exit("  python signal_probe.py 로 먼저 설정을 확인하세요.")
        api_signal.start()
        signal = api_signal
    elif a.fake and not a.signal:
        from app.violation.synthetic import fake_signal_timeline

        signal = TimelineSignal(fake_signal_timeline(), start_ts=0.0)
        print("합성 신호: 전 구간 적색 (신호위반 판정용)")
    elif a.signal:
        signal = TimelineSignal.from_file(a.signal, start_ts=0.0)
        print(f"신호 타임라인: {a.signal}")
    else:
        signal = TimelineSignal()
        print("신호 타임라인 없음 → 유턴 금지 구간(no_sign)만 판정합니다.")

    # 실시간 API 는 '지금' 을 말한다. 녹화 영상의 t=0 을 지금으로 맞추면
    # 판정 시각이 어긋나므로, 실시간 API 는 실시간 입력에만 쓴다.
    if api_signal is not None and a.video:
        print("  주의: 녹화 영상 + 실시간 API 는 시각이 맞지 않습니다.")
        print("        녹화본 판정에는 --signal 타임라인을 쓰세요.")

    # --- 번호판 인식 -------------------------------------------------
    # ViolationEngine 은 lpr=None 이면 기본 LPRPipeline() 을 스스로 만든다.
    # 그 기본값은 config.yaml 의 lpr.mock(=시연용 더미)을 따르고 학습된 가중치도
    # 물지 않는다. --lpr 을 켰을 때만 실제 모델을 물린 파이프라인을 만들어 주입한다
    # — 안 켰을 때의 동작은 예전과 완전히 같다.
    lpr_pipeline = None
    if a.lpr:
        lpr_pipeline = build_lpr_pipeline(a.plate_weights, a.lpr_mock)

    # --- 엔진 --------------------------------------------------------
    engine = ViolationEngine(zones=zones, signal_provider=signal, lpr=lpr_pipeline)

    gw = None
    forwarder = None
    if a.gateway:
        gw = GatewayClient(base_url=a.gateway).start()
        if a.lpr and a.plate_hold > 0:
            # 위반은 라인을 넘는 "그 순간" 확정되고, 번호판은 여러 프레임을 모아
            # 확정된다. 즉시 보내면 이벤트 리포트의 "차량 번호판"이 빈 채로 굳는다.
            # subscribe_to_bus() 와 둘 다 붙이면 같은 이벤트가 두 번 나가므로 하나만.
            from app.core.plate_hold import PlateHoldForwarder  # noqa: E402

            forwarder = PlateHoldForwarder(
                gateway=gw, lpr=engine.lpr, matcher=engine.matcher,
                hold_sec=a.plate_hold,
            ).attach()
            print(f"게이트웨이 전송: {gw.url}  (번호판 확정 대기 {a.plate_hold:g}초)")
        else:
            gw.subscribe_to_bus()
            print(f"게이트웨이 전송: {gw.url}")

    # --- 차량 검출 ---------------------------------------------------
    if a.fake:
        from app.violation.synthetic import SyntheticSource
        src = SyntheticSource(cam_id=a.cam, stride=a.stride)
        print("합성 모드: 유턴·좌회전·직진·신호위반 4대 → "
              "유턴 1건 + 신호위반 1건, 정확히 2건이 정상")
    elif a.track_log:
        from app.violation.track_log import TrackLogSource

        src = TrackLogSource(a.track_log, video=a.video, cam_id=a.cam,
                             stride=a.stride)
        print(src.describe())
        if src.log_cam_id and src.log_cam_id != a.cam:
            print(f"  참고: 로그의 cam_id 는 '{src.log_cam_id}' 인데 "
                  f"'{a.cam}' 으로 판정합니다 (ROI 설정 기준).")
        print("  " + src.episode_summary().replace("\n", "\n  "))
    else:
        try:
            from app.violation.vehicle_track import VehicleSource
        except ImportError:
            sys.exit("ultralytics 가 필요합니다:  pip install ultralytics")
        src = VehicleSource(a.video, cam_id=a.cam, weights=a.weights, conf=a.conf,
                            stride=a.stride, imgsz=a.imgsz)

    writer = None
    events: list[dict] = []
    banner = None
    t_start = time.time()
    processed = 0

    # 최근 BEFORE_CAPTURE_SECONDS초 분량의 (영상 시각, 프레임)만 들고 있는다.
    # 위반이 잡히는 순간 frame_buffer[0]이 "그 몇 초 전" 프레임이 된다 - a_core/
    # e_tracking의 first_frame/frame_buffer와 동일한 역할.
    frame_buffer: deque = deque()
    # 위반 잡힌 순간 곧바로 PATCH를 보내면, --plate-hold로 이벤트 POST 자체가
    # 뒤로 미뤄져 있을 때 캡처 PATCH가 이벤트 생성보다 먼저 게이트웨이에 도착해
    # "그 trackId 이벤트가 아직 없음"으로 조용히 무시될 수 있다. 이벤트가 실제로
    # 나갈 시점 이후에 PATCH가 도착하도록 그만큼 지연을 준다.
    capture_delay_sec = (a.plate_hold + 0.5) if (forwarder is not None) else 0.0

    for frame_no, ts, frame, dets in src.frames():
        processed += 1

        # 1인칭 게임 신호위반 데모일 때만 stop/exit ROI를 이동한다.
        # center ROI는 건드리지 않으므로 불법유턴 판정에는 영향이 없다.
        if moving_roi is not None:
            update_demo_moving_roi(cz, ts, moving_roi)

        if writer is None and a.save:
            Path(a.save).parent.mkdir(parents=True, exist_ok=True)
            writer = cv2.VideoWriter(
                a.save,
                cv2.VideoWriter_fourcc(*"mp4v"),
                src.fps / a.stride,
                src.size,
            )

        frame_buffer.append((ts, frame))
        while frame_buffer and ts - frame_buffer[0][0] > BEFORE_CAPTURE_SECONDS:
            frame_buffer.popleft()

        watching: dict[int, tuple] = {}
        for d in dets:
            evs = engine.process(d, frame=frame if a.lpr else None)
            # 유턴 후보(중앙선 통과) 또는 신호위반 후보(적색 정지선 통과)
            pend = (any(k[1] == d.track_id for k in engine.uturn._pending)
                    or any(k[1] == d.track_id for k in engine.red_light._pending))
            state = "watch" if pend else "car"
            for ev in evs:
                if ev.violation_type not in watched_types:
                    continue          # 고위험 차량 경보 등은 엔진이 따로 처리
                state = "violation"
                payload = ev.to_payload()
                if frame is not None:
                    tag = "uturn" if ev.violation_type == ViolationType.ILLEGAL_UTURN else "signal"
                    cap_path = save_capture(cv2, frame, a.cam, tag)
                    if cap_path:
                        payload["frame_before"] = cap_path
                        payload["frame_after"] = cap_path
                        # forwarder의 pending item에도 캡처 경로 주입
                        if forwarder is not None:
                            for item in forwarder._pending:
                                if item.track_id == ev.track_id:
                                    item.payload["frame_before"] = cap_path
                                    item.payload["frame_after"] = cap_path
                events.append(payload)
                label = (SUBTYPE_KO.get(ev.subtype) or VTYPE_EN[ev.violation_type])
                banner = (f"[{label}] track #{ev.track_id}  t={ts:.1f}s", ts + 2.0)
                print(f"\n  ★ {VTYPE_KO[ev.violation_type]}  t={ts:6.2f}s  "
                      f"track=#{ev.track_id}  "
                      f"{ev.subtype or ev.zone_id}  {ev.detail}")

                # [신규] 사건 전/후 캡처 - "전"은 frame_buffer에 남아있는 가장 오래된
                # (=이 순간 기준 BEFORE_CAPTURE_SECONDS초 전) 프레임, "후"는 위반이
                # 확정된 바로 이 프레임.
                before_frame = frame_buffer[0][1] if frame_buffer else None
                frame_ref_before = save_capture(cv2, before_frame, a.cam, "before")
                frame_ref_after = save_capture(cv2, frame, a.cam, "after")
                if gw is not None and (frame_ref_before or frame_ref_after):
                    gw.update_captures(
                        f"trk-{ev.track_id}", frame_ref_before, frame_ref_after,
                        delay_sec=capture_delay_sec,
                    )
            watching[d.track_id] = (d.bbox, state)

        # 보류 중인 위반 이벤트 중 번호판이 확정됐거나 대기 시간을 넘긴 건을 내보낸다.
        if forwarder is not None:
            forwarder.tick(ts)

        if banner and ts > banner[1]:
            banner = None

        if a.show or writer is not None:
            vis = draw_overlay(cv2, frame.copy(), cz, engine, ts, watching, banner)
            draw_signal(cv2, vis, signal, cz, ts)
            if writer is not None:
                writer.write(vis)
            if a.show:
                cv2.imshow("uturn", cv2.resize(vis, None, fx=0.6, fy=0.6))
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

        if processed % 30 == 0:
            print(f"\r  {frame_no+1}/{src.total or '?'} 프레임  "
                  f"({processed / max(1e-6, time.time() - t_start):.1f} fps 처리)",
                  end="", flush=True)

    if api_signal is not None:
        api_signal.stop()
        print(f"\n신호 API 폴링 {api_signal.stats['polls']}회 "
              f"(성공 {api_signal.stats['ok']} / 실패 {api_signal.stats['failed']})")
    if forwarder is not None:
        # 영상이 끝나는 순간까지 보류돼 있던 건은 있는 그대로라도 반드시 내보낸다.
        forwarder.flush()
        forwarder.detach()
        print(f"번호판 대기 결과: {forwarder.stats}")
    if gw is not None:
        gw.stop(drain=True)
        print(f"게이트웨이 전송 결과: {gw.stats}")
    if writer is not None:
        writer.release()
    if a.show:
        cv2.destroyAllWindows()

    # --- 결과 --------------------------------------------------------
    out = Path(a.events)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "video": a.video or "(synthetic)", "cam_id": a.cam, "tracker": src.tracker_name,
        "frames_processed": processed, "events": events,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n\n처리 프레임 {processed}  |  추적기 {src.tracker_name}")
    if a.track_log:
        print(f"박스 {src.stats['boxes']}개 (e_tracking 이상운전 표시 "
              f"{src.stats['alerts']}개)")
    by_type: dict[str, list] = {}
    for e in events:
        by_type.setdefault(e["type"], []).append(e)

    print(f"위반 {len(events)}건 "
          f"(불법 유턴 {len(by_type.get('illegal_uturn', []))} / "
          f"신호 위반 {len(by_type.get('red_light', []))})")
    for e in events:
        print(f"  - t={e['timestamp']:6.2f}s  {e['label']}  track=#{e['track_id']}  "
              f"{e['subtype'] or '-':<13} {e['zone_id']}")
    if not events:
        print("  (없음) 위반이 안 잡히면 UTURN_GUIDE.md 7장을 보세요.")
    print(f"이벤트 저장 → {out}")
    if a.save:
        print(f"결과 영상 저장 → {a.save}")


if __name__ == "__main__":
    main()
