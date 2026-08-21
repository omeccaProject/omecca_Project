import os
import sys
import time
import json
import uuid
import argparse
from pathlib import Path

import cv2
import requests
from ultralytics import YOLO

# Windows 콘솔 기본 코드페이지(cp949)는 🚨/🔪 같은 이모지를 못 그려서 UnicodeEncodeError로
# 죽는다. camera_watcher.py가 실제 PowerShell 창에서 이 스크립트를 자식 프로세스로 띄울 때도
# 안전하도록 UTF-8로 강제 전환한다.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

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

OUTPUT_DIR = BASE_DIR / "outputs"          # a_core/outputs/
OUTPUT_DIR.mkdir(exist_ok=True)

# 사건 발생 전/후 캡처 이미지 저장 위치. b_gateway(ReportGenerationService)의
# report.generation.frame-base-dir 기본값(../b_dashboard/public)과, b_dashboard Vite
# 개발 서버가 public/을 사이트 루트로 서빙하는 것 둘 다를 동시에 만족시키려면 반드시
# b_dashboard/public/captures/ 아래에 저장해야 한다 (frameRefBefore/After에는
# "captures/<파일명>.jpg" 처럼 이 디렉토리 기준 상대경로만 실어 보낸다).
CAPTURES_DIR = PROJECT_ROOT / "b_dashboard" / "public" / "captures"
CAPTURES_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_VIDEO = PROJECT_ROOT / "data" / "videos" / "cone.mp4"
CAM_ID = "CCTV-014"

VEHICLE_CLASSES = {"car", "truck", "bus", "motorcycle"}

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


def compute_iou(box_a, box_b):
    """두 bbox([x1,y1,x2,y2])의 IoU 계산."""
    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b

    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)

    inter_w = max(0, inter_x2 - inter_x1)
    inter_h = max(0, inter_y2 - inter_y1)
    inter_area = inter_w * inter_h

    if inter_area == 0:
        return 0.0

    area_a = (ax2 - ax1) * (ay2 - ay1)
    area_b = (bx2 - bx1) * (by2 - by1)
    return inter_area / float(area_a + area_b - inter_area)

def detect(frame, conf_threshold=0.4, vehicle_overlap_threshold=0.15):
    """프레임 1장에 대해 전체 모델 추론 후 탐지 리스트 반환.
    낙하물 후보가 차량 bbox와 vehicle_overlap_threshold 이상 겹치면
    (= 차량에 붙어있는 타이어 등으로 판단) 결과에서 제외한다.
    """
    vehicle_boxes = []
    hazard_candidates = []

    for model in ALL_MODELS:
        results = model(frame, verbose=False)[0]
        for box in results.boxes:
            conf = float(box.conf[0])
            if conf < conf_threshold:
                continue
            cls_name = model.names[int(box.cls[0])]
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            bbox = [round(x1), round(y1), round(x2), round(y2)]

            if model is general_model and cls_name in VEHICLE_CLASSES:
                vehicle_boxes.append(bbox)
            else:
                hazard_candidates.append({
                    "class": cls_name,
                    "bbox": bbox,
                    "confidence": round(conf, 3),
                })

    detections = []
    for det in hazard_candidates:
        if det["class"] in DEBRIS_CLASSES:
            overlaps_vehicle = any(
                compute_iou(det["bbox"], vbox) >= vehicle_overlap_threshold
                for vbox in vehicle_boxes
            )
            if overlaps_vehicle:
                continue  # 차량에 붙은 타이어로 판단 → 버림
        detections.append(det)

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


