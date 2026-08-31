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
# [신규: 사용자 요청 - "차 뒷바퀴가 정지선을 넘어서 한 번 찍고, 다 넘고 2초 뒤 한 번
# 더 찍어달라"] 신호위반(RED_LIGHT)은 유턴과 캡처 타이밍 개념이 다르다 - 유턴은
# "위반 전 상태"를 보여주는 게 중요해서 판정 이전 프레임을 쓰지만, 신호위반은
# "정지선을 넘는 그 순간"이 이미 위반 증거이므로 그걸 첫 캡처로 쓰고, 두 번째
# 캡처는 그로부터 AFTER_CAPTURE_SIGNAL_SECONDS(영상 시각 기준)초 뒤 - 차량이
# 교차로를 완전히 통과한 모습을 보여준다.
AFTER_CAPTURE_SIGNAL_SECONDS = 2.0


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
def draw_overlay(cv2, frame, cz, engine, ts, watching, banner, cam_id=None):
    for l in cz.lines.values():
        if l.line_type == "center":
            c = COLOR["center_allowed"] if l.uturn_allowed else COLOR["center_forbidden"]
            th = 3
        else:
            c, th = COLOR["other_line"], 2
        cv2.line(frame, tuple(map(int, l.p1)), tuple(map(int, l.p2)), c, th)

    # 변경 후
    for tid, (bbox, state) in watching.items():
        x1, y1, x2, y2 = bbox.to_xyxy()
        c = COLOR[state]
        cv2.rectangle(frame, (x1, y1), (x2, y2), c, 2 if state == "car" else 3)
        cv2.putText(frame, f"#{tid}", (x1, max(14, y1 - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, c, 2)

        # 번호판 인식 상태를 박스 바로 아래에 표시한다. 확정 전(투표 중)이면
        # 노란색 + "?", 확정되면 초록색으로 - 시연 화면에서 "인식 중"이 눈에 보이게.
        if engine.lpr is not None and cam_id is not None:
            plate_no, is_confirmed = engine.lpr.leading_plate(cam_id, tid)
            if plate_no:
                label = plate_no if is_confirmed else f"{plate_no}?"
                plate_color = (0, 255, 0) if is_confirmed else (0, 230, 255)
                cv2.putText(frame, label, (x1, y2 + 20),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 3)
                cv2.putText(frame, label, (x1, y2 + 20),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, plate_color, 2)

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

# 새로 추가 (main() 함수 정의 바로 위)
def run_journey_follow(a) -> None:
    """--journey-role follow 전용 경로. ROI(config_zones.json)도, ViolationEngine도
    거치지 않는다 - 이 카메라는 실제 위반을 판정하지 않고, 영상에 차량이 처음
    나타나는 순간 이전 카메라(--journey-peer-cam)의 확정 번호판을 그대로 이어받아
    /api/cctv/journey 로 Journey 연장만 보낸다."""
    if not a.video:
        sys.exit("--journey-role follow 는 --video 가 필요합니다.")
    if not a.gateway:
        sys.exit("--journey-role follow 는 --gateway 가 필요합니다 "
                 "(이전 카메라 번호판 조회 + Journey 전송).")

    # 변경 후
    from app.core.journey import (
        fetch_latest_plate, send_journey_update, CAMERA_LOCATIONS, build_route_points,
    )

    if a.cam not in CAMERA_LOCATIONS:
        sys.exit(f"'{a.cam}' 의 위경도가 app/core/journey.py CAMERA_LOCATIONS 에 없습니다. "
                 f"먼저 한 줄 추가하세요.")

    # 변경 후
    plate = (fetch_latest_plate(a.gateway, a.journey_peer_cam,
                               event_type=a.journey_peer_event_type)
             if a.journey_peer_cam else "")
    if plate:
        print(f"Journey: {a.journey_peer_cam}에서 확정된 번호판 '{plate}'을 이어받습니다.")
    else:
        print(f"Journey: {a.journey_peer_cam}의 확정 번호판을 아직 못 찾았습니다 "
              f"(먼저 그 카메라를 --journey-role start 로 돌려 위반을 확정시켜 두세요). "
              f"번호판 없이 이어집니다.")

    try:
        import cv2
    except ImportError:
        sys.exit("OpenCV 가 필요합니다:  pip install opencv-python")
    try:
        from app.violation.vehicle_track import VehicleSource
    except ImportError:
        sys.exit("ultralytics 가 필요합니다:  pip install ultralytics")

    src = VehicleSource(a.video, cam_id=a.cam, weights=a.weights, conf=a.conf,
                        stride=a.stride, imgsz=a.imgsz)

    writer = None
    sent = False
    target_track_id = None

    processed = 0
    t_start = time.time()
    for frame_no, ts, frame, dets in src.frames():
        processed += 1

        # 변경 후
        if not sent and dets:
            # 변경 후
            # dets[0]은 그냥 검출 리스트의 첫 항목일 뿐, 화면에 실제로 가장
            # 눈에 띄는(=이어받아야 할) 차량이 아닐 수 있다(여러 대가 동시에
            # 잡히는 영상에서 확인됨). 바운딩 박스 면적이 가장 큰 차량 - 보통
            # 카메라에 가장 가깝고 크게 나온 차량 - 을 표적으로 삼는다.
            def _bbox_area(d):
                x1, y1, x2, y2 = d.bbox.to_xyxy()
                return max(0, x2 - x1) * max(0, y2 - y1)

            target_track_id = max(dets, key=_bbox_area).track_id

            peer_loc = CAMERA_LOCATIONS.get(a.journey_peer_cam)
            here_loc = CAMERA_LOCATIONS[a.cam]
            if peer_loc:
                points = build_route_points(peer_loc, here_loc)
            else:
                points = [{"lat": here_loc["lat"], "lng": here_loc["lng"]}]
            send_journey_update(a.gateway, True, a.cam, points)
            print(f"\n  ★ Journey 연장  t={ts:6.2f}s  {a.journey_peer_cam} → {a.cam}"
                  + (f"  번호판={plate}" if plate else "")
                  + f"  track=#{target_track_id}")
            sent = True
            if not (a.show or a.save):
                break  # --show/--save 둘 다 없으면 트리거 즉시 종료 (영상 끝까지 돌 필요 없음)

        # 변경 후
        if writer is None and a.save:
            Path(a.save).parent.mkdir(parents=True, exist_ok=True)
            writer = cv2.VideoWriter(
                a.save,
                cv2.VideoWriter_fourcc(*"mp4v"),
                src.fps / a.stride,
                src.size,
            )

        # 변경 후
        if a.show or writer is not None:
            vis = frame.copy()
            for d in dets:
                is_target = (d.track_id == target_track_id)
                x1, y1, x2, y2 = d.bbox.to_xyxy()
                color = (0, 200, 0) if is_target else (150, 150, 150)
                cv2.rectangle(vis, (x1, y1), (x2, y2), color, 2)
                cv2.putText(vis, f"#{d.track_id}", (x1, max(14, y1 - 6)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
                # 표적 차량(트리거 시점에 잡힌 track_id)에만 이전 카메라에서
                # 이어받은 번호판을 표시한다. 실제 재인식이 아니라 "같은 차량이
                # 여기서도 추적되고 있다"는 시연용 오버레이일 뿐, 신호위반/불법유턴
                # 판정은 하지 않는다.
                if is_target and plate:
                    cv2.putText(vis, plate, (x1, y2 + 20),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 3)
                    cv2.putText(vis, plate, (x1, y2 + 20),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)
            if writer is not None:
                writer.write(vis)
            if a.show:
                cv2.imshow("journey-follow", cv2.resize(vis, None, fx=0.6, fy=0.6))
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

        if processed % 30 == 0:
            print(f"\r  {frame_no+1}/{src.total or '?'} 프레임  "
                  f"({processed / max(1e-6, time.time() - t_start):.1f} fps 처리)",
                  end="", flush=True)

    if writer is not None:
        writer.release()
    if a.show:
        cv2.destroyAllWindows()
    if not sent:
        print("\n  ⚠ 영상 전체에서 차량이 한 번도 감지되지 않아 Journey를 보내지 못했습니다.")
    print(f"\n처리 프레임 {processed}")
    if a.save:
        print(f"결과 영상 저장 → {a.save}")

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
    # 변경 후
    ap.add_argument("--mode", choices=["all", "uturn", "signal"], default="all",
                    help="감지 모드 (all: 불법유턴+신호위반, uturn: 불법유턴만, signal: 신호위반만)")
    ap.add_argument("--journey-role", choices=["", "start", "follow"], default="",
                    help="GIS 이동 경로(Journey) 데모용. 'start': 이 카메라에서 위반이 잡히면 "
                         "여정을 시작한다(예: 한강중학교/L010321). 'follow': 이전 카메라"
                         "(--journey-peer-cam)에서 확정된 번호판을 그대로 이어받아 이 카메라"
                         "에서도 같은 차량으로 잡은 것처럼 여정을 연장한다(예: 녹사평역/L010062).")
    ap.add_argument("--journey-peer-cam", default="", metavar="CAM_ID",
                    help="--journey-role follow 일 때, 바로 이전 지점의 cam_id. 그 카메라의 "
                         "가장 최근 확정 번호판을 자동으로 가져와 이 카메라 LPR 결과 대신 "
                         "강제로 사용한다.")
    ap.add_argument("--journey-peer-event-type", default="SIGNAL_VIOLATION",
                choices=["SIGNAL_VIOLATION", "UTURN_VIOLATION"],
                help="--journey-role follow 일 때, 이전 카메라(--journey-peer-cam)에서 "
                        "어떤 종류의 위반 이벤트로 확정된 번호판을 찾을지. 신호위반 여정이면 "
                        "SIGNAL_VIOLATION(기본값), 불법유턴 여정이면 UTURN_VIOLATION.")
    ap.add_argument(
        "--demo-moving-roi",
        default="",
        metavar="JSON",
        help="1인칭 게임 신호위반 데모 전용 이동 ROI 설정 파일. "
            "정지선/진출선에만 적용하며 불법유턴 ROI에는 적용하지 않음.",
    )
    # 변경 후
    a = ap.parse_args()

    if a.journey_role == "follow":
        # 이 카메라는 ROI도 ViolationEngine도 필요 없다 - 차량이 나타나는 순간
        # 이전 카메라의 확정 번호판을 그대로 이어받아 Journey만 보낸다.
        run_journey_follow(a)
        return

    if a.mode == "uturn":
        watched_types = (ViolationType.ILLEGAL_UTURN,)
        # [버그 수정] 반대쪽(--mode signal) 프로세스가 담당하는 유형은 게이트웨이로
        # 보내지 않는다 - 안 그러면 중앙선+정지선이 둘 다 있는 카메라에서 두 프로세스가
        # 같은 위반을 각자 감지해 이벤트가 중복으로 뜬다 (plate_hold.py 주석 참고).
        excluded_types = {ViolationType.RED_LIGHT.value}
    elif a.mode == "signal":
        watched_types = (ViolationType.RED_LIGHT,)
        excluded_types = {ViolationType.ILLEGAL_UTURN.value}
    else:
        watched_types = (ViolationType.ILLEGAL_UTURN, ViolationType.RED_LIGHT)
        excluded_types = set()

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

    # 변경 후
    gw = None
    forwarder = None
    if a.gateway:
        gw = GatewayClient(base_url=a.gateway).start()

        force_plate = ""
        if a.journey_role == "follow" and a.journey_peer_cam:
            from app.core.journey import fetch_latest_plate  # noqa: E402

            force_plate = fetch_latest_plate(a.gateway, a.journey_peer_cam,
                                            event_type=a.journey_peer_event_type)
            if force_plate:
                print(f"Journey: {a.journey_peer_cam}에서 확정된 번호판 '{force_plate}'을 "
                      f"이어받아 이 카메라에서 강제로 사용합니다.")
            else:
                print(f"Journey: {a.journey_peer_cam}의 확정 번호판을 아직 못 찾았습니다 "
                      f"(먼저 그 카메라를 --journey-role start 로 돌려 위반을 확정시켜 두세요). "
                      f"이번 실행에서는 번호판 없이 이어집니다.")

        # 위반은 라인을 넘는 "그 순간" 확정되고, 번호판은 여러 프레임을 모아
        # 확정된다. 즉시 보내면 이벤트 리포트의 "차량 번호판"이 빈 채로 굳는다.
        # subscribe_to_bus() 와 둘 다 붙이면 같은 이벤트가 두 번 나가므로 하나만.
        # journey_role이 설정된 경우, --lpr 없이도 force_plate만으로 이어지도록
        # forwarder를 만든다(신호위반2 카메라는 자체 LPR 없이도 동작해야 하므로).
        if (a.lpr and a.plate_hold > 0) or a.journey_role:
            from app.core.plate_hold import PlateHoldForwarder  # noqa: E402

            forwarder = PlateHoldForwarder(
                gateway=gw, lpr=engine.lpr if a.lpr else None, matcher=engine.matcher,
                hold_sec=a.plate_hold, excluded_types=frozenset(excluded_types),
                gateway_origin=a.gateway,
                journey_role=a.journey_role,
                journey_peer_cam_id=a.journey_peer_cam,
                force_plate=force_plate,
            ).attach()
            print(f"게이트웨이 전송: {gw.url}  (번호판 확정 대기 {a.plate_hold:g}초)")
        else:
            gw.subscribe_to_bus(excluded_types=excluded_types)
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
    # [신규] 신호위반 전용 - "정지선 넘는 순간" 캡처는 이미 찍어서 PATCH까지 보냈고,
    # "그로부터 2초 뒤" 캡처만 기다리는 중인 건들. {track_id, target_ts} 형태.
    pending_signal_after: list[dict] = []
    # [신규] "차 뒷바퀴가 정지선을 넘는 그 순간"의 프레임을 신호위반 확정 전에 미리
    # 캡처해 둔다 - (cam_id, track_id, intersection_id) -> "/captures/....jpg".
    # RedLightDetector.check()는 진출선까지 넘어야 위반이 "확정"되는데, 그 확정
    # 시점의 frame은 이미 교차로를 다 지나간 뒤라 정지선을 넘는 순간이 아니다.
    # engine.red_light._pending에 막 후보로 등록된 바로 그 프레임을 여기서 미리
    # 캡처해 뒀다가, 나중에 확정되면 "전" 캡처로 재사용한다.
    signal_before_captures: dict[tuple, str] = {}
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

                if ev.violation_type == ViolationType.RED_LIGHT:
                    # [수정] "전" 캡처 = 차 뒷바퀴가 정지선을 "넘는 바로 그 순간"의
                    # 프레임(위 signal_before_captures에 미리 캡처해 둔 것을 재사용) -
                    # 여기 확정 시점의 frame은 이미 교차로를 다 지나간 뒤라서 안 쓴다.
                    # "후"는 지금 당장이 아니라 AFTER_CAPTURE_SIGNAL_SECONDS초 뒤(영상
                    # 시각 기준, 교차로를 다 통과한 모습)로 미룬다 - 그래서 여기선
                    # "전"만 즉시 전송하고, "후"는 아래 pending_signal_after 큐에
                    # 넣어 이후 프레임에서 채운다.
                    before_key = (ev.cam_id, ev.track_id, ev.zone_id)
                    frame_ref_before = signal_before_captures.pop(before_key, None)
                    if frame_ref_before is None:
                        # 못 찾았으면(캐시가 이미 정리됐거나 등) 예전처럼 확정 시점
                        # 프레임으로라도 대체한다 - "전" 사진이 아예 안 남는 것보다 낫다.
                        frame_ref_before = save_capture(cv2, frame, a.cam, "signal-before")
                    if gw is not None and frame_ref_before:
                        gw.update_captures(
                            f"trk-{ev.cam_id}-{ev.track_id}", frame_ref_before, None,
                            delay_sec=capture_delay_sec,
                        )
                    pending_signal_after.append({
                        "track_id": ev.track_id,
                        "cam_id": ev.cam_id,
                        "target_ts": ts + AFTER_CAPTURE_SIGNAL_SECONDS,
                    })
                else:
                    # [기존] 유턴 - "전"은 frame_buffer에 남아있는 가장 오래된
                    # (=이 순간 기준 BEFORE_CAPTURE_SECONDS초 전) 프레임, "후"는 위반이
                    # 확정된 바로 이 프레임.
                    before_frame = frame_buffer[0][1] if frame_buffer else None
                    frame_ref_before = save_capture(cv2, before_frame, a.cam, "before")
                    frame_ref_after = save_capture(cv2, frame, a.cam, "after")
                    if gw is not None and (frame_ref_before or frame_ref_after):
                        gw.update_captures(
                            f"trk-{ev.cam_id}-{ev.track_id}", frame_ref_before, frame_ref_after,
                            delay_sec=capture_delay_sec,
                        )
            watching[d.track_id] = (d.bbox, state)

        # [신규] 방금 정지선을 넘어 후보로 등록된 건이 있으면, 지금 이 프레임을
        # "정지선을 넘는 순간"의 캡처로 미리 저장해 둔다. frame_no가 pending에
        # 기록된 값과 같아야 "막 등록된" 것이므로 중복 캡처하지 않는다.
        for key, (_p_ts, p_frame_no, _p_pt) in engine.red_light._pending.items():
            if p_frame_no == frame_no and key not in signal_before_captures:
                cap_path = save_capture(cv2, frame, a.cam, "signal-before")
                if cap_path:
                    signal_before_captures[key] = cap_path
        # 확정됐거나(위에서 이미 소비) 타임아웃/취소돼 _pending에서 사라진 건은
        # 여기 캐시에도 계속 남아있을 이유가 없다 - 메모리 누수 방지.
        for stale_key in [k for k in signal_before_captures if k not in engine.red_light._pending]:
            del signal_before_captures[stale_key]

        # [신규] 신호위반 "2초 뒤" 캡처 - 목표 시각(target_ts)에 도달한 건부터
        # 지금 프레임을 "후" 캡처로 저장해서 PATCH로 채워 넣는다. frame_ref_before를
        # None으로 보내므로(EventService가 null 필드는 덮어쓰지 않음) 이미 저장된
        # "전" 캡처는 그대로 유지된다.
        if pending_signal_after:
            still_pending = []
            for item in pending_signal_after:
                if ts >= item["target_ts"]:
                    frame_ref_after = save_capture(cv2, frame, a.cam, "signal-after")
                    if gw is not None and frame_ref_after:
                        gw.update_captures(
                            f"trk-{item['cam_id']}-{item['track_id']}", None, frame_ref_after,
                            delay_sec=capture_delay_sec,
                        )
                else:
                    still_pending.append(item)
            pending_signal_after = still_pending

        # 보류 중인 위반 이벤트 중 번호판이 확정됐거나 대기 시간을 넘긴 건을 내보낸다.
        if forwarder is not None:
            forwarder.tick(ts)

        if banner and ts > banner[1]:
            banner = None

        if a.show or writer is not None:
            vis = draw_overlay(cv2, frame.copy(), cz, engine, ts, watching, banner, cam_id=a.cam)
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

    # [신규] 영상이 끝날 때까지 target_ts(정지선 통과 +2초)에 못 미친 신호위반
    # 건이 남아있으면 - 있는 그대로 마지막 프레임을 "후" 캡처로 써서 보낸다
    # (forwarder.flush()와 같은 취지: 캡처가 아예 안 붙은 채로 끝나는 일은 없게 한다).
    if pending_signal_after:
        for item in pending_signal_after:
            frame_ref_after = save_capture(cv2, frame, a.cam, "signal-after")
            if gw is not None and frame_ref_after:
                gw.update_captures(
                    f"trk-{item['cam_id']}-{item['track_id']}", None, frame_ref_after,
                    delay_sec=capture_delay_sec,
                )
        pending_signal_after = []

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
        # update_captures()가 delay_sec만큼 지연 후 PATCH를 보내는 백그라운드 스레드를
        # daemon으로 띄우기 때문에, 여기서 join하지 않고 바로 stop()/프로세스 종료로 넘어가면
        # 아직 sleep 중이던 캡처 전송 스레드가 통째로 죽어 "이미지 없음"이 발생한다.
        # 반드시 stop()보다 먼저 호출해서 지연 전송이 끝날 때까지 기다려야 한다.
        gw.join_captures(timeout=capture_delay_sec + 3.0)
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
