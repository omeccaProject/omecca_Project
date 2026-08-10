import os
import shutil
import random
import hashlib
import yaml

random.seed(42)

OUTPUT_DIR = "road_hazard_v3"
SPLITS = ["train", "valid", "test"]

FINAL_CLASS_NAMES = [
    'electric_scooter',   # 0
    'traffic_cone',       # 1
    'road_debris',        # 2
]

# name_map: {원본 클래스 "이름": 통합 후 id}  — 목록에 없는 이름은 전부 제외됨
# max_obj : 한 장에 객체가 이 개수 초과면 제외
# budget  : split별 최대 객체 수 (None = 전부)
DATASETS = [
    {"dir": "unusual_raw",   "prefix": "un_",
     "name_map": {"debris": 2},
     "max_obj": 12, "budget": None},

    {"dir": "obstacle_raw",  "prefix": "ob_",
     "name_map": {"road_debris": 2, "fallen_tree": 2},
     "max_obj": 12, "budget": None},

    {"dir": "tire_raw",      "prefix": "tr_",
     "name_map": {"car-tire": 2},
     "max_obj": None, "budget": None},

    {"dir": "box_raw",       "prefix": "bx_",
     "name_map": {"Carton": 2},
     "max_obj": 3, "budget": {"train": 800, "valid": 250, "test": 120}},

     # 새 데이터셋: 전량 사용 (방치 상태 포함)
    {"dir": "kickboard_new", "prefix": "kn_",
     "name_map": {"kb": 0},          # ← 할 일 2에서 확인한 이름으로!
     "max_obj": None, "budget": None},

    # 기존: 주행 중 사진이라 대폭 축소
    {"dir": "kickboard_raw", "prefix": "kb_",
     "name_map": {"KickBorad": 0},
     "max_obj": None, "budget": {"train": 700, "valid": 200, "test": 100}},

    {"dir": "cone_raw",      "prefix": "cn_",
     "name_map": {"Safety Cone": 1},
     "max_obj": 8, "budget": {"train": 2500, "valid": 800, "test": 400}},
]

VALID_DIR_CANDIDATES = ["valid", "val"]

seen_hash = set()      # 이미지 내용 중복
seen_stem = set()      # Roboflow 원본 파일명 중복
unmapped = {}          # 매핑 안 된 클래스명 기록


def load_names(base_dir):
    """데이터셋의 data.yaml에서 {클래스id: 이름} 반환"""
    for cand in ["data.yaml", "data.yml"]:
        p = os.path.join(base_dir, cand)
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                d = yaml.safe_load(f)
            n = d.get("names")
            if isinstance(n, dict):
                return {int(k): v for k, v in n.items()}
            if isinstance(n, list):
                return {i: v for i, v in enumerate(n)}
    return None


def rf_stem(fname):
    """Roboflow 내보내기 파일명에서 원본 이름 추출 (114_jpeg.rf.abc123.jpg -> 114_jpeg)"""
    base = os.path.splitext(fname)[0]
    return base.split(".rf.")[0].lower()


def find_split_dir(base_dir, split):
    if split == "valid":
        for c in VALID_DIR_CANDIDATES:
            if os.path.exists(os.path.join(base_dir, c)):
                return c
    return split if os.path.exists(os.path.join(base_dir, split)) else None


