#!/usr/bin/env python3
"""번호판 인식률 측정 — 실데이터로 정답률을 센다.

왜 필요한가
    `tests/` 의 정확도 수치는 전부 **합성 이미지**(`plate_synth.py`)로 잰 것이다.
    합성에서 잘 나오는 것이 실사진에서도 잘 나온다는 보장은 없다. 전에
    합성 98% → 실데이터 3.3% 로 무너진 전례가 있다. 이 스크립트는 실제로
    찍은 사진으로 "몇 장 중 몇 장 맞췄나"를 센다.

정답은 파일 이름에서 읽는다
    plates/12가3456.jpg        → 정답 "12가3456"
    plates/서울78바9012.png    → 정답 "서울78바9012"
    plates/12가3456_2.jpg      → 정답 "12가3456"  ('_' 뒤는 무시)

    지역명(서울·경기…)은 `plate_format.canonical()` 로 떼고 비교한다.
    '서울12가3456' 과 '12가3456' 은 같은 차량이기 때문이다.

무엇을 재는가
    검출률       사진에서 번호판 '영역'을 찾아냈나
    판독률       그 영역에서 글자를 읽어냈나
    정확도       읽은 번호가 정답과 **완전히** 같은가   ← 발표에 쓸 숫자
    문자 정확도  몇 글자나 맞췄나 (한 글자 차이와 전부 틀림을 구분한다)

    정확도에는 **95% 신뢰구간**을 같이 낸다. 30장 중 24장(80%)은 참값이
    62~91% 어딘가라는 뜻이고, 이걸 빼면 숫자를 과신하게 된다.

    신뢰도 임계값별 표도 낸다. `config.yaml` 의 `min_plate_conf` 를 얼마로
    두어야 오독을 걸러낼 수 있는지 이 표를 보고 정한다.

사용법
    python bench_lpr.py                     # plates/ 폴더 채점
    python bench_lpr.py --dir 다른폴더
    python bench_lpr.py --weights plate.pt  # 번호판 YOLO 가중치가 있으면
    python bench_lpr.py --save-fail         # 틀린 사진을 output/ 에 따로 모은다
"""

from __future__ import annotations

import argparse
import csv
import math
import re
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

try:
    import cv2  # noqa: F401
except ImportError:
    sys.exit("OpenCV 가 필요합니다:  pip install opencv-python")

from app.core.config import settings                      # noqa: E402
from app.lpr import plate_format as pf                    # noqa: E402
from app.lpr import preprocess                            # noqa: E402
from app.lpr.recognizer import PlateRecognizer, get_reader  # noqa: E402
from app.lpr.visualize import imread_unicode, imwrite_unicode  # noqa: E402
from try_lpr import PlateFinder                           # noqa: E402

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}
LINE = "─" * 72

# 읽기 경로 이름. 어느 경로가 정확한지 갈라 보려고 구분한다.
ENGINE_KO = {
    "easyocr:2pass": "자리별 2패스",
    "easyocr:hangul-fix": "한글자리 복구",
    "easyocr": "단일 패스",
}


# ==========================================================================
def truth_from_name(path: Path) -> str:
    """파일 이름에서 정답을 읽는다.

        12가3456.jpg          → 12가3456
        12가3456_2.jpg        → 12가3456      '_' 뒤는 사본 표시
        12가3456 (2).jpg      → 12가3456      윈도우가 붙이는 사본 표시
        12가3456-야간.jpg     → 12가3456      '-' 뒤는 메모

    사본 표시를 안 떼면 `strip_noise()` 가 괄호만 지우고 숫자 '2' 를 번호에
    붙여 버려서('12가34562') 멀쩡한 사진이 전부 오답 처리된다.
    """
    stem = path.stem
    stem = re.sub(r"\s*\(\d+\)\s*$", "", stem)     # " (2)"
    stem = re.split(r"[_\-]", stem)[0]             # "_2", "-야간"
    return stem.strip()


