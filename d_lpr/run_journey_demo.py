"""한강중학교(L010321) -> 녹사평역(L010062) 번호판 매칭 GIS Journey 데모를
명령어 하나로 순서대로 실행하는 래퍼.

내부적으로 하는 일은 지금까지 터미널 두 개에 따로 치던 것과 완전히 같다.

    1) run_uturn.py --cam L010321 --journey-role start   (신호위반1 - 실제 위반 확정)
    2) run_uturn.py --cam L010062 --journey-role follow   (신호위반2 - 번호판 이어받아 Journey 연장)

1번이 끝까지 돌아서 번호판이 게이트웨이(/api/events)에 저장된 뒤에만 2번을 시작해야
하므로, subprocess.run()으로 "1번이 끝날 때까지 기다렸다가" 2번을 실행한다(병렬 아님).

사용법:
    python run_journey_demo.py
    python run_journey_demo.py --video1 videos/다른영상1.mp4 --video2 videos/다른영상2.mp4
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent


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
    ap = argparse.ArgumentParser(description="한강중학교->녹사평역 Journey 데모 한 번에 실행")
    ap.add_argument("--video1", default="videos/신호위반1_sample.mp4",
                    help="카메라1(한강중학교/L010321, journey-role start) 영상")
    ap.add_argument("--video2", default="videos/신호위반2_sample.mp4",
                    help="카메라2(녹사평역/L010062, journey-role follow) 영상")
    ap.add_argument("--cam1", default="L010321")
    ap.add_argument("--cam2", default="L010062")
    ap.add_argument("--gateway", default="http://localhost:8080")
    ap.add_argument("--signal", default="signal_timeline.json")
    ap.add_argument("--demo-moving-roi", default="demo_moving_roi_L010321.json")
    ap.add_argument("--no-lpr", action="store_true",
                    help="카메라1에서 --lpr을 빼고 돌린다(테스트용, 보통 안 씀)")
    ap.add_argument("--pause-sec", type=float, default=2.0,
                    help="1단계 종료 후 2단계 시작 전 대기 시간(초) - 게이트웨이가 "
                         "이벤트를 완전히 저장할 여유를 준다")
    a = ap.parse_args()

    cmd1 = [
        sys.executable, "run_uturn.py",
        "--video", a.video1,
        "--cam", a.cam1,
        "--signal", a.signal,
        "--demo-moving-roi", a.demo_moving_roi,
        "--gateway", a.gateway,
        "--mode", "signal",
        "--journey-role", "start",
    ]
    if not a.no_lpr:
        cmd1.append("--lpr")

    cmd2 = [
        sys.executable, "run_uturn.py",
        "--video", a.video2,
        "--cam", a.cam2,
        "--gateway", a.gateway,
        "--journey-role", "follow",
        "--journey-peer-cam", a.cam1,
    ]

    run_step(f"1/2  {a.cam1} - 실제 위반 확정 + Journey 시작", cmd1)

    if a.pause_sec > 0:
        print(f"\n[JOURNEY DEMO] {a.pause_sec:g}초 대기 (게이트웨이 저장 여유)...")
        time.sleep(a.pause_sec)

    run_step(f"2/2  {a.cam2} - 번호판 이어받아 Journey 연장", cmd2)

    print(f"\n{'=' * 70}")
    print("[JOURNEY DEMO] 완료 - 대시보드 '추적 차량' 탭에서 확인하세요.")
    print("=" * 70)


if __name__ == "__main__":
    main()