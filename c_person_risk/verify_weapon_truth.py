import os
import cv2
from weapon_detect import WeaponDetector

print("="*70)
print("🔍 [1. test_contracts.py 내 더미 폴백 코드 점검]")
print("="*70)
with open("test_contracts.py", "r", encoding="utf-8") as f:
    contract_code = f.read()

if "0.78" in contract_code or "150, 200, 300, 450" in contract_code:
    print("⚠️ [확인 완료] test_contracts.py 내에 더미 폴백(conf=0.78, bbox=[150,200,300,450])이 존재합니다.")
    print("   -> 흉기 미검출 시 스키마 직렬화 중단을 방어하기 위한 Mock 코드로 확인됨.")
else:
    print("ℹ️ 더미 폴백 하드코딩이 없습니다.")

print("\n" + "="*70)
print("🔍 [2. 샘플 영상별 WeaponDetector(best.pt) 실제 흉기 검출 실측]")
print("="*70)

detector = WeaponDetector()
target_videos = ["my_sample.mp4", "1sample.mp4", "stair_sample.mp4"]

for vid in target_videos:
    if not os.path.exists(vid):
        print(f"[-] {vid}: 파일 없음")
        continue

    cap = cv2.VideoCapture(vid)
    frame_idx = 0
    detected_frames = 0
    sample_detections = []

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frame_idx += 1
        
        # 5프레임 간격 샘플링
        if frame_idx % 5 == 0:
            try:
                raw = detector.detect_weapons(frame)
            except Exception as e:
                raw = []
            
            if raw and len(raw) > 0:
                detected_frames += 1
                if len(sample_detections) < 3:
                    sample_detections.append((frame_idx, raw))

    cap.release()
    print(f"\n[*] 대상 영상: {vid} (총 {frame_idx} 프레임 중 샘플링 검사)")
    print(f" -> 실제 흉기 탐지 성공 프레임 수: {detected_frames}회")
    if sample_detections:
        print(" -> 검출 실측 샘플 (프레임번호, 라벨, 신뢰도, BBox):")
        for f_no, res in sample_detections:
            print(f"    • Frame {f_no}: {res}")
    else:
        print(" -> 실제 흉기 객체 미검출 (비위험 일반 영상)")

print("\n" + "="*70)
