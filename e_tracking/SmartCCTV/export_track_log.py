"""
export_track_log.py
==============================================
사전 분석 배치 스크립트 (GIS 박스 오버레이용)

anomaly_detection.py를 "import"해서 그 안의 탐지/추적/판정 함수를
그대로 재사용합니다. 새로운 알고리즘을 만들지 않습니다.
  - 탐지: ad.detect() (YOLO11m)
  - 추적: model.track()의 ByteTrack 결과 (box.id)
  - 궤적 갱신: ad.update_track()
  - 이상운전 판정: ad.evaluate_anomaly_rules() / ad.is_abnormal_active()
  - 번호판 표시: ad.get_vehicle_plate()
  - 이상운전 사유 문구: ad.WEAVING_REASON_KOR

이 스크립트가 하는 일
----------------------------------------------------
0805.mp4를 처음부터 끝까지 한 번 분석해서,
  - 프레임별 차량 박스 좌표 (x1,y1,x2,y2, track_id, alert 여부)
  - "이상운전 에피소드가 새로 시작된" 시각 목록(episodes)
을 web/data/anomaly-track-log.json 하나로 저장합니다.

이 스크립트가 하지 않는 일
----------------------------------------------------
  - 결과 영상(mp4)을 만들지 않습니다.
  - cv2.imshow 창을 띄우지 않습니다 (배치용이라 화면 표시가 필요 없음).
  - 새로운 탐지/추적/판정 로직을 만들지 않습니다.

왜 "사전 분석"인가?
----------------------------------------------------
브라우저 <video> 태그와 Python의 OpenCV는 완전히 다른 프로세스에서
같은 mp4를 각자 재생합니다. 둘을 프레임 단위로 실시간 동기화하려면
별도의 스트리밍 서버 + 정밀한 시간 동기화가 필요해서 훨씬 복잡하고
지연/오차가 생기기 쉽습니다.

대신 이 스크립트로 "0805.mp4에서 언제 어떤 차량이 어디에 있었는지"를
한 번만 계산해서 저장해두면, 브라우저는 영상 자체(0805.mp4)를 그대로
재생하면서 그 재생 시각(video.currentTime)에 맞는 박스 좌표를 JSON에서
찾아 canvas로 그리기만 하면 됩니다. 영상은 원본 그대로 재생되고, 사용자
입장에서는 "영상이 재생되는 동안 AI가 박스를 그려주는" 것처럼 보입니다.

0805.mp4가 바뀌지 않는 한 이 스크립트는 한 번만 실행하면 됩니다.

실행 방법
----------------------------------------------------
    python export_track_log.py
    (다른 영상/카메라를 분석하려면: python export_track_log.py --video videos/x.mp4 --output web/data/x.json --cam-id X)

(프로젝트 루트 SMARTCCTV/ 에서 실행한다고 가정합니다. web/data/ 가
 보이는 위치가 아니라면 OUTPUT_JSON 경로를 실제 위치에 맞게 바꿔주세요.)
"""

import argparse
import json

import cv2

import anomaly_detection as ad  # 기존 파일을 그대로 import해서 재사용 (수정하지 않음)

# --------------------------------------------------
# 설정
# --------------------------------------------------
VIDEO_PATH = "videos/0805.mp4"  # GIS의 H4642 CCTV에 연결된 영상과 반드시 동일해야 함
OUTPUT_JSON = "web/data/anomaly-track-log.json"
CAM_ID = "H4642"  # GIS의 TEST_VIDEO_OVERRIDES에 등록된 cam_id와 동일해야 함