def save_capture(frame, cam_id, tag):
    """frame(원본 BGR numpy 배열)을 CAPTURES_DIR에 JPEG로 저장하고, b_gateway/b_dashboard가
    바로 쓸 수 있는 "/captures/<파일명>.jpg" 형태의 경로를 반환한다.
    frame이 None이면(예: before_frame을 못 잡은 경우) 저장하지 않고 None을 반환한다.

    맨 앞에 "/"를 붙여 사이트 루트 기준 절대경로로 만든다 - 프론트(EventDetailModal,
    CctvGrid)가 지금 어떤 화면(라우트)에 떠 있든 상관없이 항상 같은 곳을 가리키게 하기
    위함이다("captures/..."처럼 슬래시 없는 상대경로는 브라우저가 현재 페이지 URL 기준으로
    풀어내기 때문에, 라우트 깊이에 따라 엉뚱한 위치를 가리킬 수 있었다).
    b_gateway 쪽 ReportGenerationService.java가 Path.of(frameBaseDir, ref)로 합칠 때도
    맨 앞 "/"는 그냥 무시되고 frameBaseDir 밑에 이어붙는 것으로 확인했다 - PDF 생성 경로는
    안 깨진다.
    실제로 저장이 실패하면(cv2.imwrite가 False를 반환) 존재하지 않는 파일을 가리키는
    경로를 보내는 걸 막기 위해 이 경우도 None으로 반환한다."""
    if frame is None:
        return None
    filename = f"{cam_id}_{tag}_{uuid.uuid4().hex[:8]}.jpg"
    ok = cv2.imwrite(str(CAPTURES_DIR / filename), frame)
    if not ok:
        print(f"  ⚠️  캡처 이미지 저장 실패: {filename}")
        return None
    return f"/captures/{filename}"


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
    parser.add_argument("--save", action="store_true",
                    help="탐지 결과 영상을 a_core/outputs/ 에 저장")
    parser.add_argument("--cam-id", default=CAM_ID,
                    help="이벤트에 실릴 cam_id. camera_watcher.py가 카메라별로 넘겨준다")
    args = parser.parse_args()

    cam_id = args.cam_id
    tracker = StationaryObjectTracker(threshold_sec=args.threshold)

    # 한 영상 안에 서로 다른 후보(bbox가 살짝씩 어긋나 IOU 매칭이 끊기면서 별개의
    # candidate로 잡히는 경우 - 실제로 도로 위 물체가 여러 개거나, 흔들림/각도 때문에
    # 같은 물체가 여러 후보로 쪼개지는 영상에서 자주 발생)가 각자 2초 임계값을 넘기면,
    # tracker는 그때마다 별개의 이벤트를 계속 반환한다 - 카메라 하나에 낙하물 이벤트가
    # 여러 건 연달아 쌓이는 원인이었다. "카메라 하나당 한 번이면 충분"이 이 프로젝트의
    # 요구사항이므로(camera_watcher.py의 has_fired_debris 로직과 동일한 취지), 이 프로세스
    # 실행 동안 낙하물 이벤트는 첫 건만 전송하고 이후 후보는 감지만 하고 전송은 건너뛴다.
    debris_alerted_this_run = False

    writer = None
    if args.save:
        save_path = OUTPUT_DIR / f"{Path(args.video).stem}_detected.mp4"

    for frame, idx in frame_generator(args.video, target_fps=args.fps):
        detections = detect(frame)
        now = time.time()

        # 1. 낙하물(방치물) 이벤트
        debris_candidates = [d for d in detections if d["class"] in DEBRIS_CLASSES]
        for event in tracker.update(debris_candidates, now, frame):
            if debris_alerted_this_run:
                print(f"  ⏭️  낙하물 이미 이 실행에서 한 번 전송됨 - {event['class']} 후보는 건너뜀 (카메라당 1건 정책)")
                continue
            debris_alerted_this_run = True
            # roiId는 b_gateway에서 Long(실제 roi 테이블 FK)이라, 문자열 placeholder를 넣으면
            # "Cannot deserialize value of type java.lang.Long"로 게이트웨이가 매번 400 거부한다.
            # 카메라별 ROI 등록 연동이 아직 없으므로 스키마 기본값(null)을 그대로 쓴다.
            # 사건 발생 전(before) = 후보가 처음 등록된 순간의 프레임(tracker가 저장해둠),
            # 사건 발생 후(after) = 지금(임계값 넘어서 이벤트가 확정된) 순간의 프레임.
            frame_ref_before = save_capture(event.get("before_frame"), cam_id, "before")
            frame_ref_after = save_capture(frame.copy(), cam_id, "after")
            payload = build_event_payload(
                cam_id, event,
                frame_ref_before=frame_ref_before,
                frame_ref_after=frame_ref_after,
            )

            print("🚨 [DEBRIS] 이벤트 전송:")
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            send_to_gateway(payload)

        # 2. 흉기 이벤트 - 정지판별 없이 탐지 즉시 발생하므로 "전/후"를 구분할 별도 프레임이
        # 없다 - 탐지된 바로 그 프레임을 전/후 양쪽에 그대로 사용한다.
        for det in detections:
            if det["class"] in WEAPON_CLASSES:
                weapon_frame_ref = save_capture(frame.copy(), cam_id, "weapon")
                payload = build_weapon_event_payload(
                    cam_id, det,
                    frame_ref_before=weapon_frame_ref,
                    frame_ref_after=weapon_frame_ref,
                )
                print("🔪 [WEAPON] 이벤트 전송:")
                print(json.dumps(payload, ensure_ascii=False, indent=2))
                send_to_gateway(payload)

        # 박스 그리기는 저장/화면표시 둘 다에 필요하므로 여기서 한 번만 수행
        frame = draw_detections(frame, detections)

        if args.save:
            if writer is None:
                h, w = frame.shape[:2]
                fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                writer = cv2.VideoWriter(str(save_path), fourcc, args.fps, (w, h))
            writer.write(frame)

        if not args.no_display:
            cv2.imshow("OMECCA - Module A", resize_for_display(frame))
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    if writer is not None:
        writer.release()
        print(f"[SAVE] 저장 완료: {save_path}")

    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()