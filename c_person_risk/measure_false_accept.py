import os
import pickle
import cv2
import numpy as np
import face_recognition

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "face_embeddings.pkl")
OTHERS_DIR = os.path.join(BASE_DIR, "others")

if not os.path.exists(DB_PATH):
    print("[ERROR] face_embeddings.pkl 파일이 없습니다.")
    exit(1)

with open(DB_PATH, "rb") as f:
    db = pickle.load(f)

known_embeddings = [item["embedding"] for item in db]
target_name = db[0]["name"] if db else "이시헌"
tolerance = 0.48

image_files = [f for f in os.listdir(OTHERS_DIR) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
if not image_files:
    print(f"[*] '{OTHERS_DIR}' 폴더에 사진 파일이 없습니다.")
    exit(0)

print("\n" + "="*65)
print(f"🎯 [False Accept(타인 오탐 방어) 다중 표본 실측]")
print(f" - 등록 수배자: {target_name} (Tolerance: {tolerance})")
print(f" - 검증 대상 사진: {len(image_files)}장")
print("="*65 + "\n")

results = []
false_accept_count = 0

for img_name in image_files:
    img_path = os.path.join(OTHERS_DIR, img_name)
    
    # 한글 경로 지원을 위한 바이너리 디코딩
    try:
        img_array = np.fromfile(img_path, np.uint8)
        img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
    except Exception as e:
        print(f"[-] {img_name}: 파일 로드 실패")
        continue

    if img is None:
        print(f"[-] {img_name}: 이미지 디코딩 실패")
        continue

    # 리사이즈 (연산 가속)
    h, w = img.shape[:2]
    if max(h, w) > 1080:
        scale = 1080 / max(h, w)
        img = cv2.resize(img, (int(w * scale), int(h * scale)))

    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    locs = face_recognition.face_locations(rgb, model="hog")
    
    if not locs:
        print(f"[-] {img_name:<20} | 얼굴 미검출 (건너뜀)")
        continue

    encs = face_recognition.face_encodings(rgb, locs)
    if not encs:
        continue

    # 가장 가까운 수배자 벡터와의 최소 거리 산출
    dists = face_recognition.face_distance(known_embeddings, encs[0])
    min_dist = float(np.min(dists))
    score = round(1.0 - min_dist, 2)
    
    # 판정
    is_false_accept = min_dist <= tolerance
    if is_false_accept:
        false_accept_count += 1
        verdict = f"❌ [FALSE ACCEPT - 오탐] (Dist: {min_dist:.4f} <= {tolerance})"
    else:
        verdict = f"✅ [TRUE REJECT - 정상 배제] (Dist: {min_dist:.4f} > {tolerance})"

    results.append((img_name, min_dist, score, not is_false_accept))
    print(f"▶ {img_name:<20} | Dist: {min_dist:.4f} | Score: {score:.2f} | {verdict}")

print("\n" + "="*65)
print("📋 [실측 요약 통계]")
print(f" - 총 검증 표본: {len(results)}건")
print(f" - True Reject (정상 배제): {len(results) - false_accept_count}건")
print(f" - False Accept (오탐): {false_accept_count}건")
if results:
    dists = [r[1] for r in results]
    print(f" - 타인 Distance 통계: 최소 {min(dists):.4f} ~ 최대 {max(dists):.4f} (평균 {np.mean(dists):.4f})")
    print(f" - 오탐 분리 마진: 최소 마진 {min(dists) - tolerance:+.4f}")
print("="*65)