import os
import shutil

OUTPUT_DIR = "road_hazard_finetune"
SPLITS = ["train", "valid", "test"]

# ===== 합칠 데이터셋 등록 =====
# class_remap: {원본 클래스 id: 통합 후 id}  — 매핑에 없는 id는 자동으로 버려짐
DATASETS = [
    # 킥보드: ['KickBorad'] → electric_scooter(0)
    {"dir": "kickboard_raw", "prefix": "kb_", "class_remap": {0: 0}},

    # 타이어: ['car-tire'] → car_tire(1)
    {"dir": "tire_raw",      "prefix": "tr_", "class_remap": {0: 1}},

    # 박스: ['Carton'] → box(2)
    {"dir": "box_raw",       "prefix": "bx_", "class_remap": {0: 2}},

    # 라바콘: ['Safety Cone'] → traffic_cone(3)
    {"dir": "cone_raw",      "prefix": "cn_", "class_remap": {0: 3}},

    # 나무: ['Roads', 'Trees'] → Trees(1)만 fallen_tree(4)로. Roads(0)는 제외
    {"dir": "tree_raw",      "prefix": "tw_", "class_remap": {1: 4}},

    # 흉기: ['blunt weapon', 'knife'] → blunt_weapon(6), knife(5)
    {"dir": "weapon_raw",    "prefix": "wp_", "class_remap": {0: 6, 1: 5}},
]

FINAL_CLASS_NAMES = [
    'electric_scooter',
    'car_tire',
    'box',
    'traffic_cone',
    'fallen_tree',
    'knife',
    'blunt_weapon',
]

VALID_DIR_CANDIDATES = ["valid", "val"]


def find_split_dir(base_dir, split):
    if split == "valid":
        for c in VALID_DIR_CANDIDATES:
            if os.path.exists(os.path.join(base_dir, c)):
                return c
    return split if os.path.exists(os.path.join(base_dir, split)) else None


def copy_split(src_dir, dst_dir, split, actual_src_split, prefix, class_remap):
    src_img = os.path.join(src_dir, actual_src_split, "images")
    src_lbl = os.path.join(src_dir, actual_src_split, "labels")
    dst_img = os.path.join(dst_dir, split, "images")
    dst_lbl = os.path.join(dst_dir, split, "labels")

    if not os.path.exists(src_img):
        print(f"  ⚠️  건너뜀 (이미지 폴더 없음): {src_img}")
        return 0, 0

    os.makedirs(dst_img, exist_ok=True)
    os.makedirs(dst_lbl, exist_ok=True)

    copied = 0
    skipped_empty = 0

    for fname in os.listdir(src_img):
        lbl_name = os.path.splitext(fname)[0] + ".txt"
        src_lbl_path = os.path.join(src_lbl, lbl_name)

        # 라벨 파일 먼저 처리해서, 남는 객체가 하나도 없으면 이미지도 복사 안 함
        new_lines = []
        if os.path.exists(src_lbl_path):
            with open(src_lbl_path, "r") as f:
                for line in f:
                    parts = line.strip().split()
                    if not parts:
                        continue
                    old_cls = int(parts[0])
                    if old_cls not in class_remap:
                        continue  # 제외 대상 클래스 (background, Roads 등)
                    parts[0] = str(class_remap[old_cls])
                    new_lines.append(" ".join(parts))

        if not new_lines:
            skipped_empty += 1
            continue

        new_name = prefix + fname
        shutil.copy(os.path.join(src_img, fname), os.path.join(dst_img, new_name))

        new_lbl_name = os.path.splitext(new_name)[0] + ".txt"
        with open(os.path.join(dst_lbl, new_lbl_name), "w") as f:
            f.write("\n".join(new_lines))

        copied += 1

    return copied, skipped_empty


def main():
    print(f"합칠 데이터셋: {len(DATASETS)}개")
    print(f"최종 클래스 {len(FINAL_CLASS_NAMES)}개: {FINAL_CLASS_NAMES}\n")

    grand_total = 0
    for split in SPLITS:
        total = 0
        print(f"[{split}]")
        for ds in DATASETS:
            actual = find_split_dir(ds["dir"], split)
            if actual is None:
                print(f"  ⚠️  {ds['dir']}: '{split}' 없음, 건너뜀")
                continue
            n, skipped = copy_split(ds["dir"], OUTPUT_DIR, split, actual,
                                    ds["prefix"], ds["class_remap"])
            msg = f"  {ds['dir']}: {n}장"
            if skipped:
                msg += f"  (제외 클래스만 있어서 버린 이미지 {skipped}장)"
            print(msg)
            total += n
        print(f"  → {split} 합계: {total}장\n")
        grand_total += total

    yaml_lines = [
        "train: train/images",
        "val: valid/images",
        "test: test/images",
        "",
        f"nc: {len(FINAL_CLASS_NAMES)}",
        f"names: {FINAL_CLASS_NAMES}",
    ]
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(os.path.join(OUTPUT_DIR, "data.yaml"), "w") as f:
        f.write("\n".join(yaml_lines))

    print(f"✅ 병합 완료: 총 {grand_total}장 · {OUTPUT_DIR}/data.yaml 생성됨")


if __name__ == "__main__":
    main()