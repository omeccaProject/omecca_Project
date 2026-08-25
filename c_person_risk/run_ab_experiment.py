import os
import sys
import shutil
import pickle
import time
import cv2
import numpy as np
import face_recognition
from ultralytics import YOLO

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
KNOWN_DIR = os.path.join(BASE_DIR, "known_faces")
OTHERS_DIR = os.path.join(BASE_DIR, "others")
BACKUP_DIR = os.path.join(BASE_DIR, f"known_faces_backup_{time.strftime('%Y%m%d_%H%M%S')}")
TEMP_PKL = os.path.join(BASE_DIR, "face_embeddings_temp.pkl")
VIDEO_PATH = os.path.join(BASE_DIR, "stair_sample.mp4")

TOLERANCE = 0.48

print("\n" + "="*70)
print("[C파트 - False Accept & Recall 대조실험 자동화 파이프라인]")
print("="*70)

# [1단계] known_faces 백업
if os.path.exists(KNOWN_DIR):
    shutil.copytree(KNOWN_DIR, BACKUP_DIR)
    print(f"[*] 1단계: known_faces 백업 완료 -> {os.path.basename(BACKUP_DIR)}")
else:
    print("[ERROR] known_faces 폴더가 존재하지 않습니다.")
    sys.exit(1)

# [2단계] 단일 정면 사진(W001_이시헌_1.jpg) 기반 임시 DB 생성
single_photo = "W001_이시헌_1.jpg"
single_photo_path = os.path.join(KNOWN_DIR, single_photo)

if not os.path.exists(single_photo_path):
    files = sorted([f for f in os.listdir(KNOWN_DIR) if f.lower().endswith(('.jpg', '.jpeg', '.png'))])
    if not files:
        print("[ERROR] known_faces 폴더에 사진이 없습니다.")
        sys.exit(1)
    single_photo = files[0]
    single_photo_path = os.path.join(KNOWN_DIR, single_photo)

print(f"[*] 2단계: 기준 단일 정면 사진 -> {single_photo}")

img_array = np.fromfile(single_photo_path, np.uint8)
img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
h, w = img.shape[:2]
if max(h, w) > 1080:
    scale = 1080 / max(h, w)
    img = cv2.resize(img, (int(w * scale), int(h * scale)))

rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
locs = face_recognition.face_locations(rgb, model="hog")
if not locs:
    print(f"[ERROR] {single_photo}에서 얼굴을 검출할 수 없습니다.")
    sys.exit(1)

encs = face_recognition.face_encodings(rgb, locs)
if not encs:
    print(f"[ERROR] {single_photo} 임베딩 생성 실패.")
    sys.exit(1)

temp_db = [{"name": "이시헌", "embedding": encs[0], "source_file": single_photo}]
with open(TEMP_PKL, "wb") as f:
    pickle.dump(temp_db, f)
print(f"[*] 2단계 완료: face_embeddings_temp.pkl 격리 저장 완료 (벡터 1개)")

# [3단계] False Accept 재측정 (타인 4명 vs 단일 임베딩)
print("\n[*] 3단계: 타인 4명 False Accept 재측정 중...")
other_files = sorted([f for f in os.listdir(OTHERS_DIR) if f.lower().endswith(('.jpg', '.jpeg', '.png'))])
single_embed = encs[0]

fa_results = {}
for o_name in other_files:
    o_path = os.path.join(OTHERS_DIR, o_name)
    o_arr = np.fromfile(o_path, np.uint8)
    o_img = cv2.imdecode(o_arr, cv2.IMREAD_COLOR)
    if o_img is None:
        continue

    oh, ow = o_img.shape[:2]
    if max(oh, ow) > 1080:
        s = 1080 / max(oh, ow)
        o_img = cv2.resize(o_img, (int(ow * s), int(oh * s)))

    o_rgb = cv2.cvtColor(o_img, cv2.COLOR_BGR2RGB)
    o_locs = face_recognition.face_locations(o_rgb, model="hog")
    if not o_locs:
        continue
    o_encs = face_recognition.face_encodings(o_rgb, o_locs)
    if not o_encs:
        continue

    dist = float(face_recognition.face_distance([single_embed], o_encs[0])[0])
    fa_results[o_name] = dist
    print(f"    - {o_name}: {dist:.4f}")

