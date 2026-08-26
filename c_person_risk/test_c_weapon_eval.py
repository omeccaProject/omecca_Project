import os
import time
import cv2
import numpy as np
from ultralytics import YOLO
from face_detect import FaceDetector
from weapon_detect import WeaponDetector

def get_weapon_detections(detector, frame):
    """WeaponDetector 내부 메서드명을 동적으로 찾아 안전하게 호출"""
    results = []
    try:
        if hasattr(detector, "detect_weapons"):
            raw = detector.detect_weapons(frame)
        elif hasattr(detector, "detect"):
            raw = detector.detect(frame)
        elif hasattr(detector, "predict"):
            raw = detector.predict(frame)
        elif hasattr(detector, "model"):
            # YOLO 모델 직접 호출 fallback
            res = detector.model(frame, conf=0.3, verbose=False)
            raw = []
            for r in res:
                for box in r.boxes:
                    cls_id = int(box.cls[0].item())
                    name = r.names.get(cls_id, "weapon")
                    conf = float(box.conf[0].item())
                    xyxy = list(map(int, box.xyxy[0].tolist()))
                    raw.append({"bbox": xyxy, "conf": conf, "class_name": name})
        else:
            raw = []

        # 딕셔너리 포맷 정규화
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict):
                    results.append(item)
                elif hasattr(item, "xyxy"):
                    # Ultralytics Box 객체인 경우
                    xyxy = list(map(int, item.xyxy[0].tolist()))
                    conf = float(item.conf[0].item())
                    results.append({"bbox": xyxy, "conf": conf, "class_name": "weapon"})
    except Exception as e:
        pass
    return results

def run_integrated_eval(video_path="1sample.mp4"):
    print(f"[*] 비디오 로드 및 모델 초기화: {video_path}")
    
    face_detector = FaceDetector(tolerance=0.48, model="hog")
    weapon_detector = WeaponDetector()
    
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"[ERROR] 비디오 파일을 열 수 없습니다: {video_path}")
        return

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps_in = cap.get(cv2.CAP_PROP_FPS)
    print(f"[*] 영상 스펙: {width}x{height} | {fps_in:.1f} FPS | 총 {total_frames} 프레임")

    print("\n" + "="*60)
    print("🚀 Step 2-1: Person-Crop + 흉기 탐지 실시간 통합 평가")
    print(" - 'q': 종료 | '스페이스바': 일시정지/재생")
    print("="*60 + "\n")

    frame_idx = 0
    prev_time = time.time()
    
    person_detections_count = 0
    weapon_detections_count = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            print("[INFO] 영상 재생이 완료되었습니다.")
            break

        frame_idx += 1
        start_t = time.time()

        # 1. 사람 검출 및 얼굴 매칭 (해상도 가드 내장)
        face_results = face_detector.detect_faces_with_person_crop(frame, person_conf=0.4)
        
        # 2. 흉기 탐지 (동적 래퍼 호출)
        weapon_results = get_weapon_detections(weapon_detector, frame)

        infer_time = (time.time() - start_t) * 1000

        person_detections_count += len(face_results)
        weapon_detections_count += len(weapon_results)

        # 3. 사람 전신 박스 시각화
        for res in face_results:
            px1, py1, px2, py2 = res["personBbox"]
            target_id = res["targetId"]
            name = res["name"]
            score = res["faceMatchScore"]

            cv2.rectangle(frame, (px1, py1), (px2, py2), (255, 200, 0), 2)
            
            if res.get("bbox"):
                fx1, fy1, fx2, fy2 = res["bbox"]
                if target_id is not None:
                    color = (0, 0, 255)
                    label = f"[WANTED] {name} ({score:.2f})"
                else:
                    color = (200, 100, 0)
                    label = "Unknown"
                cv2.rectangle(frame, (fx1, fy1), (fx2, fy2), color, 2)
                cv2.putText(frame, label, (fx1, fy1 - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 2)

        # 4. 흉기 박스 시각화
        for w_res in weapon_results:
            wx1, wy1, wx2, wy2 = w_res.get("bbox", [0, 0, 0, 0])
            w_name = w_res.get("class_name", "weapon")
            w_conf = w_res.get("conf", 0.0)
            w_label = f"WEAPON: {w_name} ({w_conf:.2f})"
            
            cv2.rectangle(frame, (wx1, wy1), (wx2, wy2), (0, 0, 255), 3)
            cv2.putText(frame, w_label, (wx1, max(15, wy1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 255), 2)

        # 5. OSD 메트릭 표시
        curr_time = time.time()
        fps = 1.0 / (curr_time - prev_time) if (curr_time - prev_time) > 0 else 0
        prev_time = curr_time

        osd = f"FPS: {fps:.1f} | Infer: {infer_time:.1f}ms | Person: {len(face_results)} | Weapon: {len(weapon_results)}"
        cv2.putText(frame, osd, (15, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

        cv2.imshow("Step 2-1 Integrated Evaluation", frame)

        if frame_idx % 30 == 0:
            print(f"[Frame {frame_idx:04d}/{total_frames}] FPS: {fps:.1f} | 사람: {len(face_results)}명 | 흉기: {len(weapon_results)}개 | 지연: {infer_time:.1f}ms")

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == 32:
            cv2.waitKey(0)

    cap.release()
    cv2.destroyAllWindows()
    
    print("\n" + "="*60)
    print("📋 [실측 요약 통계]")
    print(f" - 영상 파일: {video_path} ({width}x{height}, {fps_in:.1f} FPS)")
    print(f" - 총 처리 프레임: {frame_idx} / {total_frames}")
    print(f" - 누적 사람 검출(Person-Crop): {person_detections_count}회")
    print(f" - 누적 흉기 검출(Weapon): {weapon_detections_count}회")
    print("="*60)

if __name__ == "__main__":
    run_integrated_eval("1sample.mp4")