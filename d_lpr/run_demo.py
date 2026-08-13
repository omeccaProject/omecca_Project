#!/usr/bin/env python3
"""Mock 시연 스크립트.

영상·모델 가중치 없이 전체 파이프라인을 끝까지 돌려본다.

    python run_demo.py            # 시나리오 1회 실행 후 결과 출력
    python run_demo.py --loop     # 대시보드 확인용으로 계속 이벤트 생성
    python run_demo.py --serve    # 데이터 생성 후 API 서버까지 기동
"""

from __future__ import annotations

import argparse
import logging
import random
import sys
import time

from app.core.bus import TOPIC_VIOLATION, bus
from app.core.config import settings
from app.core.gateway import GatewayClient
from app.simulator import demo_scenarios
from app.vehicle.repository import get_repository
from app.violation.engine import ViolationEngine
from app.violation.signal_state import ManualSignal, SignalPhase

logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(name)-24s %(message)s")
log = logging.getLogger("demo")

BAR = "─" * 78


def build_engine() -> tuple[ViolationEngine, ManualSignal]:
    signal = ManualSignal(default=SignalPhase.GREEN)
    engine = ViolationEngine(signal_provider=signal)
    # Mock 인식기가 DB에 있는 번호판을 뱉도록 시드와 맞춰준다
    engine.lpr.recognizer.set_mock_plates(get_repository().all_plates())
    return engine, signal


def run_once(engine: ViolationEngine, signal: ManualSignal, base_ts: float, verbose: bool = True):
    results = []
    for idx, sc in enumerate(demo_scenarios()):
        t0 = base_ts + idx * 30.0

        # 첫 시나리오만 적색 신호 (신호위반 재현), 나머지는 녹색
        phase = SignalPhase.RED if sc.track_id == 101 else SignalPhase.GREEN
        signal.update("SIG-A", phase, ts=t0 - 5.0)   # grace 통과를 위해 5초 전 전환
        signal.update("SIG-B", phase, ts=t0 - 5.0)

        events = []
        for det in sc.detections(t0, frame0=idx * 1000):
            events.extend(engine.process(det, frame=None, plate_hint=sc.plate_no))

        results.append((sc, phase, events))
        if verbose:
            print(f"\n[{idx + 1}] {sc.name}  (신호: {phase.value}, 기대: {sc.expect})")
            if not events:
                print("    → 이벤트 없음")
            for e in events:
                print(f"    → {e.label} | 번호판 {e.plate_no or '-'} "
                      f"({e.plate_confidence:.2f}) | 위험도 {e.risk_level.value}")
                print(f"       {e.detail}")
    return results


def main() -> int:
    ap = argparse.ArgumentParser(description="LPR / 위반 감지 Mock 시연")
    ap.add_argument("--loop", action="store_true", help="계속 이벤트 생성 (대시보드용)")
    ap.add_argument("--interval", type=float, default=3.0, help="--loop 시 반복 간격(초)")
    ap.add_argument("--serve", action="store_true", help="시연 후 API 서버 기동")
    ap.add_argument("--reset", action="store_true", help="기존 위반 데이터 삭제 후 시작")
    args = ap.parse_args()

    if not settings.lpr.mock:
        log.warning("mock 모드가 꺼져 있습니다. config.yaml 의 lpr.mock 을 확인하세요.")

    repo = get_repository()
    if args.reset:
        repo.clear()
        log.info("기존 위반/인식 로그 삭제 완료")

    engine, signal = build_engine()
    gw = GatewayClient(base_url="http://localhost:8080").start()
    gw.subscribe_to_bus()
    bus.subscribe(lambda topic, payload: None)   # 버스 동작 확인용 no-op 구독자

    print(BAR)
    print("오메카3 스마트 관제 - 번호판 인식 / 차량 위반 감지 시연 (담당: 박지원)")
    print(f"DB: {repo.driver} | Mock 모드: {settings.lpr.mock} | "
          f"카메라: {', '.join(engine.zones.cam_ids())}")
    print(BAR)

    run_once(engine, signal, time.time() - 3600)

    print("\n" + BAR)
    print("집계")
    print(BAR)
    print(f"  처리 탐지 수     : {engine.stats['detections']}")
    print(f"  번호판 확정 건수 : {engine.lpr.stats['confirmed']} "
          f"(시도 {engine.lpr.stats['read']}, 기각 {engine.lpr.stats['rejected']})")
    print(f"  DB 매칭          : 정확 {engine.matcher.stats['matched']} / "
          f"유사 {engine.matcher.stats['fuzzy']} / 미등록 {engine.matcher.stats['unregistered']}")
    print(f"  고위험 경보      : {engine.matcher.stats['alerts']}")
    print(f"  신호 위반        : {engine.stats.get('red_light', 0)}")
    print(f"  불법 유턴        : {engine.stats.get('illegal_uturn', 0)}")
    print(f"  버스 발행 이벤트 : {len(bus.recent(TOPIC_VIOLATION, limit=999))}")
    print(BAR)

    if args.loop:
        print("\n--loop 모드: Ctrl+C 로 종료. 대시보드(http://localhost:8010)에서 확인하세요.")
        try:
            while True:
                time.sleep(args.interval)
                engine.reset()
                engine.lpr.recognizer.set_mock_plates(repo.all_plates())
                run_once(engine, signal, time.time() - random.uniform(0, 86400 * 3), verbose=False)
                log.info("이벤트 배치 생성 완료 (누적 %d건)", sum(repo.count_by_type().values()))
        except KeyboardInterrupt:
            print("\n종료")

    if args.serve:
        import uvicorn
        from app.api.server import app as api

        print(f"\nAPI 서버 기동 → http://localhost:{settings.server.port}")
        uvicorn.run(api, host=settings.server.host, port=int(settings.server.port))
    gw.stop(drain=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
