#!/usr/bin/env python3
"""번호판 학습 데이터 점검 · 준비.

**학습을 돌리기 전에 이걸 먼저 본다.** Colab에서 몇 시간 태우고 나서
"데이터가 잘못됐네" 를 알게 되면 그 시간이 통째로 날아간다.

무엇을 보는가
    1) 라벨   — 파일명이 번호판 형식인가. 아니면 학습에 못 쓴다.
    2) 형태   — 번호판만 잘린 사진인가, 차 전체 사진인가.
                인식 모델 학습에는 **번호판만 잘린 것**이 필요하다.
    3) 글자 분포 — 어떤 한글이 몇 번 나오는가.
                '너' 가 3장뿐이면 모델은 '너' 를 못 배운다. 이게 학습 전에
                반드시 봐야 할 값이다.
    4) 중복   — 같은 번호가 여러 장이면 train/val 을 나눌 때 갈라 놔야 한다.
                같은 차가 양쪽에 들어가면 검증 점수가 부풀려진다.

무엇을 만드는가
    --build 를 주면 EasyOCR 학습기(deep-text-recognition-benchmark 계열)가
    먹는 형식으로 내보낸다.

        out/train/  이미지들 + gt.txt   ("파일명<탭>정답")
        out/val/    이미지들 + gt.txt

사용법
    python prep_train_data.py --dir "..\\번호판1000"              # 점검만
    python prep_train_data.py --dir ... --crop                    # 번호판만 잘라내기
    python prep_train_data.py --dir ... --build out\\train_data    # 학습용 내보내기
"""

from __future__ import annotations

import argparse
import random
import re
import shutil
import sys
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

try:
    import cv2  # noqa: F401
except ImportError:
    sys.exit("OpenCV 가 필요합니다:  pip install opencv-python")

from app.lpr import plate_format as pf                          # noqa: E402
from app.lpr.visualize import imread_unicode, imwrite_unicode   # noqa: E402

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
LINE = "─" * 72

# 번호판 실물 가로/세로 비. 이보다 훨씬 작으면 차 전체 사진일 가능성이 크다.
PLATE_AR = 520 / 110        # ≈ 4.7
CROP_AR_MIN = 2.0           # 잘린 번호판이라면 최소 이 정도는 된다


def label_from_name(path: Path) -> str:
    """파일명 → 정답.

    Roboflow 로 내보내면 파일명 뒤에 해시가 붙는다.

        서울83사6490.jpg                   → 서울83사6490
        서울83사6490_jpg.rf.a1b2.jpg       → 서울83사6490   (Roboflow 내보내기)
        경기37바5689-5.jpg                 → 경기37바5689   ('-5' 는 같은 차 사본)
        100라7873 (2)_jpg.rf.a1b2.jpg      → 100라7873      (사본 + Roboflow)

    **순서가 중요하다.** Roboflow 접미사를 먼저 떼야 한다. 사본 표시 ' (2)' 가
    파일명 끝이 아니라 해시 앞에 끼여 있어서, 끝에서만 찾으면 못 떼고
    '100라7873 (2)' 가 정답으로 잡혀 멀쩡한 사진이 통째로 버려진다.
    """
    stem = path.stem
    stem = re.sub(r"_(jpe?g|png|bmp|webp)\.rf\.[0-9a-fA-F]+$", "", stem)  # Roboflow
    stem = re.sub(r"\s*\(\d+\)\s*$", "", stem)                            # 사본 표시
    return re.split(r"[_\-]", stem)[0].strip()


def find_roboflow_split(root: Path) -> list[tuple[str, Path, Path]]:
    """Roboflow YOLO 내보내기 구조를 찾는다.

        root/train/images/*.jpg   root/train/labels/*.txt
        root/valid/images/...     root/test/images/...

    반환: [(구분, 이미지폴더, 라벨폴더), ...]  없으면 빈 목록.

    라벨 txt 는 YOLO 형식이다 — `클래스 중심x 중심y 폭 높이` (0~1 정규화).
    이 박스를 쓰면 우리 검출기를 돌리는 것보다 정확하게 번호판만 잘라낼 수 있다.
    사람이 직접 그은 좌표이기 때문이다.
    """
    out = []
    for name in ("train", "valid", "val", "test"):
        img_dir = root / name / "images"
        lab_dir = root / name / "labels"
        if img_dir.is_dir():
            out.append((name, img_dir, lab_dir if lab_dir.is_dir() else None))
    return out


def yolo_box(label_file: Path, w: int, h: int) -> tuple[int, int, int, int] | None:
    """YOLO 라벨 한 줄 → 픽셀 좌표 (x1,y1,x2,y2). 가장 큰 박스를 고른다."""
    try:
        lines = [ln.split() for ln in label_file.read_text().strip().splitlines() if ln.strip()]
    except OSError:
        return None
    best = None
    for parts in lines:
        if len(parts) < 5:
            continue
        try:
            cx, cy, bw, bh = (float(v) for v in parts[1:5])
        except ValueError:
            continue
        x1 = int((cx - bw / 2) * w); x2 = int((cx + bw / 2) * w)
        y1 = int((cy - bh / 2) * h); y2 = int((cy + bh / 2) * h)
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        if x2 - x1 < 8 or y2 - y1 < 4:
            continue
        area = (x2 - x1) * (y2 - y1)
        if best is None or area > best[0]:
            best = (area, (x1, y1, x2, y2))
    return best[1] if best else None


