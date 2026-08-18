import os
import sys
import time
import cv2
import torch
import numpy as np

base_dir = os.path.dirname(os.path.abspath(__file__))
if base_dir not in sys.path:
    sys.path.append(base_dir)

from weapon_detect import WeaponDetector
from face_detect import FaceDetector
from event_publisher import send_event

COOLDOWN_SEC = 3.0

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

def run_pipeline(video_source=0, conf_threshold=0.50, skip_frames=15):
    print(f'[*] C파트 통합 파이프라인 가동 (Conf: {conf_threshold}, Skip: {skip_frames})')
    
    weapon_det = WeaponDetector(conf_threshold=conf_threshold)
    face_det = FaceDetector(tolerance=0.55)
    
    cap = cv2.VideoCapture(video_source)
    if not cap.isOpened():
        print(f'[ERROR] 비디오 소스를 열 수 없습니다: {video_source}')
        return

    frame_idx = 0
    cached_faces = []
    
    # 쿨다운 관리 딕셔너리 (인물 ID별 / 무기 라벨별)
    last_sent_wanted = {}
    last_sent_weapon = {}

    while True:
        ret, frame = cap.read()
        if not ret:
            break
            
        frame_idx += 1
        h, w = frame.shape[:2]
        now = time.time()
        
        # 1. 흉기 탐지 (실시간 GPU 추론)
        weapons = weapon_det.detect_weapons(frame)
        
        # 2. 얼굴 인식 (skip_frames 주기로 갱신)
        if frame_idx % skip_frames == 0 or frame_idx == 1:
            cached_faces = face_det.detect_faces_with_person_crop(frame)
            
        # 3. 수배자 이벤트 처리 (WANTED_PERSON)
        for face in cached_faces:
            matched_id = face.get('matchedDbId')
            if matched_id is not None:
                # personBbox 기반 개별 무장 판정
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
                
                # BBox 안전성: personBbox 없을 경우 얼굴 박스(location: t,r,b,l)를 fallback 좌표로 활용
                if p_bbox:
                    target_bbox = clip_bbox_xyxy(p_bbox, w, h)
                else:
                    loc = face['location']
                    target_bbox = clip_bbox_xyxy([loc[3], loc[0], loc[1], loc[2]], w, h)
                
                # 쿨다운 검사 후 전송
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
                        cam_id='CAM_01',
                        meta=meta
                    )
                    last_sent_wanted[matched_id] = now

        # 4. 흉기 단독 이벤트 처리 (WEAPON)
        for w_obj in weapons:
            w_label = w_obj['label']
            if now - last_sent_weapon.get(w_label, 0) >= COOLDOWN_SEC:
                # 흉기를 든 수배자가 있는지 역추적
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
                    cam_id='CAM_01',
                    meta=meta
                )
                last_sent_weapon[w_label] = now

        # 5. 시연 화면 렌더링 (수배자만 강조, Unknown 일반인 박스 숨김)
        for f in cached_faces:
            if f.get('matchedDbId') is not None: # Unknown 필터링 (수배자만 렌더링)
                loc = f['location'] # [t, r, b, l]
                t, r, b, l = loc[0], loc[1], loc[2], loc[3]
                cv2.rectangle(frame, (l, t), (r, b), (0, 255, 0), 2)
                cv2.putText(frame, f"{f['name']} ({f['faceMatchScore']:.2f})", (l, max(15, t - 10)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                
                if f.get('personBbox'):
                    px1, py1, px2, py2 = clip_bbox_xyxy(f['personBbox'], w, h)
                    cv2.rectangle(frame, (px1, py1), (px2, py2), (255, 200, 0), 1)

        # 흉기 렌더링
        for w_item in weapons:
            bx = clip_bbox_xyxy(w_item['bbox'], w, h)
            cv2.rectangle(frame, (bx[0], bx[1]), (bx[2], bx[3]), (0, 0, 255), 2)
            cv2.putText(frame, f"{w_item['label']} {w_item['confidence']:.2f}", (bx[0], max(15, bx[1] - 10)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

    cap.release()
    print('[*] 파이프라인 정상 종료')

if __name__ == '__main__':
    src = sys.argv[1] if len(sys.argv) > 1 else 'c_person_risk/sample.mp4'
    run_pipeline(video_source=src, conf_threshold=0.50, skip_frames=15)