def edit_distance(a: str, b: str) -> int:
    """레벤슈타인 거리. 한 글자 오독과 전부 오독을 구분하려고 쓴다."""
    if a == b:
        return 0
    if not a or not b:
        return len(a) or len(b)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def wilson(hits: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """정확도의 95% 신뢰구간 (Wilson score).

    표본이 작을 때 단순 정규근사(p ± 1.96·√(p(1-p)/n))는 구간이 0 밑이나
    1 위로 새어 나가 말이 안 되는 값을 준다. Wilson 은 그런 일이 없다.
    """
    if n == 0:
        return (0.0, 0.0)
    p = hits / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - m), min(1.0, c + m))


# ==========================================================================
class Bench:
    def __init__(self, weights: str = "", gpu: bool = False,
                 structured=None, max_plates: int = 5) -> None:
        print("OCR 모델 로딩 중... (최초 1회 가중치를 내려받습니다)")
        t0 = time.perf_counter()
        self.reader = get_reader(settings.lpr.ocr_lang, gpu)
        if self.reader is None:
            sys.exit("EasyOCR 를 쓸 수 없습니다. 인식률 측정은 OCR 없이 불가능합니다.\n"
                     "  설치:  pip install easyocr")
        print(f"로딩 완료 ({time.perf_counter() - t0:.1f}초)\n")
        self.finder = PlateFinder(self.reader, weights or None)
        # structured=None 이면 파이프라인이 알아서 정한다.
        # (번호판 전용 모델이 있으면 2패스를 끄는 것이 실측상 낫다)
        self.rec = PlateRecognizer(mock=False, gpu=gpu, structured=structured)
        print(f"자리별 2패스: {'켬' if self.rec.structured else '끔'}")
        self.max_plates = max_plates

    # 크롭 덤프용. 설정되면 read_one 이 전처리 결과를 여기에 쌓는다.
    dump_dir: "Path | None" = None
    dump_name: str = ""
    last_boxes: tuple = ((), "")     # 직전 사진의 검출 상자 (진단용)

    def read_one(self, img) -> tuple[list[tuple[str, float, str]], int]:
        """사진 한 장 → ((번호, 신뢰도, 엔진) 후보 목록, 검출된 영역 수).

        후보는 신뢰도 높은 순이다. 1등을 최종 답으로 채점하고, 정답이 2등
        이하에 있었는지도 따로 센다 (검출 문제인지 순위 문제인지 갈라 보려고).

        `엔진` 은 `easyocr:2pass`(자리별 2패스) 또는 `easyocr`(단일 패스)다.
        한글이 숫자로 읽히는 오류는 2패스가 막게 되어 있으므로, 그 오류가
        나왔다면 **2패스가 걸리지 않고 단일 패스로 새어 나간 것**이다.
        어느 쪽이었는지 남겨야 원인을 짚을 수 있다.
        """
        boxes, method = self.finder.find(img)
        self.last_boxes = (boxes, method)     # 진단용 (--debug-fail)
        out: list[tuple[str, float, str]] = []
        for box in boxes[: self.max_plates]:
            result = preprocess.run(
                img, bbox_xyxy=box.to_xyxy(),
                target_h=settings.lpr.upscale_height,
                deskew_limit=settings.lpr.deskew_limit,
                denoise_min_height=settings.lpr.denoise_min_height,
            )
            if result.image is None:
                continue
            if self.dump_dir is not None and not out:
                # 1등 후보(첫 박스)의 전처리 결과만 저장한다. 실제 판독에 쓰인
                # 바로 그 이미지라야 분할 실험이 의미가 있다.
                imwrite_unicode(str(self.dump_dir / f"{self.dump_name}.png"),
                                result.image)
            r = self.rec.read(result.image, bbox=box)
            if r is not None and r.plate_no:
                out.append((r.plate_no, float(r.confidence),
                            getattr(r, "engine", "") or "?"))
        out.sort(key=lambda kv: -kv[1])
        return out, len(boxes)


