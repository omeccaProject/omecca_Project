import sys
import time
import json
import argparse
from pathlib import Path

import cv2
import requests
from ultralytics import YOLO

# ── 경로 기준점 (실행 위치와 무관하게 동작) ──────────────────────
BASE_DIR = Path(__file__).resolve().parent          # a_core/
PROJECT_ROOT = BASE_DIR.parent                       # omecca_Project/
DETECTOR_DIR = PROJECT_ROOT / "a_detector"

sys.path.append(str(DETECTOR_DIR))

from hazard_classes import DEBRIS_CLASSES, WEAPON_CLASSES   # noqa: E402
from stationary_tracker import StationaryObjectTracker       # noqa: E402
from video_input import frame_generator                      # noqa: E402
from schema import build_event_payload, build_weapon_event_payload  # noqa: E402

# ── 모델 로드 ────────────────────────────────────────────────
HAZARD_MODEL_PATH = DETECTOR_DIR / "models" / "road_hazard.pt"

if not HAZARD_MODEL_PATH.exists():
    raise FileNotFoundError(
        f"낙하물 모델을 찾을 수 없습니다: {HAZARD_MODEL_PATH}\n"
        "저장소를 clone한 직후라면 a_detector/models/road_hazard.pt 가 "
        "포함되어 있는지 확인하세요."
    )

general_model = YOLO("yolo11n.pt")            # COCO 사전학습 (사람·차량 등)
hazard_model = YOLO(str(HAZARD_MODEL_PATH))   # 낙하물 파인튜닝 모델

ALL_MODELS = [general_model, hazard_model]

DEFAULT_VIDEO = PROJECT_ROOT / "data" / "videos" / "test_cone.mp4"
CAM_ID = "CCTV-014"


# b_gateway 전송 설정. b_gateway의 GATEWAY_API_KEY 환경변수와 같은 값이어야 함
# (기본값은 서로 일치하게 맞춰둠).
GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://localhost:8080") + "/api/events"
API_KEY = os.environ.get("GATEWAY_API_KEY", "omecca-dev-key-2026")


def send_to_gateway(payload):
    """이벤트를 b_gateway로 전송한다. 게이트웨이가 죽어있어도 탐지 루프는 계속 돌아야 하므로
    실패해도 예외를 밖으로 던지지 않고 로그만 남긴다."""
    try:
        resp = requests.post(GATEWAY_URL, json=payload, headers={"X-API-Key": API_KEY}, timeout=3)
        if resp.status_code == 201:
            print(f"  → 게이트웨이 전송 성공 ({resp.status_code})")
        else:
            print(f"  → 게이트웨이 전송 거부 ({resp.status_code}): {resp.text[:200]}")
    except requests.exceptions.RequestException as e:
        print(f"  → 게이트웨이 전송 실패(연결 안 됨): {e}")


def detect(frame, conf_threshold=0.4):
    """프레임 1장에 대해 전체 모델 추론 후 탐지 리스트 반환."""
    detections = []
    for model in ALL_MODELS:
        results = model(frame, verbose=False)[0]
        for box in results.boxes:
            conf = float(box.conf[0])
            if conf < conf_threshold:
                continue
            cls_name = model.names[int(box.cls[0])]
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            detections.append({
                "class": cls_name,
                "bbox": [round(x1), round(y1), round(x2), round(y2)],
                # ERD 규격: confidence DECIMAL(4,3), 0~1 범위
                "confidence": round(conf, 3),
            })
    return detections


def draw_detections(frame, detections):
    for det in detections:
        x1, y1, x2, y2 = det["bbox"]
        label = f'{det["class"]} {det["confidence"]}'
        if det["class"] in WEAPON_CLASSES:
            color = (0, 0, 255)      # 흉기 = 빨강
        elif det["class"] in DEBRIS_CLASSES:
            color = (0, 165, 255)    # 낙하물 = 주황
        else:
            color = (0, 255, 0)      # 일반 객체 = 초록
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        cv2.putText(frame, label, (x1, y1 - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
    return frame


def resize_for_display(frame, max_width=960):
    """화면 표시용으로만 축소. 탐지는 이미 끝난 뒤라 정확도에 영향 없음."""
    h, w = frame.shape[:2]
    if w <= max_width:
        return frame
    scale = max_width / w
    return cv2.resize(frame, (max_width, int(h * scale)))


def main():
    parser = argparse.ArgumentParser(description="모듈 A 낙하물·흉기 탐지 실행")
    parser.add_argument("--video", default=str(DEFAULT_VIDEO), help="입력 영상 경로")
    parser.add_argument("--fps", type=int, default=10, help="처리 FPS")
    parser.add_argument("--threshold", type=int, default=10,
                        help="방치물 판정 정지 지속시간(초)")
    parser.add_argument("--no-display", action="store_true",
                        help="화면 출력 없이 실행 (서버 연동용)")
    args = parser.parse_args()

    tracker = StationaryObjectTracker(threshold_sec=args.threshold)

    for frame, idx in frame_generator(args.video, target_fps=args.fps):
        detections = detect(frame)
        now = time.time()

        # 1. 낙하물(방치물) 이벤트 — 낙하물 클래스만 정지 판별에 투입
        debris_candidates = [d for d in detections if d["class"] in DEBRIS_CLASSES]
        for event in tracker.update(debris_candidates, now):
            payload = build_event_payload(CAM_ID, event, roi_id="roi_sidewalk_01")

            print("🚨 [DEBRIS] 이벤트 전송:")
            print("[DEBRIS] 이벤트 전송 예정:")
            print("[DEBRIS] 이벤트 전송 예정:")
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            send_to_gateway(payload)

        # 2. 흉기 이벤트 — 탐지 즉시 발생
        for det in detections:
            if det["class"] in WEAPON_CLASSES:
                payload = build_weapon_event_payload(CAM_ID, det)
                print("🔪 [WEAPON] 이벤트 전송:")
                print("[WEAPON] 이벤트 전송 예정:")
                print("[WEAPON] 이벤트 전송 예정:")
                print(json.dumps(payload, ensure_ascii=False, indent=2))
                send_to_gateway(payload)

        if not args.no_display:
            frame = draw_detections(frame, detections)
            cv2.imshow("OMECCA - Module A", resize_for_display(frame))
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()