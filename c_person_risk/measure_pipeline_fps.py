import os
import sys
import time
import cv2
import torch
import numpy as np
import face_recognition
from ultralytics import YOLO

# 1. GPU 및 환경 진단
print("\n" + "="*70)
print("🚀 [C파트 GPU 가속 & 다중 모델 동시 추론 실측 FPS 벤치마크]")
print("="*70)

cuda_ok = torch.cuda.is_available()
device = "cuda:0" if cuda_ok else "cpu"
gpu_name = torch.cuda.get_device_name(0) if cuda_ok else "N/A (CPU Only)"

print(f"[*] 하드웨어 가속 상태: {'✅ GPU 가속 활성화' if cuda_ok else '❌ CPU 모드'}")
print(f"[*] 활성 디바이스: {device} ({gpu_name})")

# 2. 모델 로드 (사람/안면 + 9클래스 흉기)
VIDEO_PATH = "stair_sample.mp4"
WEAPON_MODEL_PATH = "best.pt"
KNOWN_FACES_DIR = "known_faces"

if not os.path.exists(VIDEO_PATH):
    VIDEO_PATH = "sample.mp4"

print(f"[*] 대상 비디오 소스: {VIDEO_PATH}")
print(f"[*] 흉기 탐지 모델: {WEAPON_MODEL_PATH} (9클래스)")

person_model = YOLO("yolov8n.pt").to(device)
weapon_model = YOLO(WEAPON_MODEL_PATH).to(device) if os.path.exists(WEAPON_MODEL_PATH) else None

if weapon_model is None:
    print(f"[!] 경고: {WEAPON_MODEL_PATH} 가 없어 yolov8n으로 대체 로드합니다.")
    weapon_model = YOLO("yolov8n.pt").to(device)

# 수배자 임베딩 로드
known_encs = []
known_names = []
if os.path.exists(KNOWN_FACES_DIR):
    for f in os.listdir(KNOWN_FACES_DIR):
        if f.endswith(('.jpg', '.png', '.jpeg')):
            p = os.path.join(KNOWN_FACES_DIR, f)
            arr = np.fromfile(p, np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if img is not None:
                rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                locs = face_recognition.face_locations(rgb, model="hog")
                if locs:
                    known_encs.append(face_recognition.face_encodings(rgb, locs)[0])
                    known_names.append(f)

print(f"[*] 등록 수배자 프로필: {len(known_encs)}건 로드 완료")

# 3. 비디오 벤치마크 루프
cap = cv2.VideoCapture(VIDEO_PATH)
if not cap.isOpened():
    print(f"[ERROR] {VIDEO_PATH} 열기 실패")
    sys.exit(1)

total_video_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
native_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0

print(f"[*] 비디오 메타: 총 {total_video_frames}프레임 / 원본 {native_fps:.1f} FPS")
print("[*] 벤치마크 추론 시작 (얼굴인식 + 흉기탐지 동시 연산 중)...", flush=True)

processed_frames = 0
start_time = time.time()
frame_interval = 1  # 전 프레임 전수 추론

while True:
    ret, frame = cap.read()
    if not ret:
        break

    processed_frames += 1
    vh, vw = frame.shape[:2]

    # [모델 1: 사람 및 얼굴 인식 파이프라인]
    p_res = person_model(frame, classes=[0], conf=0.4, verbose=False, device=device)
    for r in p_res:
        for box in r.boxes:
            px1, py1, px2, py2 = map(int, box.xyxy[0].tolist())
            crop = frame[max(0, py1):min(vh, py2), max(0, px1):min(vw, px2)]
            if crop.size > 0 and (py2 - py1) >= 80:
                crgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
                flocs = face_recognition.face_locations(crgb, model="hog")
                if flocs and len(known_encs) > 0:
                    fencs = face_recognition.face_encodings(crgb, flocs)
                    if fencs:
                        _ = face_recognition.face_distance(known_encs, fencs[0])

    # [모델 2: 9클래스 흉기 탐지 파이프라인]
    _ = weapon_model(frame, conf=0.3, verbose=False, device=device)

    if processed_frames % 100 == 0:
        curr_elapsed = time.time() - start_time
        curr_fps = processed_frames / curr_elapsed
        print(f" -> [{processed_frames}/{total_video_frames} 프레임] 실시간 처리 속도: {curr_fps:.2f} FPS", flush=True)

cap.release()
total_elapsed = time.time() - start_time
avg_fps = processed_frames / total_elapsed

# 4. 결과 출력
print("\n" + "="*70)
print("🎯 [실측 벤치마크 최종 결과]")
print("="*70)
print(f"• 활성 GPU: {gpu_name} (CUDA 0번)")
print(f"• 동시 구동 모듈: YOLO 사람검출 + dlib 안면인식 + 9클래스 흉기탐지(best.pt)")
print(f"• 처리 프레임 수: 총 {processed_frames} 프레임")
print(f"• 총 소요 시간: {total_elapsed:.2f} 초")
print(f"• 실측 평균 처리 속도: ⭐️ {avg_fps:.2f} FPS ⭐️")
print("="*70)
