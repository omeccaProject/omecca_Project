from pathlib import Path
from collections import Counter

ROOT = Path("./a_detector")

# labels 폴더를 자동으로 전부 찾음
label_dirs = sorted({p for p in ROOT.rglob("labels") if p.is_dir()})

if not label_dirs:
    print("labels 폴더를 못 찾았습니다. 폴더 구조를 확인해주세요.")

for ld in label_dirs:
    txts = list(ld.rglob("*.txt"))
    if not txts:
        continue

    counter = Counter()
    empty = 0
    for txt in txts:
        lines = [l for l in txt.read_text().strip().splitlines() if l.strip()]
        if not lines:
            empty += 1
            continue
        for line in lines:
            counter[int(line.split()[0])] += 1

    total = sum(counter.values())
    print("=" * 55)
    print(f"[{ld.relative_to(ROOT)}]")
    print(f"  라벨 파일 {len(txts)}개 / 빈 라벨 {empty}개 / 총 객체 {total}개")
    for cid in sorted(counter):
        pct = counter[cid] / total * 100 if total else 0
        print(f"    class {cid} : {counter[cid]:6d}  ({pct:5.1f}%)")
    print()