def copy_split(ds, split, actual, id2final):
    src_dir = ds["dir"]
    src_img = os.path.join(src_dir, actual, "images")
    src_lbl = os.path.join(src_dir, actual, "labels")
    dst_img = os.path.join(OUTPUT_DIR, split, "images")
    dst_lbl = os.path.join(OUTPUT_DIR, split, "labels")

    if not os.path.exists(src_img):
        return 0, 0, 0, {}

    os.makedirs(dst_img, exist_ok=True)
    os.makedirs(dst_lbl, exist_ok=True)

    candidates = []
    sk_dense = 0
    sk_dup = 0

    for fname in sorted(os.listdir(src_img)):
        stem = rf_stem(fname)
        if stem in seen_stem:
            sk_dup += 1
            continue

        path = os.path.join(src_img, fname)
        try:
            with open(path, "rb") as f:
                h = hashlib.md5(f.read()).hexdigest()
        except OSError:
            continue
        if h in seen_hash:
            sk_dup += 1
            continue

        lbl_path = os.path.join(src_lbl, os.path.splitext(fname)[0] + ".txt")
        new_lines = []
        if os.path.exists(lbl_path):
            with open(lbl_path, "r") as f:
                for line in f:
                    parts = line.strip().split()
                    if not parts:
                        continue
                    old = int(parts[0])
                    name = id2final.get(old, f"<id{old}>")
                    if name not in ds["name_map"]:
                        unmapped.setdefault(src_dir, set()).add(name)
                        continue
                    parts[0] = str(ds["name_map"][name])
                    new_lines.append(" ".join(parts))

        if not new_lines:
            continue
        if ds["max_obj"] is not None and len(new_lines) > ds["max_obj"]:
            sk_dense += 1
            continue

        candidates.append((fname, new_lines, h, stem))

    budget = ds["budget"]
    limit = budget.get(split) if isinstance(budget, dict) else budget
    if limit is not None:
        random.shuffle(candidates)
        candidates.sort(key=lambda x: len(x[1]))
        picked, used = [], 0
        for c in candidates:
            if used + len(c[1]) > limit:
                continue
            picked.append(c)
            used += len(c[1])
        candidates = picked

    cls_count = {}
    for fname, new_lines, h, stem in candidates:
        seen_hash.add(h)
        seen_stem.add(stem)
        new_name = ds["prefix"] + fname
        shutil.copy(os.path.join(src_img, fname), os.path.join(dst_img, new_name))
        with open(os.path.join(dst_lbl, os.path.splitext(new_name)[0] + ".txt"), "w") as f:
            f.write("\n".join(new_lines))
        for l in new_lines:
            c = int(l.split()[0])
            cls_count[c] = cls_count.get(c, 0) + 1

    return len(candidates), sk_dense, sk_dup, cls_count


def main():
    print(f"최종 클래스 {len(FINAL_CLASS_NAMES)}개: {FINAL_CLASS_NAMES}\n")

    id2final_cache = {}
    for ds in DATASETS:
        names = load_names(ds["dir"])
        if names is None:
            print(f"  [주의] {ds['dir']}/data.yaml 없음 -> 이 데이터셋 건너뜀")
        id2final_cache[ds["dir"]] = names

    grand_total = 0
    grand_cls = {s: {} for s in SPLITS}

    for split in SPLITS:
        total = 0
        print(f"[{split}]")
        for ds in DATASETS:
            id2final = id2final_cache[ds["dir"]]
            if id2final is None:
                continue
            actual = find_split_dir(ds["dir"], split)
            if actual is None:
                print(f"  {ds['dir']:16s} '{split}' 없음")
                continue
            n, sk_dense, sk_dup, cls_count = copy_split(ds, split, actual, id2final)
            obj = sum(cls_count.values())
            msg = f"  {ds['dir']:16s} {n:5d}장 / 객체 {obj:5d}개"
            if sk_dup:
                msg += f"  (중복 {sk_dup}장)"
            if sk_dense:
                msg += f"  (객체과다 {sk_dense}장)"
            print(msg)
            total += n
            for c, v in cls_count.items():
                grand_cls[split][c] = grand_cls[split].get(c, 0) + v
        print(f"  -> {split} 합계: {total}장\n")
        grand_total += total

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(os.path.join(OUTPUT_DIR, "data.yaml"), "w") as f:
        f.write("\n".join([
            "train: train/images",
            "val: valid/images",
            "test: test/images",
            "",
            f"nc: {len(FINAL_CLASS_NAMES)}",
            f"names: {FINAL_CLASS_NAMES}",
        ]))

    if unmapped:
        print("=" * 55)
        print("매핑에서 제외된 클래스 (의도한 것인지 확인하세요)")
        for d, names in unmapped.items():
            print(f"  {d}: {sorted(names)}")
        print()

    print("=" * 55)
    print("최종 클래스 분포")
    for split in SPLITS:
        tot = sum(grand_cls[split].values())
        if not tot:
            continue
        print(f"\n[{split}] 총 {tot}개")
        for c in sorted(grand_cls[split]):
            v = grand_cls[split][c]
            print(f"  {FINAL_CLASS_NAMES[c]:18s} {v:6d}  ({v/tot*100:5.1f}%)")
    print(f"\n병합 완료: 총 {grand_total}장 · {OUTPUT_DIR}/data.yaml 생성됨")


if __name__ == "__main__":
    main()