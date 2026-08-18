#!/usr/bin/env python3
"""AI Hub 「자동차 차종/연식/번호판 인식용 영상」 → 학습용 데이터 준비.

받은 zip 4개를 **풀지 않고 그대로 읽어서** 학습 세트를 만든다.
(8만 + 1만 장을 파일로 풀면 탐색기가 버벅이고 디스크만 먹는다)

    Training/[라벨]자동차번호판OCR_train.zip     JSON — {"value": "01가0785"}
    Training/[원천]자동차번호판OCR데이터.zip     JPG  — 번호판 크롭
    Validation/[라벨]자동차번호판OCR_valid.zip
    Validation/[원천]자동차번호판OCR데이터.zip

하는 일

  1) 라벨 정리
     JSON 의 `value` 를 정답으로 쓴다. 파일명은 CP949 라 깨져 보이므로 쓰지 않는다.
     번호판 형식에 안 맞는 것(0.9%)은 버린다 — '16육2331', '영경기14노8695' 등.

  2) 글자 균형 맞추기  ★ 이게 핵심이다
     원본 분포가 심하게 치우쳐 있다.

         바 16,126장   ←  전체의 20%
         아  4,994장
         허     62장   (valid 기준)

     그대로 학습하면 모델이 **애매할 때 '바'로 찍는 버릇**이 든다. 실제로
     '바'가 아닌 번호판이 훨씬 많으니 이건 그냥 오답이 된다.
     그래서 글자마다 상한(--cap)을 두고 고르게 뽑는다.

  3) 운영과 같은 전처리
     추론할 때 OCR 이 보는 것은 원본이 아니라 `preprocess.run()` 을 거친
     이미지다(기울기 보정·대비 강화·96px 확대·여백 정리). 학습도 같은 것을
     보여줘야 한다. 원본으로 학습하면 **맑은 날 연습하고 빗속에서 시험 보는**
     꼴이 된다.

내보내는 형식 (deep-text-recognition-benchmark / EasyOCR 학습기 규격)

    out/train/000001_01가0785.png ...
    out/train/gt.txt      "파일명<탭>정답"
    out/val/...

사용법
    python prep_aihub.py --src "..\\자동차 차종-연식-번호판 인식용 영상"
    python prep_aihub.py --src ... --limit 20000 --out output\\aihub_train
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

try:
    import cv2
    import numpy as np
except ImportError:
    sys.exit("OpenCV 가 필요합니다:  pip install opencv-python")

from app.core.config import settings          # noqa: E402
from app.lpr import plate_format as pf        # noqa: E402
from app.lpr import preprocess                # noqa: E402
from app.lpr.visualize import imwrite_unicode  # noqa: E402

LINE = "─" * 72

ZIPS = {
    "train": ("Training/[라벨]자동차번호판OCR_train.zip",
              "Training/[원천]자동차번호판OCR데이터.zip"),
    "val":   ("Validation/[라벨]자동차번호판OCR_valid.zip",
              "Validation/[원천]자동차번호판OCR데이터.zip"),
}


def load_labels(zpath: Path) -> dict[str, str]:
    """라벨 zip → {파일stem: 정답}.  형식에 안 맞는 것은 버린다."""
    out: dict[str, str] = {}
    dropped = 0
    with zipfile.ZipFile(zpath) as z:
        for name in z.namelist():
            if not name.lower().endswith(".json"):
                continue
            try:
                val = json.loads(z.read(name)).get("value", "")
            except Exception:
                dropped += 1
                continue
            val = pf.strip_noise(str(val))
            if not pf.is_valid(val):
                dropped += 1
                continue
            out[name.rsplit(".", 1)[0]] = val
    return out, dropped


def hangul_of(plate: str) -> str:
    for ch in pf.canonical(plate):
        if ch in pf.PLATE_HANGUL:
            return ch
    return ""


def balanced_pick(labels: dict[str, str], cap: int, limit: int,
                  seed: int, per_plate: int = 5) -> list[tuple[str, str]]:
    """글자마다 최대 cap 장씩. 같은 번호판이 몰리지 않게 섞어서 고른다."""
    by_char: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for stem, val in labels.items():
        by_char[hangul_of(val)].append((stem, val))

    rng = random.Random(seed)
    picked: list[tuple[str, str]] = []
    for ch, items in by_char.items():
        # 같은 번호판의 여러 장이 한꺼번에 뽑히지 않도록 번호판 단위로 섞는다
        rng.shuffle(items)
        seen: Counter = Counter()
        take: list[tuple[str, str]] = []
        for stem, val in items:
            key = pf.canonical(val)
            if seen[key] >= per_plate:    # 한 차량당 장수 제한
                continue
            seen[key] += 1
            take.append((stem, val))
            if len(take) >= cap:
                break
        picked += take

    rng.shuffle(picked)
    return picked[:limit] if limit else picked


def report(tag: str, labels: dict[str, str], dropped: int) -> None:
    han = Counter(hangul_of(v) for v in labels.values())
    print(f"\n[{tag}] 유효 라벨 {len(labels)}장 (버림 {dropped}장)")
    print(f"       고유 번호판 {len(set(pf.canonical(v) for v in labels.values()))}대")
    print(f"       한글 {len(han)}종  최다 {han.most_common(1)[0]}  "
          f"최소 {han.most_common()[-1]}")


def main() -> int:
    ap = argparse.ArgumentParser(description="AI Hub 번호판 OCR 학습 데이터 준비")
    ap.add_argument("--src", required=True, help="zip 4개가 있는 폴더")
    ap.add_argument("--out", default=str(BASE / "output" / "aihub_train"))
    ap.add_argument("--limit", type=int, default=60000,
                    help="train 최대 장수. 2만으로 학습했을 때 val 84.6% 에서 "
                         "멈췄다. AI Hub 공식 벤치마크는 같은 데이터로 99.75% 다.")
    ap.add_argument("--cap", type=int, default=2500,
                    help="한글 글자당 최대 장수. 600 으로 조였더니 8만 장 중 "
                         "2만 장만 남았다('바' 16,126장 → 530장). 균형은 잡히지만 "
                         "데이터를 4분의 3 버리는 셈이라 득보다 실이 컸다.")
    ap.add_argument("--per-plate", type=int, default=5,
                    help="같은 번호판 최대 장수")
    ap.add_argument("--val-limit", type=int, default=5000)
    ap.add_argument("--val-cap", type=int, default=150)
    ap.add_argument("--jpeg", type=int, default=95,
                    help="저장 품질(1~100). PNG 로 6만 장을 저장하면 2GB 가 넘어 "
                         "Colab 업로드가 고통스럽다. 96px 높이에서 품질 95 면 "
                         "육안·학습 모두 차이가 없다. 0 이면 PNG.")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--raw", action="store_true",
                    help="전처리 없이 원본 그대로 (권장하지 않음)")
    a = ap.parse_args()

    src = Path(a.src)
    for split, (lz, iz) in ZIPS.items():
        for z in (lz, iz):
            if not (src / z).exists():
                sys.exit(f"파일이 없습니다: {src / z}")

    out = Path(a.out)
    print(f"{LINE}\nAI Hub 번호판 OCR → 학습 데이터\n{LINE}")
    print(f"원본: {src}")
    print(f"출력: {out}")
    print(f"전처리: {'없음 (원본)' if a.raw else '운영과 동일 (기울기·대비·확대)'}")

    total = {"train": 0, "val": 0}
    for split, (lz, iz) in ZIPS.items():
        labels, dropped = load_labels(src / lz)
        report(split, labels, dropped)

        cap = a.cap if split == "train" else a.val_cap
        limit = a.limit if split == "train" else a.val_limit
        picked = balanced_pick(labels, cap, limit, a.seed, a.per_plate)

        han = Counter(hangul_of(v) for _, v in picked)
        print(f"       → 균형 조정 후 {len(picked)}장  "
              f"(글자당 최다 {han.most_common(1)[0][1]}장 / 최소 "
              f"{han.most_common()[-1][1]}장)")

        dst = out / split
        dst.mkdir(parents=True, exist_ok=True)
        for pat in ("*.png", "*.jpg"):
            for old in dst.glob(pat):
                old.unlink()

        lines: list[str] = []
        fail = 0
        with zipfile.ZipFile(src / iz) as z:
            members = {n.rsplit(".", 1)[0]: n for n in z.namelist()
                       if n.lower().endswith((".jpg", ".jpeg", ".png"))}
            for i, (stem, val) in enumerate(picked):
                name = members.get(stem)
                if name is None:
                    fail += 1
                    continue
                buf = np.frombuffer(z.read(name), np.uint8)
                im = cv2.imdecode(buf, cv2.IMREAD_COLOR)
                if im is None:
                    fail += 1
                    continue
                if not a.raw:
                    h, w = im.shape[:2]
                    r = preprocess.run(
                        im, bbox_xyxy=(0, 0, w, h),
                        target_h=settings.lpr.upscale_height,
                        deskew_limit=settings.lpr.deskew_limit,
                        denoise_min_height=settings.lpr.denoise_min_height,
                    )
                    if r.image is None:
                        fail += 1
                        continue
                    im = r.image
                ext = ".png" if a.jpeg <= 0 else ".jpg"
                fname = f"{i:06d}{ext}"
                # **cv2.imwrite 를 쓰면 안 된다.** 경로에 한글이 있으면
                # (C:\Users\박지원\...) 아무것도 쓰지 않고 False 만 돌려준다.
                # 예외도 안 나므로 "다 저장했다"고 착각하게 된다.
                if not imwrite_unicode(str(dst / fname), im, a.jpeg):
                    fail += 1
                    continue
                lines.append(f"{fname}\t{val}")
                if (i + 1) % 2000 == 0:
                    print(f"       {i + 1}/{len(picked)} 처리 중...")

        (dst / "gt.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        total[split] = len(lines)
        # 정말로 파일이 만들어졌는지 센다. gt.txt 줄 수만 믿으면 안 된다.
        on_disk = len(list(dst.glob("*.png"))) + len(list(dst.glob("*.jpg")))
        print(f"       저장 {len(lines)}장 (실패 {fail}장) → {dst}")
        print(f"       실제 파일 확인: {on_disk}개 "
              f"{'OK' if on_disk == len(lines) else '← 불일치! 저장에 실패했다'}")
        if on_disk != len(lines):
            sys.exit("이미지가 제대로 저장되지 않았습니다. 경로에 쓰기 권한이 있는지 확인하세요.")

    print(f"\n{LINE}\n완료\n{LINE}")
    print(f"  train {total['train']}장 / val {total['val']}장")
    print(f"  위치: {out}")
    print(f"\n  이 폴더를 zip 으로 묶어 Colab 에 올린다:")
    print(f"    cd {out}")
    print(f"    Compress-Archive -Path train,val -DestinationPath ..\\aihub_train.zip -Force")
    print("  만들어진 zip 을 drive.google.com 내 드라이브 최상위에 올린다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