def main() -> int:
    ap = argparse.ArgumentParser(description="번호판 학습 데이터 점검·준비")
    ap.add_argument("--dir", required=True, help="번호판 사진 폴더")
    ap.add_argument("--build", default="", help="학습용으로 내보낼 폴더")
    ap.add_argument("--crop", action="store_true",
                    help="차 전체 사진에서 번호판만 잘라낸다 (검출기 사용)")
    ap.add_argument("--val-ratio", type=float, default=0.1, help="검증 비율")
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()

    src = Path(a.dir)
    if not src.is_dir():
        sys.exit(f"폴더가 없습니다: {src}")

    # Roboflow 내보내기면 사람이 그어 둔 번호판 박스를 그대로 쓴다.
    rf = find_roboflow_split(src)
    boxfile: dict[Path, Path] = {}
    if rf:
        print(f"{LINE}\nRoboflow 내보내기 구조를 찾았습니다\n{LINE}")
        files = []
        for name, img_dir, lab_dir in rf:
            imgs = sorted(p for p in img_dir.iterdir()
                          if p.suffix.lower() in IMAGE_EXT)
            files += imgs
            n_lab = 0
            if lab_dir:
                for p in imgs:
                    lf = lab_dir / (p.stem + ".txt")
                    if lf.exists():
                        boxfile[p] = lf
                        n_lab += 1
            print(f"  {name:6} 이미지 {len(imgs):4d}장  라벨 {n_lab}개")
        print("\n  ※ 번호판 박스가 있으므로 검출기를 돌릴 필요가 없다.")
        print("    사람이 직접 그은 좌표라 우리 검출기보다 정확하다.")
    else:
        files = sorted(p for p in src.rglob("*")
                       if p.suffix.lower() in IMAGE_EXT and not p.name.startswith("."))
    if not files:
        sys.exit(f"{src} 에 이미지가 없습니다.")

    print(f"\n{LINE}\n이미지 {len(files)}장 — {src}\n{LINE}")

    # ---------------------------------------------------------------- 1) 라벨
    good, bad = [], []
    for p in files:
        lab = label_from_name(p)
        (good if pf.is_valid(lab) else bad).append((p, lab))

    print(f"\n[1] 라벨 (파일명)")
    print(f"    번호판 형식 O : {len(good)}장  ({len(good)/len(files):.1%})")
    print(f"    번호판 형식 X : {len(bad)}장")
    if bad:
        print("    형식이 아닌 예:")
        for p, lab in bad[:8]:
            print(f"      {p.name}   → '{lab}'")
        if len(bad) > 8:
            print(f"      ... 외 {len(bad) - 8}개")
        print("    ※ 이 파일들은 학습에 쓸 수 없다. 이름을 고치거나 빼야 한다.")
    if not good:
        sys.exit("\n쓸 수 있는 라벨이 하나도 없습니다.")

    # ---------------------------------------------------------------- 2) 형태
    print(f"\n[2] 사진 형태")
    ars, sizes, unreadable = [], [], 0
    for p, _ in good[:400]:                       # 표본만 봐도 충분하다
        im = imread_unicode(str(p))
        if im is None:
            unreadable += 1
            continue
        h, w = im.shape[:2]
        sizes.append((w, h))
        ars.append(w / max(1, h))
    if not ars:
        sys.exit("이미지를 하나도 열지 못했습니다.")
    ars.sort()
    med_ar = ars[len(ars) // 2]
    cropped = sum(1 for r in ars if r >= CROP_AR_MIN)
    print(f"    가로/세로 비 중앙값 {med_ar:.2f}   (번호판 실물은 약 {PLATE_AR:.1f})")
    print(f"    번호판만 잘린 것으로 보이는 비율 {cropped}/{len(ars)} = {cropped/len(ars):.0%}")
    if unreadable:
        print(f"    열 수 없는 파일 {unreadable}장")
    ws = sorted(w for w, _ in sizes); hs = sorted(h for _, h in sizes)
    print(f"    크기 중앙값 {ws[len(ws)//2]} x {hs[len(hs)//2]}")
    if cropped / len(ars) < 0.5:
        print("    ※ 차 전체 사진으로 보인다. 인식 모델 학습에는 **번호판만**")
        print("      잘라낸 이미지가 필요하다.  --crop 을 붙여 잘라내라.")

    # ------------------------------------------------------- 3) 글자 분포
    print(f"\n[3] 글자 분포 — 학습이 되고 안 되고를 가르는 값")
    han = Counter()
    for _, lab in good:
        for ch in pf.canonical(lab):
            if ch in pf.PLATE_HANGUL:
                han[ch] += 1
    print(f"    등장한 한글 {len(han)}종 / 번호판에 쓰이는 전체 {len(pf.PLATE_HANGUL)}종")
    rare = [(c, n) for c, n in han.items() if n < 10]
    missing = sorted(pf.PLATE_HANGUL - set(han))
    print(f"    많이 나온 순: " + "  ".join(f"{c}{n}" for c, n in han.most_common(12)))
    if rare:
        print(f"    10장 미만 (제대로 못 배움) {len(rare)}종: "
              + " ".join(f"{c}{n}" for c, n in sorted(rare, key=lambda kv: kv[1])))
    if missing:
        print(f"    아예 없음 {len(missing)}종: {' '.join(missing)}")
        print("    ※ 없는 글자는 학습 후에도 못 읽는다. 기존 모델보다 나빠질 수도 있다.")

    # ------------------------------------------------------------ 4) 중복
    by_plate: dict[str, list[Path]] = {}
    for p, lab in good:
        by_plate.setdefault(pf.canonical(lab), []).append(p)
    dup = {k: v for k, v in by_plate.items() if len(v) > 1}
    print(f"\n[4] 중복")
    print(f"    고유 번호판 {len(by_plate)}대 / 사진 {len(good)}장")
    if dup:
        print(f"    여러 장 있는 번호판 {len(dup)}대 "
              f"(최대 {max(len(v) for v in dup.values())}장)")
        print("    ※ train/val 은 **번호판 단위**로 나눈다. 같은 차가 양쪽에")
        print("      들어가면 검증 점수가 실제보다 높게 나온다.")

    # ------------------------------------------------------------- 판정
    print(f"\n{LINE}\n판정\n{LINE}")
    n_ok = len(good)
    if n_ok < 300:
        print(f"  사진 {n_ok}장은 파인튜닝에 부족하다. 500장 이상을 권한다.")
    elif n_ok < 800:
        print(f"  사진 {n_ok}장. 파인튜닝은 되지만 효과는 제한적일 수 있다.")
    else:
        print(f"  사진 {n_ok}장. 파인튜닝에 충분하다.")
    if missing:
        print(f"  다만 한글 {len(missing)}종이 데이터에 없다. 그 글자는 못 배운다.")
    if cropped / len(ars) < 0.5 and not a.crop:
        print("  번호판만 잘라내는 작업이 먼저 필요하다 (--crop).")

    if not a.build:
        print(f"\n학습용으로 내보내려면:  --build out\\train_data")
        return 0

    # ------------------------------------------------------------ 내보내기
    out = Path(a.build)
    (out / "train").mkdir(parents=True, exist_ok=True)
    (out / "val").mkdir(parents=True, exist_ok=True)

    plates = sorted(by_plate)
    random.Random(a.seed).shuffle(plates)          # 번호판 단위로 섞는다
    n_val = max(1, int(len(plates) * a.val_ratio))
    val_set = set(plates[:n_val])

    finder = None
    use_box = bool(boxfile)
    if a.crop and not use_box:
        from app.lpr.detector import PlateDetector
        finder = PlateDetector(mock=False)
        print("\n검출기로 번호판을 잘라냅니다 (실패한 사진은 건너뜁니다)...")
    elif use_box:
        print(f"\n라벨 박스로 번호판을 잘라냅니다 ({len(boxfile)}개)...")

    from app.core.config import settings
    from app.lpr import preprocess

    counts = {"train": 0, "val": 0, "skip": 0}
    lines: dict[str, list[str]] = {"train": [], "val": []}
    for plate, paths in by_plate.items():
        split = "val" if plate in val_set else "train"
        for i, p in enumerate(paths):
            im = imread_unicode(str(p))
            if im is None:
                counts["skip"] += 1
                continue

            bbox = None
            if p in boxfile:
                h0, w0 = im.shape[:2]
                bbox = yolo_box(boxfile[p], w0, h0)
            elif finder is not None:
                boxes = finder.detect(im, None)
                bbox = boxes[0].to_xyxy() if boxes else None

            if bbox is not None:
                # 학습 입력도 **운영과 똑같은 전처리**를 거쳐야 한다.
                # 깨끗한 원본으로만 배우면 실제 입력에서 성능이 안 나온다.
                r = preprocess.run(im, bbox_xyxy=bbox,
                                   target_h=settings.lpr.upscale_height,
                                   deskew_limit=settings.lpr.deskew_limit,
                                   denoise_min_height=settings.lpr.denoise_min_height)
                if r.image is None:
                    counts["skip"] += 1
                    continue
                im = r.image
            elif use_box or a.crop:
                counts["skip"] += 1          # 자르라고 했는데 좌표가 없다
                continue

            name = f"{plate}_{i}.png"
            imwrite_unicode(str(out / split / name), im)
            lines[split].append(f"{name}\t{plate}")
            counts[split] += 1

    for split in ("train", "val"):
        (out / split / "gt.txt").write_text("\n".join(lines[split]) + "\n",
                                            encoding="utf-8")
    print(f"\n내보내기 완료 → {out}")
    print(f"  train {counts['train']}장 / val {counts['val']}장 / 건너뜀 {counts['skip']}장")
    print(f"  라벨 파일: {out}\\train\\gt.txt , {out}\\val\\gt.txt")
    print("\n  이 폴더를 통째로 압축해 Colab 에 올리면 된다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
