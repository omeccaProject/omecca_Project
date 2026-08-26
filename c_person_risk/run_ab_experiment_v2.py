import os
import sys
import cv2
import numpy as np
import face_recognition

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
KNOWN_DIR = os.path.join(BASE_DIR, "known_faces")
OTHERS_DIR = os.path.join(BASE_DIR, "others")

CANDIDATE_PHOTOS = ["W001_이시헌_1.jpg", "W001_이시헌_2.jpg", "W001_이시헌_3.jpg"]
TOLERANCE = 0.48

def load_and_encode(img_path):
    img_array = np.fromfile(img_path, np.uint8)
    img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
    if img is None:
        return None
    h, w = img.shape[:2]
    if max(h, w) > 1080:
        scale = 1080 / max(h, w)
        img = cv2.resize(img, (int(w * scale), int(h * scale)))
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    locs = face_recognition.face_locations(rgb, model="hog")
    if not locs:
        return None
    encs = face_recognition.face_encodings(rgb, locs)
    return encs[0] if encs else None

print("\n" + "="*70)
print("🔬 [실험 2] 기준사진(1/2/3)별 False Accept 3x4 정밀 매트릭스 측정")
print("="*70)

base_embeddings = {}
for photo in CANDIDATE_PHOTOS:
    path = os.path.join(KNOWN_DIR, photo)
    if not os.path.exists(path):
        print(f"[경고] {photo} 파일이 known_faces 폴더에 없습니다.")
        continue
    emb = load_and_encode(path)
    if emb is not None:
        base_embeddings[photo] = emb
        print(f"[*] 기준 사진 로드 완료: {photo}")
    else:
        print(f"[오류] {photo} 안면 검출 실패")

if not base_embeddings:
    print("[ERROR] 등록 가능한 기준 사진이 없습니다.")
    sys.exit(1)

other_files = sorted([f for f in os.listdir(OTHERS_DIR) if f.lower().endswith(('.jpg', '.jpeg', '.png'))])
other_embeddings = {}
for o_name in other_files:
    o_path = os.path.join(OTHERS_DIR, o_name)
    o_emb = load_and_encode(o_path)
    if o_emb is not None:
        other_embeddings[o_name] = o_emb

matrix = {}
for photo_name, b_emb in base_embeddings.items():
    matrix[photo_name] = {}
    for o_name, o_emb in other_embeddings.items():
        dist = float(face_recognition.face_distance([b_emb], o_emb)[0])
        matrix[photo_name][o_name] = dist

print("\n" + "="*70)
print("📋 [클로드 전달용] 3x4 Raw Distance 매트릭스 (Tolerance: 0.48)")
print("="*70)

targets = list(other_embeddings.keys())
header = "| 기준 사진 (수배자) | " + " | ".join([t.replace('.jpg','') for t in targets]) + " | 평균 Dist | 판정 (오탐수) |"
sep = "| :--- | " + " | ".join([":---:" for _ in targets]) + " | :---: | :---: |"

print(header)
print(sep)

for photo_name, dist_dict in matrix.items():
    row_dists = [dist_dict.get(t, 0.0) for t in targets]
    fa_count = sum(1 for d in row_dists if d <= TOLERANCE)
    mean_d = np.mean(row_dists)
    
    vals_str = " | ".join([f"{d:.4f}{' (오탐)' if d <= TOLERANCE else ''}" for d in row_dists])
    status = f"❌ 오탐 {fa_count}건" if fa_count > 0 else "✅ 0건 (완벽 배제)"
    print(f"| {photo_name} | {vals_str} | {mean_d:.4f} | {status} |")

print("="*70)