"""실시간 신호 API 점검 도구 (KLID 교통안전 신호등 실시간 정보).

공공데이터포털 15157604 — 행정안전부 한국지역정보개발원

하는 일
    1) 인증키 확인 후 실제로 한 번 호출
    2) 지금 신호가 살아 있는 교차로 목록 표시
    3) 내 촬영 지점 좌표로 가까운 교차로 찾기      (--near 위도,경도)
    4) 교차로 이름으로 찾기                        (--find 강남)
    5) 특정 교차로의 8방향 신호를 실시간 관찰      (--watch 1057)

사용 예
    python signal_probe.py                       # 연결 확인 + 살아있는 교차로
    python signal_probe.py --near 37.5665,126.978
    python signal_probe.py --find 사거리
    python signal_probe.py --watch 1057 --seconds 120

인증키는 `.env` 의 SIGNAL_API_KEY 에서 읽고, 화면에는 마스킹해서만 찍는다.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from app.core.config import mask, secret                          # noqa: E402
from app.violation.signal_klid import (                           # noqa: E402
    DIRECTIONS, KlidSignal, PATH_SIGNAL,
)
from app.violation.signal_state import Movement, SignalPhase      # noqa: E402

MOVE_KO = {
    Movement.STRAIGHT: "직진", Movement.LEFT: "좌회전", Movement.UTURN: "유턴",
    Movement.PED: "보행", Movement.BUS: "버스", Movement.BIKE: "자전거",
}
PHASE_KO = {
    SignalPhase.RED: "적색", SignalPhase.YELLOW: "황색", SignalPhase.GREEN: "녹색",
    SignalPhase.LEFT_ARROW: "좌회전", SignalPhase.GREEN_LEFT: "직진+좌회전",
    SignalPhase.UNKNOWN: "-",
}


def describe(sig: KlidSignal, sid: str, now: float) -> str:
    parts = []
    for m in (Movement.STRAIGHT, Movement.LEFT, Movement.UTURN, Movement.PED):
        ph = sig.movement_at(sid, now, m)
        if ph is SignalPhase.UNKNOWN:
            continue
        r = sig.remain_sec(sid, now, m)
        tail = f"({r:.0f}s)" if r is not None else ""
        parts.append(f"{MOVE_KO[m]} {PHASE_KO[ph]}{tail}")
    return " · ".join(parts) if parts else "(자료 없음)"


def main() -> None:
    ap = argparse.ArgumentParser(description="KLID 실시간 신호 API 점검")
    ap.add_argument("--near", default="", help="'위도,경도' 로 가까운 교차로 찾기")
    ap.add_argument("--find", default="", help="교차로 이름으로 찾기")
    ap.add_argument("--watch", default="", help="관찰할 교차로 ID (예: 1057)")
    ap.add_argument("--seconds", type=float, default=90, help="관찰 시간(초)")
    ap.add_argument("--interval", type=float, default=1.0, help="폴링 간격(초)")
    ap.add_argument("--rows", type=int, default=1000, help="한 번에 받을 교차로 수")
    ap.add_argument("--pages", type=int, default=5, help="교차로 목록 조회 페이지 수")
    ap.add_argument("--raw", action="store_true", help="응답 원문 앞부분 출력")
    a = ap.parse_args()

    key = secret("SIGNAL_API_KEY")
    print("=" * 70)
    print(f"[1] 인증키 : {mask(key)}")
    if not key:
        print("\n인증키가 없습니다.")
        print("  1) copy .env.example .env")
        print("  2) SIGNAL_API_KEY= 뒤에 포털의 'Encoding' 키를 붙여넣기")
        sys.exit(1)

    sig = KlidSignal(num_rows=a.rows)
    print(f"    호출 URL : {sig.build_url().replace(key, '<KEY>')}")

    # --- 연결 확인 ----------------------------------------------------
    print("\n[2] 호출")
    if a.raw:
        try:
            print(sig._http_get(sig.build_url())[:1500])
        except Exception as e:
            sys.exit(f"  실패: {e}")

    t0 = time.time()
    n = sig.poll_once(now=t0)
    if n == 0:
        print(f"  실패: {sig.last_error}")
        print("\n흔한 원인")
        print("  · SERVICE_KEY_IS_NOT_REGISTERED → 승인 직후면 1시간쯤 기다려야 합니다")
        print("  · 'Decoding' 키를 넣음 → %2B, %3D%3D 가 있는 'Encoding' 키를 쓰세요")
        sys.exit(1)

    print(f"  응답 OK — 교차로 {sig.stats['rows']}곳 수신, "
          f"그중 신호가 살아 있는 (교차로×방향) {n}개")

    # --- 좌표로 찾기 --------------------------------------------------
    if a.near:
        try:
            lat, lng = (float(x) for x in a.near.split(","))
        except ValueError:
            sys.exit("  --near 는 '위도,경도' 형식입니다. 예: --near 37.5665,126.978")
        print(f"\n[3] {lat},{lng} 근처 교차로 (목록 {a.pages}페이지 조회 중…)")
        sig.load_map(pages=a.pages)
        live = {s.split(":")[0] for s in sig.live_signal_ids()}
        for d, cid, name in sig.nearest(lat, lng, limit=10):
            flag = "◀ 실시간 신호 있음" if cid in live else ""
            print(f"  {d:8.0f}m  ID={cid:<8} {name:<20} {flag}")
        print("\n  '실시간 신호 있음' 인 교차로만 판정에 쓸 수 있습니다.")

    # --- 이름으로 찾기 ------------------------------------------------
    if a.find:
        print(f"\n[3] 이름에 '{a.find}' 가 든 교차로 (목록 {a.pages}페이지 조회 중…)")
        sig.load_map(pages=a.pages)
        live = {s.split(":")[0] for s in sig.live_signal_ids()}
        hits = [(c, nm) for c, nm in sig.names.items() if a.find in nm]
        for cid, name in sorted(hits, key=lambda t: t[1])[:20]:
            flag = "◀ 실시간 신호 있음" if cid in live else ""
            print(f"  ID={cid:<8} {name:<24} {flag}")
        if not hits:
            print("  없습니다. --pages 를 늘려 보세요 (전국 4,239곳).")

    # --- 살아 있는 교차로 맛보기 ---------------------------------------
    if not a.near and not a.find and not a.watch:
        print("\n[3] 지금 신호가 살아 있는 곳 (앞 15개)")
        for sid in sig.live_signal_ids()[:15]:
            cid, d = sid.split(":")
            print(f"  {sid:<14} {DIRECTIONS[d]:<3} {describe(sig, sid, t0)}")
        print("\n  내 교차로를 찾으려면:")
        print("    python signal_probe.py --near 37.5665,126.978")
        print("    python signal_probe.py --find 사거리")

    # --- 관찰 ---------------------------------------------------------
    if a.watch:
        print("\n" + "=" * 70)
        print(f"[4] 교차로 {a.watch} 관찰 ({a.seconds:.0f}초, Ctrl+C 로 중단)")
        print("    잔여시간이 1초에 1씩 줄어들면 단위(0.1초) 해석이 맞는 것입니다.\n")
        seen: dict[str, str] = {}
        t_end = time.time() + a.seconds
        try:
            while time.time() < t_end:
                now = time.time()
                sig.poll_once(now=now)
                for sid in sig.live_signal_ids():
                    if not sid.startswith(f"{a.watch}:"):
                        continue
                    txt = describe(sig, sid, now)
                    if seen.get(sid) != txt:
                        seen[sid] = txt
                        d = sid.split(":")[1]
                        print(f"  {time.strftime('%H:%M:%S')}  {DIRECTIONS[d]:<3} {txt}")
                time.sleep(a.interval)
        except KeyboardInterrupt:
            pass
        print(f"\n  폴링 {sig.stats['polls']}회 "
              f"(성공 {sig.stats['ok']} / 실패 {sig.stats['failed']}), "
              f"신호 변화 {sig.stats['changes']}회")
        if not seen:
            print(f"  교차로 {a.watch} 는 실시간 신호가 안 옵니다. 다른 ID를 쓰세요.")

    print("\n다음 단계")
    print("  1) 내 교차로 ID와 진입 방향을 정한다 (예: 1057 + 서쪽 → \"1057:wt\")")
    print("  2) config_zones.json 의 해당 라인 signal_id 를 그 값으로 바꾼다")
    print("  3) python run_uturn.py --cam CAM-TEST --signal-api ...")


if __name__ == "__main__":
    main()
