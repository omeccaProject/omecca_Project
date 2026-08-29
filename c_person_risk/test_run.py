import argparse
import os
import sys
import time
import cv2
import torch
import numpy as np
from PIL import ImageFont, ImageDraw, Image

base_dir = os.path.dirname(os.path.abspath(__file__))
if base_dir not in sys.path:
    sys.path.append(base_dir)

from weapon_detect import WeaponDetector
from face_detect import FaceDetector
from event_publisher import send_event

COOLDOWN_SEC = 3.0
PKL_CHECK_INTERVAL = 1.0  # Hot-Reload 폴링 주기(초)

# [추가] cv2.putText는 한글을 지원하지 않아서 화면에 물음표(????)로 깨져 나온다
# (인식/이벤트 로직과는 무관한, 순수 "시연 화면 표시" 문제). PIL로 한글 폰트를
# 찾아서 그리는 방식으로 대체한다 - 서버마다 설치된 폰트가 다를 수 있어 여러
# 후보 경로를 순서대로 시도하고, 하나도 없으면 그냥 기본 폰트로 폴백한다
# (그래도 최소한 프로그램이 죽지는 않게).
_KOREAN_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/unfonts-core/UnDotum.ttf",
    "C:\\Windows\\Fonts\\malgun.ttf",  # 윈도우 노트북에서 돌릴 경우 대비
]
_font_cache = {}


def _get_korean_font(size=20):
    if size in _font_cache:
        return _font_cache[size]
    for path in _KOREAN_FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                font = ImageFont.truetype(path, size)
                _font_cache[size] = font
                return font
            except Exception:
                continue
    print("[경고] 한글 폰트를 찾지 못했습니다 - 화면 표시용 이름이 깨질 수 있습니다 "
          "(인식/이벤트 발행 자체에는 영향 없음). sudo apt install fonts-nanum 권장.")
    font = ImageFont.load_default()
    _font_cache[size] = font
    return font


def put_text_kr(frame, text, org, color_bgr, font_size=20):
    """한글이 섞인 텍스트를 프레임에 그린다. color_bgr은 기존 cv2 색상 순서(B,G,R)
    그대로 받아서 내부에서 RGB로 변환한다 - 호출부 수정을 최소화하기 위함."""
    font = _get_korean_font(font_size)
    pil_img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil_img)
    x, y = org
    draw.text((x, y - font_size), text, font=font, fill=(color_bgr[2], color_bgr[1], color_bgr[0]))
    return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)


def resize_for_display(frame, max_width=960):
    """화면 표시용으로만 축소. 탐지/좌표 계산은 이미 끝난 뒤라 정확도에 영향 없음"""
    h, w = frame.shape[:2]
    if w <= max_width:
        return frame
    scale = max_width / w
    return cv2.resize(frame, (max_width, int(h * scale)))


def clip_bbox_xyxy(bbox, w, h):
    """좌표 클리핑 (화면 밖 좌표 이탈 방어)"""
    if not bbox or len(bbox) != 4:
        return [0, 0, 0, 0]
    x1, y1, x2, y2 = bbox
    return [max(0, min(w, int(x1))), max(0, min(h, int(y1))),
            max(0, min(w, int(x2))), max(0, min(h, int(y2)))]


def is_point_in_bbox(point, bbox):
    """흉기 중심점이 사람 바운딩 박스 내부에 포함되는지 판정"""
    if not point or not bbox or len(bbox) != 4:
        return False
    px, py = point
    x1, y1, x2, y2 = bbox
    return (x1 <= px <= x2) and (y1 <= py <= y2)