# ==========================================================================
def main() -> int:
    ap = argparse.ArgumentParser(description="번호판 인식률 측정 (실데이터)")
    ap.add_argument("--dir", action="append", default=None,
                    help="사진 폴더. 여러 번 주면 합쳐서 채점한다. "
                         "예: --dir plates --dir plates_test")
    ap.add_argument("--out", default=str(BASE / "output"), help="결과 저장 폴더")
    ap.add_argument("--weights", default="", help="번호판 YOLO 가중치 (있으면)")
    ap.add_argument("--gpu", action="store_true")
    ap.add_argument("--structured", dest="structured", action="store_true",
                    default=None, help="자리별 2패스 강제로 켜기")
    ap.add_argument("--no-structured", dest="structured", action="store_false",
                    help="자리별 2패스 강제로 끄기")
    ap.add_argument("--max-plates", type=int, default=5, help="사진 한 장당 볼 후보 수")
    ap.add_argument("--save-fail", action="store_true", help="틀린 사진을 따로 모은다")
    ap.add_argument("--debug-fail", action="store_true",
                    help="틀린 사진의 검출 상자와 후보를 전부 출력한다. "
                         "'잘림'의 원인이 검출 분할인지 인식인지 가른다.")
    ap.add_argument("--dump-crops", default="",
                    help="전처리된 번호판 크롭을 이 폴더에 저장한다 (분할 튜닝용). "
                         "이걸 뽑아 두면 OCR 없이도 분할 실험을 반복할 수 있다.")
    a = ap.parse_args()

    dirs = [Path(d) for d in (a.dir or [str(BASE / "plates")])]
    for d in dirs:
        if not d.is_dir():
            sys.exit(f"폴더가 없습니다: {d}")

    files = []
    for d in dirs:
        got = sorted(p for p in d.iterdir()
                     if p.suffix.lower() in IMAGE_EXT and not p.name.startswith("."))
        print(f"  {d}  {len(got)}장")
        files += got
    src = dirs[0]
    if not files:
        sys.exit("사진이 없습니다.\n"
                 "  파일 이름을 번호판 번호로 저장하세요:  12가3456.jpg")

    # --- 정답 형식 점검. 이름이 번호판이 아니면 채점 자체가 무의미하다 -----
    bad = [p.name for p in files if not pf.is_valid(truth_from_name(p))]
    if bad:
        print("주의 — 파일 이름이 번호판 형식이 아닙니다. 정답으로 쓸 수 없습니다:")
        for n in bad[:10]:
            print(f"    {n}")
        if len(bad) > 10:
            print(f"    ... 외 {len(bad) - 10}개")
        print("  이름을 '12가3456.jpg' 형태로 바꾸고 다시 실행하세요.\n")
        files = [p for p in files if pf.is_valid(truth_from_name(p))]
        if not files:
            return 1

    print(f"사진 {len(files)}장 채점 시작\n{LINE}")
    if len(files) < 30:
        print(f"주의: {len(files)}장은 표본이 적습니다. 신뢰구간이 넓게 나옵니다.")
        print("      최소 30장, 권장 50장.\n")

    bench = Bench(a.weights, a.gpu, a.structured, a.max_plates)
    if a.dump_crops:
        bench.dump_dir = Path(a.dump_crops)
        bench.dump_dir.mkdir(parents=True, exist_ok=True)
        print(f"전처리 크롭을 저장합니다 → {bench.dump_dir}\n")

    rows = []
    t0 = time.perf_counter()
    for i, p in enumerate(files, 1):
        img = imread_unicode(str(p))
        if img is None:
            print(f"  [{i:3d}/{len(files)}] {p.name}  — 파일을 열 수 없음")
            continue
        truth = pf.canonical(truth_from_name(p))
        # 크롭 파일 이름을 정답으로 두면, 나중에 분할 실험할 때
        # '몇 글자여야 하는지'를 파일 이름만으로 알 수 있다.
        bench.dump_name = truth
        cands, n_box = bench.read_one(img)

        pred, conf, engine = (cands[0] if cands else ("", 0.0, ""))
        predc = pf.canonical(pred) if pred else ""
        exact = bool(predc) and predc == truth
        # 정답이 1등은 아니어도 후보 안에는 있었나 (검출·전처리 문제와 순위 문제를 구분)
        in_top = any(pf.canonical(c) == truth for c, _, _ in cands)
        dist = edit_distance(predc, truth)
        char_acc = 1.0 - dist / max(len(truth), 1)

        rows.append({
            "file": (p.name if len(dirs) == 1 else f"{p.parent.name}/{p.name}"), "truth": truth, "pred": predc, "conf": round(conf, 3),
            "engine": engine, "valid": int(pf.is_valid(predc)) if predc else 0,
            "exact": int(exact), "in_top": int(in_top), "boxes": n_box,
            "edit": dist, "char_acc": round(max(0.0, char_acc), 3),
        })

        mark = "○" if exact else ("△" if in_top else "×")
        note = "" if exact else f"  (정답 {truth})"
        tag = p.name if len(dirs) == 1 else f"{p.parent.name}/{p.name}"
        print(f"  [{i:3d}/{len(files)}] {mark} {tag:34s} → "
              f"{predc or '(읽기 실패)':12s} {conf:.2f}{note}")

        if a.debug_fail and not exact:
            bx, method = bench.last_boxes
            ih, iw = img.shape[:2]
            print(f"        검출 방식 {method} / 상자 {len(bx)}개 (사진 {iw}x{ih})")
            for k, b in enumerate(bx[: a.max_plates]):
                x1, y1, x2, y2 = b.to_xyxy()
                print(f"          #{k} x{x1}~{x2} y{y1}~{y2}  "
                      f"{x2-x1}x{y2-y1}  가로/세로 {(x2-x1)/max(1,y2-y1):.2f}")
            print(f"        후보 {len(cands)}개:")
            for t, c, e in cands:
                print(f"          '{t}'  신뢰도 {c:.2f}  ({e})")

    elapsed = time.perf_counter() - t0
    if not rows:
        sys.exit("채점할 수 있는 사진이 없었습니다.")

    # ------------------------------------------------------------ 집계
    n = len(rows)
    detected = sum(1 for r in rows if r["boxes"] > 0)
    readable = sum(1 for r in rows if r["pred"])
    exact = sum(r["exact"] for r in rows)
    in_top = sum(r["in_top"] for r in rows)
    char = sum(r["char_acc"] for r in rows) / n
    lo, hi = wilson(exact, n)

    print(f"\n{LINE}\n결과 — 사진 {n}장, {elapsed:.1f}초 ({elapsed/n:.2f}초/장)\n{LINE}")
    print(f"  검출률 (번호판 영역을 찾음)   {detected:3d}/{n}  {detected/n:6.1%}")
    print(f"  판독률 (글자를 읽어냄)        {readable:3d}/{n}  {readable/n:6.1%}")
    print(f"  ★ 정확도 (완전 일치)          {exact:3d}/{n}  {exact/n:6.1%}"
          f"   95% 신뢰구간 {lo:.1%} ~ {hi:.1%}")
    print(f"  후보 안에는 정답이 있었음      {in_top:3d}/{n}  {in_top/n:6.1%}")
    print(f"  문자 정확도 (글자 단위 평균)              {char:6.1%}")

    # --- 번호판 종류별 -----------------------------------------------------
    #   한글이 용도를 나타낸다. 영업용(아·바·사·자)은 **노란 바탕**이라
    #   흑백으로 바꾸면 흰 판보다 대비가 낮아진다. 종류별로 갈라 봐야
    #   "전체 90%인데 노란 판만 50%" 같은 것이 드러난다.
    CLASS_KO = {"private": "자가용(흰 판)", "commercial": "영업용(노란 판)",
                "rental": "렌터카", "delivery": "택배", "unknown": "기타"}
    by_cls: dict[str, list] = {}
    for r in rows:
        by_cls.setdefault(pf.plate_class(r["truth"]), []).append(r)
    if len(by_cls) > 1:
        print(f"\n  번호판 종류별")
        print(f"    {'종류':<16} {'장수':>5} {'정답':>5} {'정확도':>8}")
        for k in ("private", "commercial", "rental", "delivery", "unknown"):
            g = by_cls.get(k)
            if not g:
                continue
            ok_n = sum(r["exact"] for r in g)
            print(f"    {CLASS_KO[k]:<16} {len(g):5d} {ok_n:5d} {ok_n/len(g):8.1%}")
        if "commercial" not in by_cls:
            print("    주의: 영업용(노란 판)이 한 장도 없다. 그쪽 성능은 모르는 상태다.")

    # --- 읽기 경로별: 2패스가 실제로 걸리고 있나 ---------------------------
    engines = sorted({r["engine"] for r in rows if r["engine"]})
    if engines:
        print(f"\n  읽기 경로별")
        print(f"    {'경로':<16} {'건수':>5} {'정답':>5} {'정확도':>8}")
        for e in engines:
            g = [r for r in rows if r["engine"] == e]
            ok = sum(r["exact"] for r in g)
            name = ENGINE_KO.get(e, e)
            print(f"    {name:<16} {len(g):5d} {ok:5d} {ok/len(g):8.1%}")
        print("    2패스는 한글이 숫자로 읽히는 오류를 구조적으로 막는다.")
        print("    단일 패스 비중이 크면 분할(segment)이 자주 실패했다는 뜻이다.")

        # 2패스가 어느 단계에서 포기했나 — 여기가 개선 지점이다
        bail = getattr(bench.rec, "bail", {}) or {}
        if bail:
            tot = sum(bail.values())
            print(f"\n  2패스 포기 지점 (총 {tot}회)")
            for k, v in sorted(bail.items(), key=lambda kv: -kv[1]):
                print(f"    {v:4d}회  {k}")
            print("    가장 많은 항목을 고치면 2패스 적용 범위가 그만큼 넓어진다.")

    # --- 오류 유형: 어디를 고쳐야 가장 많이 오르나 -------------------------
    from collections import Counter
    fails_all = [r for r in rows if not r["exact"]]
    cnt: "Counter[str]" = Counter()
    if fails_all:
        han = pf.PLATE_HANGUL
        def classify(t: str, p: str) -> str:
            if not p:
                return "판독 실패"
            if len(p) < len(t) - 1:
                return "잘림 (일부만 읽음)"
            nt, np_ = sum(c in han for c in t), sum(c in han for c in p)
            if np_ == 0 and nt == 1:
                return "한글을 숫자로 오독"
            if np_ > nt:
                return "한글 중복"
            if len(p) > len(t):
                return "여분 글자 붙음"
            return "글자 오독"

        cnt = Counter(classify(r["truth"], r["pred"]) for r in fails_all)
        print(f"\n  오류 유형 (총 {len(fails_all)}건)")
        for k, v in cnt.most_common():
            print(f"    {v:3d}건  {k}   (다 고치면 +{v/n:.0%}p)")
        invalid = sum(1 for r in fails_all if not r["valid"])
        print(f"    이 중 {invalid}건은 번호판 '형식' 자체가 틀렸다 "
              f"— 형식 검사로 걸러낼 수 있는 몫이다.")

    # --- 신뢰도 임계값별: 얼마 이상만 믿을지 정하는 근거 -------------------
    print(f"\n  신뢰도 임계값별 (현재 설정 min_plate_conf = {settings.lpr.min_plate_conf:.2f})")
    print(f"    {'임계값':>6}  {'채택':>6}  {'그중 정답':>9}  {'정밀도':>7}")
    thresholds = [0.0, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]
    for t in thresholds:
        taken = [r for r in rows if r["pred"] and r["conf"] >= t]
        if not taken:
            continue
        ok = sum(r["exact"] for r in taken)
        star = " ←현재" if abs(t - settings.lpr.min_plate_conf) < 0.001 else ""
        print(f"    {t:6.2f}  {len(taken):6d}  {ok:9d}  {ok/len(taken):7.1%}{star}")
    print("    임계값을 올리면 정밀도는 오르고 채택 건수는 준다. 둘의 균형점을 고른다.")

    # ------------------------------------------------------------ 저장
    outdir = Path(a.out)
    outdir.mkdir(parents=True, exist_ok=True)
    csv_path = outdir / "lpr_bench.csv"
    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    fails = fails_all
    md = outdir / "lpr_bench.md"
    with md.open("w", encoding="utf-8") as f:
        f.write("# 번호판 인식률 측정 결과 (실데이터)\n\n")
        f.write(f"- 사진 **{n}장**, 소요 {elapsed:.1f}초 ({elapsed/n:.2f}초/장)\n")
        f.write(f"- 폴더: {', '.join(f'`{d.name}/`' for d in dirs)}\n")
        f.write(f"- 설정: 자리별 2패스 {'켬' if bench.rec.structured else '끔'}, "
                f"검출 {'YOLO' if a.weights else 'OCR/CV'}\n\n")
        f.write("| 지표 | 값 |\n|---|---|\n")
        f.write(f"| 검출률 | {detected}/{n} ({detected/n:.1%}) |\n")
        f.write(f"| 판독률 | {readable}/{n} ({readable/n:.1%}) |\n")
        f.write(f"| **정확도 (완전 일치)** | **{exact}/{n} ({exact/n:.1%})** |\n")
        f.write(f"| 정확도 95% 신뢰구간 | {lo:.1%} ~ {hi:.1%} |\n")
        f.write(f"| 후보 내 정답 포함 | {in_top}/{n} ({in_top/n:.1%}) |\n")
        f.write(f"| 문자 정확도 | {char:.1%} |\n\n")
        f.write("## 신뢰도 임계값별\n\n| 임계값 | 채택 | 그중 정답 | 정밀도 |\n|---|---|---|---|\n")
        for t in thresholds:
            taken = [r for r in rows if r["pred"] and r["conf"] >= t]
            if not taken:
                continue
            ok = sum(r["exact"] for r in taken)
            f.write(f"| {t:.2f} | {len(taken)} | {ok} | {ok/len(taken):.1%} |\n")
        if len(by_cls) > 1:
            f.write("\n## 번호판 종류별\n\n| 종류 | 장수 | 정답 | 정확도 |\n|---|---|---|---|\n")
            for k in ("private", "commercial", "rental", "delivery", "unknown"):
                g = by_cls.get(k)
                if not g:
                    continue
                ok_n = sum(r["exact"] for r in g)
                f.write(f"| {CLASS_KO[k]} | {len(g)} | {ok_n} | {ok_n/len(g):.1%} |\n")
        if engines:
            f.write("\n## 읽기 경로별\n\n| 경로 | 건수 | 정답 | 정확도 |\n|---|---|---|---|\n")
            for e in engines:
                g = [r for r in rows if r["engine"] == e]
                ok = sum(r["exact"] for r in g)
                name = ENGINE_KO.get(e, e)
                f.write(f"| {name} | {len(g)} | {ok} | {ok/len(g):.1%} |\n")
            bail = getattr(bench.rec, "bail", {}) or {}
            if bail:
                f.write("\n### 2패스 포기 지점\n\n| 단계 | 횟수 |\n|---|---|\n")
                for k, v in sorted(bail.items(), key=lambda kv: -kv[1]):
                    f.write(f"| {k} | {v} |\n")
        if fails:
            f.write(f"\n## 오류 유형\n\n| 유형 | 건수 |\n|---|---|\n")
            for k, v in cnt.most_common():
                f.write(f"| {k} | {v} |\n")
            f.write(f"\n## 틀린 사진 {len(fails)}장\n\n")
            f.write("| 파일 | 정답 | 인식 | 신뢰도 | 경로 | 형식OK | 글자오차 |\n"
                    "|---|---|---|---|---|---|---|\n")
            for r in fails:
                path = "2패스" if "2pass" in r["engine"] else "단일"
                f.write(f"| {r['file']} | {r['truth']} | {r['pred'] or '(실패)'} "
                        f"| {r['conf']:.2f} | {path} | {'○' if r['valid'] else '×'} "
                        f"| {r['edit']} |\n")
        f.write("\n> 실제 번호판 사진은 개인정보라 저장소에 올리지 않는다. "
                "이 문서의 수치만 공유한다.\n")

    print(f"\n  표    → {md}")
    print(f"  원자료 → {csv_path}")

    if a.save_fail and fails:
        faildir = outdir / "lpr_fail"
        faildir.mkdir(parents=True, exist_ok=True)
        for r in fails:
            img = imread_unicode(str(src.parent / r["file"]) if "/" in r["file"] else str(src / r["file"]))
            if img is not None:
                imwrite_unicode(str(faildir / r["file"]), img)
        print(f"  틀린 사진 → {faildir}  ({len(fails)}장)")

    print(f"\n발표에 쓸 문장:")
    print(f'  "실제 번호판 사진 {n}장으로 측정한 결과 완전 일치율 {exact/n:.1%} '
          f'(95% 신뢰구간 {lo:.0%}~{hi:.0%})"')
    print(LINE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