def export(video_path: str = VIDEO_PATH, output_json: str = OUTPUT_JSON, cam_id: str = CAM_ID):
    model = ad.YOLO(ad.MODEL_PATH)
    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        raise FileNotFoundError(f"영상을 열 수 없습니다: {video_path}")

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0

    # HOLD_WARNING_SECONDS(초 단위)를 이 영상의 실제 fps 기준으로 환산
    # (anomaly_detection.py의 run()과 동일한 방식)
    ad.HOLD_WARNING_FRAMES = max(1, round(ad.HOLD_WARNING_SECONDS * fps))

    frames_out = []
    episodes = []
    frame_idx = 0

    print(f"분석 시작: {video_path} ({width}x{height}, {fps:.2f}fps)")

    while True:
        frame_idx += 1
        ret, frame = cap.read()
        if not ret:
            break

        results = ad.detect(model, frame)
        boxes = results[0].boxes
        boxes_out = []

        if boxes is not None:
            for box in boxes:
                if box.id is None:
                    continue

                x1, y1, x2, y2 = map(int, box.xyxy[0])
                center = ((x1 + x2) // 2, (y1 + y2) // 2)
                track_id = int(box.id[0])

                # ① 궤적 갱신 (기존 함수 그대로 호출)
                ad.update_track(track_id, center, frame_idx)

                # ② 이상운전 판정 (기존 함수 그대로 호출)
                #    handle_anomaly()와 동일한 순서: "새로 감지되었는가" -> hold 갱신 -> "지금 활성 상태인가"
                was_active_before = ad.is_abnormal_active(track_id, frame_idx)
                result = ad.evaluate_anomaly_rules(track_id, frame_idx)

                state = ad.get_or_create_track_state(track_id)
                if result is not None:
                    state.last_weaving_frame = frame_idx

                is_active = ad.is_abnormal_active(track_id, frame_idx)

                boxes_out.append(
                    {
                        "track_id": track_id,
                        "x1": x1,
                        "y1": y1,
                        "x2": x2,
                        "y2": y2,
                        "alert": is_active,
                    }
                )

                # ③ 새 에피소드 시작 = 방금까지 비활성이었는데 지금 막 새로 감지됨
                #    (anomaly_detection.py의 add_event_log() 호출 조건과 동일)
                if result is not None and not was_active_before:
                    episodes.append(
                        {
                            "t": round(frame_idx / fps, 3),
                            "track_id": track_id,
                            "plate": ad.get_vehicle_plate(track_id),
                            "reason": ad.WEAVING_REASON_KOR,
                        }
                    )
                    print(f"  [{frame_idx / fps:6.2f}s] 이상운전 에피소드 시작 - Track #{track_id}")

        frames_out.append({"t": round(frame_idx / fps, 3), "boxes": boxes_out})

        if frame_idx % 300 == 0:
            print(f"  ... {frame_idx}프레임 처리됨 ({frame_idx / fps:.1f}s)")

    cap.release()

    payload = {
        "cam_id": cam_id,
        "video": video_path,
        "fps": fps,
        "width": width,
        "height": height,
        "frame_count": frame_idx,
        "frames": frames_out,
        "episodes": episodes,
    }

    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)

    print(f"\n완료: 프레임 {len(frames_out)}개, 이상운전 에피소드 {len(episodes)}건")
    print(f"저장 위치: {output_json}")


if __name__ == "__main__":
    # 인자 없이 실행하면 기존과 완전히 동일하게 동작한다(0805.mp4/H4642 - 하위 호환 유지).
    # export_forza_track_logs.py가 Forza A/B/C/D를 각각 별도 프로세스로 이 스크립트를
    # 호출할 때는 --video/--output/--cam-id로 다른 영상을 지정한다.
    parser = argparse.ArgumentParser(description="영상 1개를 분석해 GIS 박스 오버레이용 track log JSON을 생성한다.")
    parser.add_argument("--video", default=VIDEO_PATH, help=f"분석할 영상 경로 (기본값: {VIDEO_PATH})")
    parser.add_argument("--output", default=OUTPUT_JSON, help=f"결과 JSON 저장 경로 (기본값: {OUTPUT_JSON})")
    parser.add_argument("--cam-id", default=CAM_ID, help=f"이 영상에 연결된 cam_id (기본값: {CAM_ID})")
    args = parser.parse_args()

    export(video_path=args.video, output_json=args.output, cam_id=args.cam_id)