#!/usr/bin/env python3
"""ITS 국가교통정보센터 실시간 CCTV 가져오기.

인증키로 CCTV 목록을 받아오고, 스트림(HLS)을 열어 우리 파이프라인에 넣는다.

    python its_cctv.py --list                      # 우리 지역 CCTV 목록 보기
    python its_cctv.py --list --area 서울           # 서울 근처만
    python its_cctv.py --play 0                    # 0번 CCTV 화면 띄우기
    python its_cctv.py --grab 0 -n 30              # 0번에서 30장 캡처 → captures/
    python its_cctv.py --grab 0 -n 30 --lpr        # 캡처하면서 번호판 인식까지

인증키는 아래 순서로 찾는다.
    1) --key 옵션
    2) .env 의 ITS_API_KEY  (권장)
    3) its_key.txt 파일 (기존 방식, 계속 동작)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# OpenCV 는 영상을 열 때만 필요하다. 목록 조회(--list)는 순수 HTTP 요청이므로
# 여기서 미리 불러오지 않는다. 필요한 시점에 _need_cv() 로 가져온다.
cv2 = None


def _need_cv():
    """영상 기능을 쓸 때만 OpenCV 를 불러온다."""
    global cv2
    if cv2 is None:
        try:
            import cv2 as _cv2
        except ImportError:
            print("영상을 보려면 OpenCV 가 필요합니다:  pip install opencv-python")
            print("(목록 조회 --list 는 OpenCV 없이도 됩니다)")
            raise SystemExit(1)
        cv2 = _cv2
    return cv2


API = "https://openapi.its.go.kr:9443/cctvInfo"
LINE = "─" * 72

# 자주 쓰는 지역의 좌표 범위 (minX, maxX, minY, maxY) = (경도, 위도)
AREAS = {
    "서울": (126.80, 127.15, 37.45, 37.65),
    "안양": (126.90, 127.00, 37.36, 37.43),   # 우리 AI Hub 데이터와 같은 지역
    "성남": (127.06, 127.18, 37.35, 37.45),
    "수원": (126.95, 127.08, 37.25, 37.33),
    "인천": (126.60, 126.80, 37.40, 37.55),
    "부산": (128.95, 129.20, 35.10, 35.25),
}


def load_key(explicit: str | None) -> str:
    if explicit:
        return explicit.strip()
    try:                       # .env 를 먼저 올린다
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from app.core.config import load_dotenv
        load_dotenv()
    except Exception:
        pass
    env = os.environ.get("ITS_API_KEY")
    if env:
        return env.strip()
    f = Path(__file__).with_name("its_key.txt")
    if f.exists():
        return f.read_text(encoding="utf-8").strip()
    print("인증키를 찾을 수 없습니다. 아래 중 하나로 지정하세요.")
    print("  1) python its_cctv.py --key 발급받은키 ...")
    print("  2) its_key.txt 파일에 키만 한 줄로 저장")
    print("  3) 환경변수 ITS_API_KEY 설정")
    raise SystemExit(1)


# ==========================================================================
def fetch_list(key: str, bbox, road: str = "its", cctv_type: int = 1) -> list[dict]:
    """CCTV 목록 조회.

    road      : its(국도·지방도) / ex(고속도로)
    cctv_type : 1=실시간 스트리밍(HLS), 2=동영상 파일, 3=정지영상
    """
    minx, maxx, miny, maxy = bbox
    q = urllib.parse.urlencode({
        "apiKey": key, "type": road, "cctvType": cctv_type,
        "minX": minx, "maxX": maxx, "minY": miny, "maxY": maxy,
        "getType": "json",
    })
    url = f"{API}?{q}"
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"조회 실패: {e}")
        print("  · 인증키가 맞는지, 'CCTV 화상자료' 항목이 체크되어 있는지 확인하세요.")
        return []

    res = data.get("response", {})
    items = res.get("data") or []
    if isinstance(items, dict):
        items = [items]
    return items


def show_list(items: list[dict]) -> None:
    if not items:
        print("해당 범위에 CCTV 가 없습니다. 좌표 범위를 넓혀보세요.")
        return
    print(f"\nCCTV {len(items)}대\n")
    print(f"{'번호':>4}  {'이름':<34} {'좌표':<22} 스트림")
    print("-" * 72)
    for i, c in enumerate(items):
        name = str(c.get("cctvname", ""))[:32]
        coord = f"{float(c.get('coordy', 0)):.4f}, {float(c.get('coordx', 0)):.4f}"
        has = "○" if c.get("cctvurl") else "×"
        print(f"{i:>4}  {name:<34} {coord:<22} {has}")
    print(f"\n보려면:  python its_cctv.py --play 0")


# ==========================================================================
def open_stream(url: str):
    """HLS 스트림 열기. 열리기까지 몇 초 걸린다."""
    cv2 = _need_cv()
    print("스트림 접속 중... (10초쯤 걸립니다)")
    cap = cv2.VideoCapture(url)
    if not cap.isOpened():
        print("스트림을 열 수 없습니다.")
        print("  · CCTV 가 점검 중이거나 주소가 만료됐을 수 있습니다 (목록을 다시 받아보세요)")
        print("  · 방화벽이 막고 있을 수도 있습니다")
        return None
    return cap


def play(cap, title: str) -> None:
    cv2 = _need_cv()
    print("q 종료 / s 현재 화면 저장\n")
    out = Path("captures"); out.mkdir(exist_ok=True)
    n = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            print("프레임 수신 중단")
            break
        cv2.imshow("ITS CCTV", frame)
        k = cv2.waitKey(1) & 0xFF
        if k == ord("q"):
            break
        if k == ord("s"):
            p = out / f"its_{int(time.time())}.jpg"
            cv2.imwrite(str(p), frame)
            n += 1
            print(f"  저장: {p}")
    cap.release()
    cv2.destroyAllWindows()
    print(f"\n{n}장 저장했습니다.")


def grab(cap, count: int, interval: float, outdir: Path, run_lpr: bool) -> None:
    """N장 캡처. --lpr 이면 번호판 인식까지 돌린다."""
    cv2 = _need_cv()
    outdir.mkdir(parents=True, exist_ok=True)
    runner = None
    if run_lpr:
        from app.core.config import settings
        from app.lpr.recognizer import get_reader
        print("OCR 모델 로딩 중...")
        reader = get_reader(settings.lpr.ocr_lang, False)
        if reader is None:
            print("EasyOCR 를 쓸 수 없어 캡처만 합니다.")
        else:
            runner = _make_runner()

    saved = 0
    t_last = 0.0
    while saved < count:
        ok, frame = cap.read()
        if not ok:
            print("프레임 수신 중단")
            break
        now = time.time()
        if now - t_last < interval:
            continue
        t_last = now

        p = outdir / f"its_{saved:04d}.jpg"
        cv2.imwrite(str(p), frame)
        saved += 1
        msg = f"  [{saved}/{count}] {p.name}  {frame.shape[1]}x{frame.shape[0]}"

        if runner is not None:
            items, method = runner.process_frame(frame)
            found = [i for i in items if i.ok]
            msg += f"  검출 {len(items)}건({method})"
            if found:
                msg += "  →  " + ", ".join(f"{i.plate_no} {i.conf:.2f}" for i in found)
            annotated = runner.annotate(frame, items, f"ITS CCTV  {saved}/{count}")
            cv2.imwrite(str(outdir / f"its_{saved:04d}_결과.jpg"), annotated)
        print(msg)

    cap.release()
    print(f"\n{saved}장 저장: {outdir.resolve()}")
    if runner is None:
        print("번호판 인식까지 보려면:  python try_lpr.py " + str(outdir))


def _make_runner():
    """try_lpr.py 의 Runner 를 기본 옵션으로 만든다."""
    import argparse as _a

    import try_lpr
    ns = _a.Namespace(
        no_ocr=False, gpu=False, weights=None, no_structured=False,
        max_plates=6, font_size=20, stages=False,
    )
    return try_lpr.Runner(ns)


# ==========================================================================
def main() -> int:
    ap = argparse.ArgumentParser(description="ITS 실시간 CCTV")
    ap.add_argument("--key", help="인증키 (없으면 its_key.txt / 환경변수)")
    ap.add_argument("--list", action="store_true", help="CCTV 목록 보기")
    ap.add_argument("--play", type=int, metavar="N", help="N번 CCTV 화면 띄우기")
    ap.add_argument("--grab", type=int, metavar="N", help="N번 CCTV 에서 캡처")
    ap.add_argument("-n", "--count", type=int, default=20, help="캡처 장수")
    ap.add_argument("--interval", type=float, default=1.0, help="캡처 간격(초)")
    ap.add_argument("--lpr", action="store_true", help="캡처하며 번호판 인식")
    ap.add_argument("--out", default="captures", help="저장 폴더")
    ap.add_argument("--area", default="안양", help=f"지역 {list(AREAS)}")
    ap.add_argument("--road", default="its", choices=["its", "ex"],
                    help="its=국도·지방도 / ex=고속도로")
    ap.add_argument("--bbox", nargs=4, type=float,
                    metavar=("minX", "maxX", "minY", "maxY"), help="좌표 직접 지정")
    args = ap.parse_args()

    key = load_key(args.key)
    bbox = tuple(args.bbox) if args.bbox else AREAS.get(args.area)
    if bbox is None:
        print(f"모르는 지역입니다: {args.area}  (가능: {list(AREAS)})")
        return 1

    print(LINE)
    print(f"ITS 실시간 CCTV — {args.area if not args.bbox else '직접 지정'} / "
          f"{'고속도로' if args.road == 'ex' else '국도·지방도'}")
    print(LINE)

    items = fetch_list(key, bbox, args.road)
    if not items:
        # 조회 결과가 비었는데 조용히 끝나면 왜 안 되는지 알 수 없다.
        print(f"\n'{args.area}' 범위에 CCTV 가 없습니다.\n")
        print("  · --play / --grab 할 때도 --area 를 똑같이 붙여야 합니다")
        print(f"    예)  python its_cctv.py --play 0 --area 서울\n")
        print(f"  · 다른 지역: {' '.join(AREAS)}")
        print("  · 고속도로: --road ex")
        print("  · 범위 직접 지정: --bbox 126.7 127.3 37.3 37.7")
        return 1

    if args.list or (args.play is None and args.grab is None):
        show_list(items)
        return 0

    idx = args.play if args.play is not None else args.grab
    if not (0 <= idx < len(items)):
        print(f"번호가 범위를 벗어났습니다 (0 ~ {len(items)-1})")
        return 1

    cam = items[idx]
    url = cam.get("cctvurl")
    print(f"\n선택: {cam.get('cctvname')}")
    if not url:
        print("이 CCTV 는 스트림 주소가 없습니다. 다른 번호를 고르세요.")
        return 1

    cap = open_stream(url)
    if cap is None:
        return 1

    if args.play is not None:
        play(cap, str(cam.get("cctvname")))
    else:
        grab(cap, args.count, args.interval, Path(args.out), args.lpr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
