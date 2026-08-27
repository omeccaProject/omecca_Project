"""GIS Journey 데모(카메라1 -> 카메라2, 번호판 매칭 이동 경로)를 명령어 하나로
순서대로 실행하는 래퍼. 신호위반 / 불법유턴 둘 다 이 스크립트 하나로 커버한다.

내부적으로 하는 일은 터미널 두 개에 따로 치던 것과 완전히 같다.

    1) run_uturn.py --cam <cam1> --journey-role start   (실제 위반 확정 + Journey 시작)
    2) run_uturn.py --cam <cam2> --journey-role follow   (번호판 이어받아 Journey 연장)

1번이 끝까지 돌아서 번호판이 게이트웨이(/api/events)에 저장된 뒤에만 2번을 시작해야
하므로, subprocess.run()으로 "1번이 끝날 때까지 기다렸다가" 2번을 실행한다(병렬 아님).

사용법 - 신호위반 (한강중학교 -> 녹사평역):
    python run_journey_demo.py --scenario signal ^
        --video1 videos/신호위반1_sample.mp4 --video2 videos/신호위반2_sample.mp4 ^
        --cam1 L010321 --cam2 L010062 ^
        --signal signal_timeline.json --demo-moving-roi demo_moving_roi_L010321.json

사용법 - 불법유턴 (한남고가 -> 북한남):
    python run_journey_demo.py --scenario uturn ^
        --video1 videos/uturn_sample.mp4 --video2 videos/uturn_2.mp4 ^
        --cam1 L010322 --cam2 L010116

--scenario는 --mode와 --journey-peer-event-type 기본값만 정해주는 단축 옵션이다.
--mode/--journey-peer-event-type을 직접 주면 그 값이 우선한다.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent

# --scenario 단축 옵션의 기본값. 새 시나리오가 늘어나면 여기에 한 줄만 추가하면 된다.
SCENARIO_DEFAULTS = {
    "signal": {"mode": "signal", "event_type": "SIGNAL_VIOLATION"},
    "uturn": {"mode": "uturn", "event_type": "UTURN_VIOLATION"},
}


def run_step(label: str, cmd: list[str]) -> None:
    print(f"\n{'=' * 70}")
    print(f"[JOURNEY DEMO] {label}")
    print(f"[JOURNEY DEMO] {' '.join(cmd)}")
    print("=" * 70)
    result = subprocess.run(cmd, cwd=str(BASE))
    if result.returncode != 0:
        sys.exit(f"[JOURNEY DEMO] '{label}' 단계가 종료코드 {result.returncode}로 실패했습니다 - "
                 f"중단합니다.")


def main() -> None:
    ap = argparse.ArgumentParser(description="카메라1->카메라2 Journey 데모 한 번에 실행")
    ap.add_argument("--scenario", choices=list(SCENARIO_DEFAULTS), default="signal",
                    help="--mode / --journey-peer-event-type 기본값을 한 번에 정하는 단축 옵션. "
                         "signal: 신호위반(SIGNAL_VIOLATION), uturn: 불법유턴(UTURN_VIOLATION).")
    ap.add_argument("--video1", default="videos/신호위반1_sample.mp4",
                    help="카메라1(journey-role start, 실제 위반 확정) 영상")
    ap.add_argument("--video2", default="videos/신호위반2_sample.mp4",
                    help="카메라2(journey-role follow, 번호판 이어받음) 영상")
    ap.add_argument("--cam1", default="L010321")
    ap.add_argument("--cam2", default="L010062")
    ap.add_argument("--gateway", default="http://localhost:8080")
    ap.add_argument("--mode", default="", choices=["", "all", "uturn", "signal"],
                    help="카메라1 감지 모드. 비워두면 --scenario 기본값을 쓴다.")
    ap.add_argument("--journey-peer-event-type", default="",
                    choices=["", "SIGNAL_VIOLATION", "UTURN_VIOLATION"],
                    help="카메라2가 카메라1의 번호판을 조회할 때 찾을 이벤트 타입. "
                         "비워두면 --scenario 기본값을 쓴다.")
    ap.add_argument("--signal", default="",
                    help="카메라1에 --signal로 넘길 신호 타임라인 JSON (신호위반 시나리오용, "
                         "불법유턴처럼 필요 없으면 비워둔다)")
    ap.add_argument("--demo-moving-roi", default="",
                    help="카메라1에 --demo-moving-roi로 넘길 파일 (게임 데모처럼 ROI가 "
                         "움직여야 할 때만 지정, 고정 카메라 영상이면 비워둔다)")
    ap.add_argument("--no-lpr", action="store_true",
                    help="카메라1에서 --lpr을 빼고 돌린다(테스트용, 보통 안 씀)")
    ap.add_argument("--pause-sec", type=float, default=2.0,
                    help="1단계 종료 후 2단계 시작 전 대기 시간(초) - 게이트웨이가 "
                         "이벤트를 완전히 저장할 여유를 준다")
    a = ap.parse_args()

    defaults = SCENARIO_DEFAULTS[a.scenario]
    mode = a.mode or defaults["mode"]
    event_type = a.journey_peer_event_type or defaults["event_type"]

    cmd1 = [
        sys.executable, "run_uturn.py",
        "--video", a.video1,
        "--cam", a.cam1,
        "--gateway", a.gateway,
        "--mode", mode,
        "--journey-role", "start",
    ]
    if a.signal:
        cmd1 += ["--signal", a.signal]
    if a.demo_moving_roi:
        cmd1 += ["--demo-moving-roi", a.demo_moving_roi]
    if not a.no_lpr:
        cmd1.append("--lpr")

    cmd2 = [
        sys.executable, "run_uturn.py",
        "--video", a.video2,
        "--cam", a.cam2,
        "--gateway", a.gateway,
        "--journey-role", "follow",
        "--journey-peer-cam", a.cam1,
        "--journey-peer-event-type", event_type,
    ]

    run_step(f"1/2  {a.cam1} - 실제 위반 확정 + Journey 시작 (mode={mode})", cmd1)

    if a.pause_sec > 0:
        print(f"\n[JOURNEY DEMO] {a.pause_sec:g}초 대기 (게이트웨이 저장 여유)...")
        time.sleep(a.pause_sec)

    run_step(f"2/2  {a.cam2} - 번호판 이어받아 Journey 연장 (event_type={event_type})", cmd2)

    print(f"\n{'=' * 70}")
    print("[JOURNEY DEMO] 완료 - 대시보드 '추적 차량' 탭에서 확인하세요.")
    print("=" * 70)


if __name__ == "__main__":
    main()