# [4단계] Step 2-2 고각도(stair_sample.mp4) 재현율 재측정
print("\n[*] 4단계: stair_sample.mp4 고각도 재현율 재측정 중...")
if not os.path.exists(VIDEO_PATH):
    print(f"[ERROR] {VIDEO_PATH} 영상 파일이 없습니다.")
    sys.exit(1)

cap = cv2.VideoCapture(VIDEO_PATH)
fps = cap.get(cv2.CAP_PROP_FPS) or 30.0

person_model = YOLO("yolov8n.pt")
try:
    import torch
    if torch.cuda.is_available():
        person_model.to(0)
        print("    [*] GPU(0번) 사용")
    else:
        print("    [*] GPU 미검출, CPU로 진행")
except Exception as e:
    print(f"    [WARN] device 확인 실패, CPU로 진행: {e}")

video_stats = {"zone1": [], "zone2": [], "zone3": []}
frame_idx = 0

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
    curr_dist = None
    matched = False

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
                    cdist = float(face_recognition.face_distance([single_embed], cencs[0])[0])
                    curr_dist = cdist
                    if cdist <= TOLERANCE:
                        matched = True

    if curr_dist is not None:
        if curr_sec <= 15:
            video_stats["zone1"].append((curr_dist, matched))
        elif curr_sec <= 35:
            video_stats["zone2"].append((curr_dist, matched))
        else:
            video_stats["zone3"].append((curr_dist, matched))

cap.release()

def calc_zone(records):
    if not records:
        return 0.0, 0, 0, 0.0
    dists = [r[0] for r in records]
    hits = sum(1 for r in records if r[1])
    return np.mean(dists), hits, len(records), (hits / len(records)) * 100

z1_mean, z1_hits, z1_tot, z1_rate = calc_zone(video_stats["zone1"])
z2_mean, z2_hits, z2_tot, z2_rate = calc_zone(video_stats["zone2"])
z3_mean, z3_hits, z3_tot, z3_rate = calc_zone(video_stats["zone3"])

print("\n" + "="*70)
print("[클로드 전달용] False Accept & 고각도 재현율 대조실험 결과표")
print("="*70)

report_text = f"""[C파트 - 단일 등록 vs 다중 등록 대조실험 실측 결과 보고]

1. 타인 4명 False Accept (Raw Distance) 비교 (Tolerance: {TOLERANCE})
----------------------------------------------------------------------
| 대상자 | 다중 등록(기존) | 단일 등록(대조군) | 변화량(D) | 단일 판정 |
| 김관용 | 0.4086 (오탐) | {fa_results.get('김관용.jpg', 0.0):.4f} | {fa_results.get('김관용.jpg', 0.0)-0.4086:+.4f} | {'오탐' if fa_results.get('김관용.jpg', 1.0) <= TOLERANCE else '정상 배제'} |
| 김준호 | 0.4546 (오탐) | {fa_results.get('김준호.jpg', 0.0):.4f} | {fa_results.get('김준호.jpg', 0.0)-0.4546:+.4f} | {'오탐' if fa_results.get('김준호.jpg', 1.0) <= TOLERANCE else '정상 배제'} |
| 장성혁 | 0.4692 (오탐) | {fa_results.get('장성혁.jpg', 0.0):.4f} | {fa_results.get('장성혁.jpg', 0.0)-0.4692:+.4f} | {'오탐' if fa_results.get('장성혁.jpg', 1.0) <= TOLERANCE else '정상 배제'} |
| 박지원 | 0.5003 (정상) | {fa_results.get('박지원.jpg', 0.0):.4f} | {fa_results.get('박지원.jpg', 0.0)-0.5003:+.4f} | {'오탐' if fa_results.get('박지원.jpg', 1.0) <= TOLERANCE else '정상 배제'} |

2. Step 2-2 고각도(stair_sample.mp4) 재현율 비교 (Tolerance: {TOLERANCE})
----------------------------------------------------------------------
| 구간 | 다중 등록 매칭률 | 단일 등록 매칭률 | 매칭 프레임 수 | 평균 Dist |
| 1구간(20~30도) | 37.9% | {z1_rate:.1f}% | {z1_hits}/{z1_tot} | {z1_mean:.4f} |
| 2구간(35~45도) | 16.9% | {z2_rate:.1f}% | {z2_hits}/{z2_tot} | {z2_mean:.4f} |
| 3구간(50~60도) | 14.8% | {z3_rate:.1f}% | {z3_hits}/{z3_tot} | {z3_mean:.4f} |

* 기준 등록 이미지: {single_photo} (단일 1장)"""

print(report_text)
print("="*70)