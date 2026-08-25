import os
import sys
import time
import cv2
import numpy as np
import face_recognition
from ultralytics import YOLO

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
KNOWN_DIR = os.path.join(BASE_DIR, "known_faces")
VIDEO_PATH = os.path.join(BASE_DIR, "stair_sample.mp4")
PHOTO2_PATH = os.path.join(KNOWN_DIR, "W001_이시헌_2.jpg")

TOLERANCE = 0.48

if not os.path.exists(PHOTO2_PATH):
    print(f"[ERROR] {PHOTO2_PATH} 파일이 없습니다.")
    sys.exit(1)

if not os.path.exists(VIDEO_PATH):
    print(f"[ERROR] {VIDEO_PATH} 영상 파일이 없습니다.")
    sys.exit(1)

print("\n" + "="*70)
print("🎯 [W001_이시헌_2.jpg 기준 stair_sample.mp4 재현율 실측]")
print("="*70)

# 1. W001_이시헌_2.jpg CNN 임베딩 추출
print("[*] 1단계: W001_이시헌_2.jpg CNN 모델 임베딩 추출 중...", flush=True)
img_arr = np.fromfile(PHOTO2_PATH, np.uint8)
img = cv2.imdecode(img_arr, cv2.IMREAD_COLOR)
h, w = img.shape[:2]
if max(h, w) > 1080:
    s = 1080 / max(h, w)
    img = cv2.resize(img, (int(w * s), int(h * s)))

rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
locs = face_recognition.face_locations(rgb, model="cnn", number_of_times_to_upsample=1)

if not locs:
    print("[ERROR] W001_이시헌_2.jpg CNN 안면 검출 실패")
    sys.exit(1)

encs = face_recognition.face_encodings(rgb, locs)
if not encs:
    print("[ERROR] W001_이시헌_2.jpg 임베딩 생성 실패")
    sys.exit(1)

embed_photo2 = encs[0]
print(f"[*] 임베딩 추출 완료 (검출 안면: {len(locs)}개)")

# 2. stair_sample.mp4 프레임 전수 순회
print("\n[*] 2단계: stair_sample.mp4 프레임 순회 및 Distance 측정 시작...", flush=True)
person_model = YOLO("yolov8n.pt")
cap = cv2.VideoCapture(VIDEO_PATH)

fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

zone_records = {"zone1": [], "zone2": [], "zone3": []}
frame_idx = 0
start_time = time.time()

while True:
    ret, frame = cap.read()
    if not ret:
        break

    frame_idx += 1
    curr_sec = frame_idx / fps
    vh, vw = frame.shape[:2]

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
                    dist = float(face_recognition.face_distance([embed_photo2], cencs[0])[0])
                    frame_face_dist = dist

    if frame_face_dist is not None:
        matched = (frame_face_dist <= TOLERANCE)
        if curr_sec <= 15.0:
            zone_records["zone1"].append((frame_face_dist, matched))
        elif curr_sec <= 35.0:
            zone_records["zone2"].append((frame_face_dist, matched))
        else:
            zone_records["zone3"].append((frame_face_dist, matched))

    if frame_idx % 120 == 0 or frame_idx == total_frames:
        elapsed = time.time() - start_time
        print(f" -> [{frame_idx}/{total_frames} 프레임] 진행률: {frame_idx/total_frames*100:5.1f}% | 소요: {elapsed:4.1f}초", flush=True)

cap.release()

# 3. 통계 집계
def calc_stats(records):
    if not records:
        return 0, 0, 0.0, 0.0
    total = len(records)
    hits = sum(1 for r in records if r[1])
    rate = (hits / total * 100) if total > 0 else 0.0
    mean_d = float(np.mean([r[0] for r in records])) if total > 0 else 0.0
    return hits, total, rate, mean_d

z1_hits, z1_tot, z1_rate, z1_mean = calc_stats(zone_records["zone1"])
z2_hits, z2_tot, z2_rate, z2_mean = calc_stats(zone_records["zone2"])
z3_hits, z3_tot, z3_rate, z3_mean = calc_stats(zone_records["zone3"])

# 4. 클로드 보고용 결과표 출력
print("\n" + "="*70)
print("📋 [클로드 전달용] W001_이시헌_2.jpg vs _1.jpg 재현율 비교표 (Tolerance: 0.48)")
print("="*70)

report_text = f"""[C파트 - _2.jpg 기준사진 고각도 재현율 실측 결과 보고]

1. False Accept 개선 현황 (사전 측정 완료치)
- 김관용: 0.4086 -> 0.4689 (오탐 유지)
- 김준호: 0.4546 -> 0.5609 (정상 배제로 전환)
- 장성혁: 0.4692 -> 0.6138 (정상 배제로 전환)
- 박지원: 0.5003 -> 0.5135 (정상 배제 유지)
* 오탐율: 기존 75%(3/4) -> 25%(1/4)로 대폭 개선

2. Step 2-2 고각도(stair_sample.mp4) 재현율 비교 (Tolerance: 0.48)
-----------------------------------------------------------------------------------------
| 구간 (수직 피치) | _1.jpg (기존 기준값) | _2.jpg (대조군 실측치) | 변화량 (Δ) | _2.jpg 평균 Dist |
| :--- | :---: | :---: | :---: | :---: |
| 1구간 (20~30도) | 51.0% (80/157) | {z1_rate:5.1f}% ({z1_hits:2d}/{z1_tot:3d}) | {z1_rate - 51.0:+5.1f}%p | {z1_mean:.4f} |
| 2구간 (35~45도) | 25.4% (30/118) | {z2_rate:5.1f}% ({z2_hits:2d}/{z2_tot:3d}) | {z2_rate - 25.4:+5.1f}%p | {z2_mean:.4f} |
| 3구간 (50~60도) | 18.9% (25/132) | {z3_rate:5.1f}% ({z3_hits:2d}/{z3_tot:3d}) | {z3_rate - 18.9:+5.1f}%p | {z3_mean:.4f} |
-----------------------------------------------------------------------------------------"""

print(report_text)
print("="*70)