def run_pipeline(video_source=0, conf_threshold=0.50, skip_frames=15,
                  cam_id='CAM_01', no_display=False, tolerance=0.48):
    print(f'[*] C파트 통합 파이프라인 가동 (Cam: {cam_id}, Conf: {conf_threshold}, '
          f'Skip: {skip_frames}, Tolerance: {tolerance}, Display: {not no_display})')

    weapon_det = WeaponDetector(conf_threshold=conf_threshold)
    face_det = FaceDetector(tolerance=tolerance)

    cap = cv2.VideoCapture(video_source)
    if not cap.isOpened():
        print(f'[ERROR] 비디오 소스를 열 수 없습니다: {video_source}')
        return

    frame_idx = 0
    cached_faces = []
    last_pkl_check = 0.0  # 마지막으로 pkl 변경 확인한 시각

    last_sent_wanted = {}
    last_sent_weapon = {}

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame_idx += 1
        h, w = frame.shape[:2]
        now = time.time()

        if now - last_pkl_check > PKL_CHECK_INTERVAL:
            face_det.check_and_reload()
            last_pkl_check = now

        weapons = weapon_det.detect_weapons(frame)

        if frame_idx % skip_frames == 0 or frame_idx == 1:
            cached_faces = face_det.detect_faces_with_person_crop(frame)

        # 3. 수배자 이벤트 처리 (WANTED_PERSON)
        for face in cached_faces:
            matched_id = face.get('matchedDbId')
            if matched_id is not None:
                p_bbox = face.get('personBbox')
                is_armed = False
                armed_weapon_type = None

                if p_bbox:
                    for w_obj in weapons:
                        w_box = w_obj['bbox']
                        w_center = ((w_box[0] + w_box[2]) / 2.0, (w_box[1] + w_box[3]) / 2.0)
                        if is_point_in_bbox(w_center, p_bbox):
                            is_armed = True
                            armed_weapon_type = w_obj['label']
                            break

                if p_bbox:
                    target_bbox = clip_bbox_xyxy(p_bbox, w, h)
                else:
                    loc = face['location']
                    target_bbox = clip_bbox_xyxy([loc[3], loc[0], loc[1], loc[2]], w, h)

                if now - last_sent_wanted.get(matched_id, 0) >= COOLDOWN_SEC:
                    meta = {
                        'matchedDbId': matched_id,
                        'faceMatchScore': face['faceMatchScore'],
                        'weaponType': armed_weapon_type,
                        'isArmed': is_armed
                    }
                    send_event(
                        event_type='WANTED_PERSON',
                        confidence=face['faceMatchScore'],
                        bbox=target_bbox,
                        cam_id=cam_id,
                        meta=meta,
                        frame=frame  # [추가] 이벤트 발생 순간 프레임을 캡처 이미지로 저장하기 위해 전달
                    )
                    last_sent_wanted[matched_id] = now

        # 4. 흉기 단독 이벤트 처리 (WEAPON)
        for w_obj in weapons:
            w_label = w_obj['label']
            if now - last_sent_weapon.get(w_label, 0) >= COOLDOWN_SEC:
                w_box = w_obj['bbox']
                w_center = ((w_box[0] + w_box[2]) / 2.0, (w_box[1] + w_box[3]) / 2.0)
                holder_face = None

                for face in cached_faces:
                    p_bbox = face.get('personBbox')
                    if p_bbox and is_point_in_bbox(w_center, p_bbox):
                        if face.get('matchedDbId') is not None:
                            holder_face = face
                            break

                meta = {
                    'matchedDbId': holder_face['matchedDbId'] if holder_face else None,
                    'faceMatchScore': holder_face['faceMatchScore'] if holder_face else None,
                    'weaponType': w_label,
                    'isArmed': True
                }
                send_event(
                    event_type='WEAPON',
                    confidence=w_obj['confidence'],
                    bbox=clip_bbox_xyxy(w_box, w, h),
                    cam_id=cam_id,
                    meta=meta,
                    frame=frame  # [추가] 이벤트 발생 순간 프레임을 캡처 이미지로 저장하기 위해 전달
                )
                last_sent_weapon[w_label] = now

        # 5. 시연 화면 렌더링
        if not no_display:
            for f in cached_faces:
                if f.get('matchedDbId') is not None:
                    loc = f['location']
                    t, r, b, l = loc[0], loc[1], loc[2], loc[3]
                    cv2.rectangle(frame, (l, t), (r, b), (0, 255, 0), 2)
                    frame = put_text_kr(frame, f"{f['name']} ({f['faceMatchScore']:.2f})",
                                        (l, max(20, t - 6)), (0, 255, 0), font_size=20)

                    if f.get('personBbox'):
                        px1, py1, px2, py2 = clip_bbox_xyxy(f['personBbox'], w, h)
                        cv2.rectangle(frame, (px1, py1), (px2, py2), (255, 200, 0), 1)

            for w_item in weapons:
                bx = clip_bbox_xyxy(w_item['bbox'], w, h)
                cv2.rectangle(frame, (bx[0], bx[1]), (bx[2], bx[3]), (0, 0, 255), 2)
                frame = put_text_kr(frame, f"{w_item['label']} {w_item['confidence']:.2f}",
                                    (bx[0], max(20, bx[1] - 6)), (0, 0, 255), font_size=20)

            display_frame = resize_for_display(frame, max_width=960)
            cv2.imshow(f"C-Part [{cam_id}]", display_frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    cap.release()
    if not no_display:
        cv2.destroyAllWindows()
    print(f'[*] 파이프라인 정상 종료 ({cam_id})')


def parse_args():
    parser = argparse.ArgumentParser(description="C파트(수배자/흉기) 실시간 감지 파이프라인")
    parser.add_argument("--video", default="c_person_risk/sample.mp4",
                         help="비디오 소스 경로 또는 URL (기본: sample.mp4)")
    parser.add_argument("--cam-id", default="CAM_01",
                         help="이벤트에 실어 보낼 카메라 ID")
    parser.add_argument("--conf-threshold", type=float, default=0.50,
                         help="흉기 탐지 confidence threshold (기본 0.50)")
    parser.add_argument("--skip-frames", type=int, default=15,
                         help="얼굴 인식 프레임 스킵 간격 (기본 15)")
    parser.add_argument("--tolerance", type=float, default=0.48,
                         help="얼굴 매칭 tolerance (기본 0.48)")
    parser.add_argument("--no-display", action="store_true",
                         help="화면 렌더링 없이 헤드리스로 실행 (camera_watcher.py 자동 실행용)")
    return parser.parse_args()


if __name__ == '__main__':
    if len(sys.argv) > 1 and not sys.argv[1].startswith("--"):
        run_pipeline(video_source=sys.argv[1], conf_threshold=0.50, skip_frames=15)
    else:
        args = parse_args()
        run_pipeline(
            video_source=args.video,
            conf_threshold=args.conf_threshold,
            skip_frames=args.skip_frames,
            cam_id=args.cam_id,
            no_display=args.no_display,
            tolerance=args.tolerance,
        )