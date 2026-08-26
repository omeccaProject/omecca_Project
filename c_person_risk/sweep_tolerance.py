import os
import sys
import pickle
import time
import cv2
import numpy as np
import face_recognition
from ultralytics import YOLO

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "face_embeddings.pkl")
VIDEO_PATH = os.path.join(BASE_DIR, "stair_sample.mp4")

TOLERANCE_SWEEP = [0.40, 0.41, 0.42, 0.44, 0.46, 0.48]

if not os.path.exists(DB_PATH):
    print(f"[ERROR] {DB_PATH} 파일이 없습니다.")
    sys.exit(1)

if not os.path.exists(VIDEO_PATH):
    print(f"[ERROR] {VIDEO_PATH} 영상 파일이 없습니다.")
    sys.exit(1)

with open(DB_PATH, "rb") as f:
    db = pickle.load(f)

known_embeddings = [item["embedding"] for item in db]
target_name = db[0].get("name", "이시헌")

print("\n" + "="*70)
print(f"🚀 [Step 2-3: Tolerance 스윕 & 구간별 재현율 정밀 실측]")
print(f" - 등록 DB: {target_name} ({len(known_embeddings)}개 벡터)")
print(f" - 대상 영상: {os.path.basename(VIDEO_PATH)}")
print(f" - 스윕 대상 Tolerance: {TOLERANCE_SWEEP}")
print("="*70 + "\n", flush=True)

person_model = YOLO("yolov8n.pt")
cap = cv2.VideoCapture(VIDEO_PATH)

fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

zone_dists = {"zone1": [], "zone2": [], "zone3": []}
frame_idx = 0
start_time = time.time()

print("[*] 영상 프레임 전수 순회 및 Raw Distance 수집 중...", flush=True)

while True:
    ret, frame = cap.read()
    if not ret:
        break

    frame_idx += 1
    curr_sec = frame_idx / fps
    vh, vw = frame.shape[:2]

    # 가속을 위한 960px 리사이즈
    if vw > 960:
        scale = 960 / vw
        frame = cv2.resize(frame, (960, int(vh * scale)))
        vh, vw = frame.shape[:2]

    p_res = person_model(frame, classes=[0], conf=0.4, verbose=False)
    frame_face_dist = None

    for r in p_res:
        for box in r.boxes:
            px1, py1, px2, py2 = map(int, box.xyxy[0].tolist())
            px1, py1 = max(0, px1), max(0, py1)
            px2, py2 = min(vw, px2), min(vh, py2)

            if (py2 - py1) < 100 or (px2 - px1) < 40:
                continue

            crop = frame[py1:py2, px1:px2]
            if crop.size == 0:
                continue

            crgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
            clocs = face_recognition.face_locations(crgb, model="hog")
            if clocs:
                cencs = face_recognition.face_encodings(crgb, clocs)
                if cencs:
                    dists = face_recognition.face_distance(known_embeddings, cencs[0])
                    frame_face_dist = float(np.min(dists))

    # 구간별 Raw Distance 기록
    if frame_face_dist is not None:
        if curr_sec <= 15.0:
            zone_dists["zone1"].append(frame_face_dist)
        elif curr_sec <= 35.0:
            zone_dists["zone2"].append(frame_face_dist)
        else:
            zone_dists["zone3"].append(frame_face_dist)

    if frame_idx % 60 == 0 or frame_idx == total_frames:
        elapsed = time.time() - start_time
        print(f" -> [{frame_idx}/{total_frames} 프레임] 진행률: {frame_idx/total_frames*100:5.1f}% | 소요: {elapsed:4.1f}초", flush=True)

cap.release()

# -------------------------------------------------------------
# 클로드 보고용 Tolerance 스윕 결과 집계
# -------------------------------------------------------------
z1_total = len(zone_dists["zone1"])
z2_total = len(zone_dists["zone2"])
z3_total = len(zone_dists["zone3"])

print("\n" + "="*70)
print("📋 [클로드 전달용] Tolerance 스윕 구간별 매칭률 실측 결과표")
print("="*70)
print(f"총 안면 검출 프레임 수: 1구간({z1_total}프레임), 2구간({z2_total}프레임), 3구간({z3_total}프레임)\n")

print("| tolerance | 1구간 (20~30도) | 2구간 (35~45도) | 3구간 (50~60도) | 비고 |")
print("| :---: | :---: | :---: | :---: | :--- |")

for tol in TOLERANCE_SWEEP:
    z1_hits = sum(1 for d in zone_dists["zone1"] if d <= tol)
    z2_hits = sum(1 for d in zone_dists["zone2"] if d <= tol)
    z3_hits = sum(1 for d in zone_dists["zone3"] if d <= tol)

    z1_rate = (z1_hits / z1_total * 100) if z1_total > 0 else 0.0
    z2_rate = (z2_hits / z2_total * 100) if z2_total > 0 else 0.0
    z3_rate = (z3_hits / z3_total * 100) if z3_total > 0 else 0.0

    note = ""
    if tol <= 0.40:
        note = "김관용(0.4086) 배제 가능 구간"
    elif tol == 0.48:
        note = "기존 기준값"

    print(f"| {tol:.2f} | {z1_rate:5.1f}% ({z1_hits:2d}/{z1_total}) | {z2_rate:5.1f}% ({z2_hits:2d}/{z2_total}) | {z3_rate:5.1f}% ({z3_hits:2d}/{z3_total}) | {note} |")

print("="*70)