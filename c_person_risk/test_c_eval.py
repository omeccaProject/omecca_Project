import time
import cv2
import numpy as np
from face_detect import FaceDetector

def run_evaluation(source="my_sample.mp4"):
    print("[*] FaceDetector (HOG 고속 모드) 및 YOLOv8 모델 초기화 중...")
    # model="hog"로 설정하여 CPU에서도 실시간 속도 보장
    detector = FaceDetector(tolerance=0.48, model="hog")

    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        print(f"[ERROR] 비디오 소스를 열 수 없습니다: {source}")
        return

    print("\n" + "="*50)
    print("🚀 C파트 실시간 안면 인식 & 해상도 가드 성능 평가 시작")
    print(" - 종료하려면 영상 창에서 'q' 키를 누르세요.")
    print("="*50 + "\n")

    prev_time = time.time()
    frame_count = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            print("[INFO] 영상 재생이 완료되었습니다.")
            break

        # 고해상도 영상(4K/FHD) 리사이즈로 초고속 처리 (가로 960px 기준)
        h, w = frame.shape[:2]
        if w > 960:
            scale = 960 / w
            frame = cv2.resize(frame, (960, int(h * scale)))

        frame_count += 1
        start_infer = time.time()

        # 2단계 파이프라인 (Person YOLO -> 해상도 가드 -> Face Recognition)
        results = detector.detect_faces_with_person_crop(frame, person_conf=0.4)
        infer_time = (time.time() - start_infer) * 1000  # ms

        # 시각화 오버레이
        for res in results:
            name = res["name"]
            score = res["faceMatchScore"]
            target_id = res["targetId"]
            fx1, fy1, fx2, fy2 = res["bbox"]
            px1, py1, px2, py2 = res["personBbox"]

            cv2.rectangle(frame, (px1, py1), (px2, py2), (255, 200, 0), 1)

            if target_id is not None:
                color = (0, 0, 255)  # Red (수배자)
                label = f"[WANTED] {name} ({score:.2f})"
            else:
                color = (255, 120, 0)  # Cyan
                label = "Unknown"

            cv2.rectangle(frame, (fx1, fy1), (fx2, fy2), color, 2)
            cv2.rectangle(frame, (fx1, fy1 - 22), (fx1 + len(label)*9, fy1), color, -1)
            cv2.putText(frame, label, (fx1 + 3, fy1 - 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)

        # FPS 및 OSD
        curr_time = time.time()
        fps = 1.0 / (curr_time - prev_time) if (curr_time - prev_time) > 0 else 0
        prev_time = curr_time

        osd_text = f"FPS: {fps:.1f} | Infer: {infer_time:.1f}ms | Tracked: {len(results)}"
        cv2.putText(frame, osd_text, (15, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2, cv2.LINE_AA)

        cv2.imshow("C-Part AI CCTV Face Evaluation", frame)

        # 영상 속도에 맞춰 1ms 대기 (동영상일 경우 20ms 대기 시 정상 재생 속도)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()
    print("[INFO] 평가 세션 종료.")

if __name__ == "__main__":
    run_evaluation(source="my_sample.mp4")