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
    --lpr        번호판 인식까지 같이 돌린다 (느려진다)

준비물
    1) config_zones.json 에 이 카메라의 중앙선이 있어야 한다 → draw_roi.py 로 그린다
    2) 신호 판정을 하려면 signal_timeline.json 이 필요하다 (없으면 금지 구간만 판정)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from app.core.schemas import ViolationType                       # noqa: E402
from app.violation.engine import ViolationEngine                 # noqa: E402
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
    ap.add_argument("--lpr", action="store_true", help="번호판 인식도 함께 (느림)")
    a = ap.parse_args()

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

    # --- 엔진 --------------------------------------------------------
    engine = ViolationEngine(zones=zones, signal_provider=signal)

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

    for frame_no, ts, frame, dets in src.frames():
        processed += 1
        if writer is None and a.save:
            Path(a.save).parent.mkdir(parents=True, exist_ok=True)
            writer = cv2.VideoWriter(a.save, cv2.VideoWriter_fourcc(*"mp4v"),
                                     src.fps / a.stride, src.size)

        watching: dict[int, tuple] = {}
        for d in dets:
            evs = engine.process(d, frame=frame if a.lpr else None)
            # 유턴 후보(중앙선 통과) 또는 신호위반 후보(적색 정지선 통과)
            pend = (any(k[1] == d.track_id for k in engine.uturn._pending)
                    or any(k[1] == d.track_id for k in engine.red_light._pending))
            state = "watch" if pend else "car"
            for ev in evs:
                if ev.violation_type not in WATCHED:
                    continue          # 고위험 차량 경보 등은 엔진이 따로 처리
                state = "violation"
                events.append(ev.to_payload())
                label = (SUBTYPE_KO.get(ev.subtype) or VTYPE_EN[ev.violation_type])
                banner = (f"[{label}] track #{ev.track_id}  t={ts:.1f}s", ts + 2.0)
                print(f"\n  ★ {VTYPE_KO[ev.violation_type]}  t={ts:6.2f}s  "
                      f"track=#{ev.track_id}  "
                      f"{ev.subtype or ev.zone_id}  {ev.detail}")
            watching[d.track_id] = (d.bbox, state)

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
