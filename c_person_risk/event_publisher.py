import os
import time
import random
import requests
import json
import cv2
from datetime import datetime, timezone

CAPTURE_BASE_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "b_dashboard", "public", "captures"
)

AFTER_CAPTURE_DELAY_MIN_SEC = 3.0
AFTER_CAPTURE_DELAY_MAX_SEC = 5.0

API_KEY_HEADERS = {'Content-Type': 'application/json', 'X-API-Key': 'omecca-dev-key-2026'}

# [수정] "http://localhost:8080"을 하드코딩하지 않고, 환경변수로 override 가능하게
# 바꿨다 - test_run.py를 우분투 서버가 아닌 "다른 컴퓨터"(예: GPU가 더 빠른
# 팀원 노트북)에서 돌릴 때, 그 컴퓨터 입장에서 "localhost"는 자기 자신이라
# 우분투 서버(스프링/DB/대시보드가 실제로 떠 있는 곳)로 요청이 전혀 안 간다.
# 반드시 실제 서버의 IP나 도메인을 지정해야 한다.
#
# 사용법(다른 컴퓨터에서 실행할 때):
#   Windows(cmd):  set GATEWAY_URL=http://172.30.1.33:8080 && python test_run.py ...
#   Linux/Mac:     GATEWAY_URL=http://172.30.1.33:8080 python3 test_run.py ...
# 지정 안 하면 기존처럼 "이 컴퓨터 자기 자신"(localhost:8080)을 그대로 사용한다
# - 우분투 서버 위에서 직접 실행할 때는 지금처럼 아무것도 안 바꿔도 된다.
GATEWAY_BASE_URL = os.environ.get('GATEWAY_URL', 'http://localhost:8080')
EVENTS_ENDPOINT_DEFAULT = f'{GATEWAY_BASE_URL}/api/events'
DETECTIONS_ENDPOINT = f'{GATEWAY_BASE_URL}/api/cctv/detections'


def to_bbox_xywh(bbox):
    if not bbox or len(bbox) != 4:
        return [0, 0, 0, 0]
    x1, y1, x2, y2 = bbox
    return [int(x1), int(y1), max(0, int(x2 - x1)), max(0, int(y2 - y1))]


def save_capture_frame(frame, cam_id, tag):
    """[참고] 이 함수는 캡처 이미지를 '이 컴퓨터의' b_dashboard/public/captures/에
    저장한다. 다른 컴퓨터(팀원 노트북)에서 test_run.py를 돌리면, 캡처 사진이
    우분투 서버가 아니라 그 노트북 로컬 디스크에 저장되므로, 대시보드(우분투
    서버가 서빙)에서는 해당 사진을 못 찾아 깨진 이미지로 보일 수 있다.
    지금 단계(실시간 바운딩박스 스트리밍 검증)에서는 이 캡처 저장 자체가
    핵심이 아니므로 일단 그대로 두되, 이 한계는 팀에 공유가 필요하다."""
    if frame is None:
        return None
    try:
        os.makedirs(CAPTURE_BASE_DIR, exist_ok=True)
        filename = f"{cam_id}_{tag}_{int(time.time() * 1000)}.jpg"
        filepath = os.path.join(CAPTURE_BASE_DIR, filename)
        cv2.imwrite(filepath, frame)
        return f"captures/{filename}"
    except Exception as e:
        print(f"[캡처 저장 실패] {e}")
        return None


_last_detection_send_time = 0.0
DETECTIONS_MIN_INTERVAL_SEC = 0.0


def send_detections(cam_id, frame_width, frame_height, faces=None, weapons=None):
    """매 프레임 호출해서 현재 화면의 얼굴/흉기 박스를 실시간 스트리밍한다."""
    global _last_detection_send_time
    now = time.time()
    if DETECTIONS_MIN_INTERVAL_SEC and (now - _last_detection_send_time) < DETECTIONS_MIN_INTERVAL_SEC:
        return
    _last_detection_send_time = now

    detections = []
    for i, f in enumerate(faces or []):
        bbox = f.get("bbox")
        if not bbox or len(bbox) != 4:
            continue
        detections.append({
            "trackId": 1000 + i,
            "bbox": {"x1": float(bbox[0]), "y1": float(bbox[1]), "x2": float(bbox[2]), "y2": float(bbox[3])},
            "alert": bool(f.get("alert", False)),
        })
    for i, w in enumerate(weapons or []):
        bbox = w.get("bbox")
        if not bbox or len(bbox) != 4:
            continue
        detections.append({
            "trackId": 2000 + i,
            "bbox": {"x1": float(bbox[0]), "y1": float(bbox[1]), "x2": float(bbox[2]), "y2": float(bbox[3])},
            "alert": True,
        })

    payload = {
        "camId": cam_id,
        "frameWidth": frame_width,
        "frameHeight": frame_height,
        "detections": detections,
    }
    try:
        requests.post(DETECTIONS_ENDPOINT, json=payload, headers=API_KEY_HEADERS, timeout=0.3)
    except Exception:
        pass


class EventPublisher:
    def __init__(self, endpoint=None, cooldown_sec=3.0):
        # [수정] endpoint를 명시적으로 안 넘기면, 위에서 GATEWAY_URL 환경변수를
        # 반영한 기본값을 사용한다.
        self.endpoint = endpoint or EVENTS_ENDPOINT_DEFAULT
        self.cooldown_sec = cooldown_sec
        self.last_sent_times = {}
        self.pending_after_captures = []

    def _cooldown_key(self, event_type, cam_id, meta):
        matched_id = meta.get('matchedDbId') if meta else None
        weapon_type = meta.get('weaponType') if meta else None

        if event_type == 'WANTED_PERSON' and matched_id:
            return f"{event_type}_{cam_id}_{matched_id}"
        elif event_type == 'WEAPON' and weapon_type:
            return f"{event_type}_{cam_id}_{weapon_type}"
        else:
            return f"{event_type}_{cam_id}"

    def send_event(self, event_type, confidence=0.0, bbox=None, cam_id='CAM_01', meta=None, frame=None):
        now = time.time()
        if meta is None:
            meta = {}

        cooldown_key = self._cooldown_key(event_type, cam_id, meta)
        if cooldown_key in self.last_sent_times:
            if now - self.last_sent_times[cooldown_key] < self.cooldown_sec:
                return False

        xywh_bbox = to_bbox_xywh(bbox)
        before_ref = save_capture_frame(frame, cam_id, f"{event_type}_before")
        track_id = f"cpart-{cam_id}-{event_type}-{int(now * 1000)}"

        payload = {
            'camId': cam_id,
            'targetId': None,
            'trackId': track_id,
            'eventType': event_type,
            'objectClass': 'PERSON' if event_type == 'WANTED_PERSON' else 'OBJECT',
            'confidence': float(confidence),
            'bbox': xywh_bbox,
            'occurredAt': datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z'),
            'frameRefBefore': before_ref,
            'frameRefAfter': before_ref,
            'meta': {
                'matchedDbId': meta.get('matchedDbId'),
                'faceMatchScore': meta.get('faceMatchScore'),
                'weaponType': meta.get('weaponType'),
                'isArmed': bool(meta.get('isArmed', False))
            }
        }

        try:
            res = requests.post(self.endpoint, json=payload, headers=API_KEY_HEADERS, timeout=0.5)
            self.last_sent_times[cooldown_key] = now
            success = res.status_code in (200, 201)

            matched_id = payload['meta'].get('matchedDbId')
            is_armed = payload['meta'].get('isArmed', False)
            weapon_type = payload['meta'].get('weaponType')

            log_items = []
            if matched_id:
                log_items.append(f"Target:{matched_id}")
            log_items.append(f"isArmed:{is_armed}")
            if weapon_type:
                log_items.append(f"Weapon:{weapon_type}")
            if before_ref:
                log_items.append(f"Before:{before_ref}")
            details_str = " | ".join(log_items)

            tag = f"EVENT SENT {res.status_code}" if success else f"EVENT REJECTED {res.status_code}"
            print(f"[{tag}] {event_type} | {details_str}")

            if success:
                delay = random.uniform(AFTER_CAPTURE_DELAY_MIN_SEC, AFTER_CAPTURE_DELAY_MAX_SEC)
                self.pending_after_captures.append({
                    "due_at": now + delay,
                    "track_id": track_id,
                    "cam_id": cam_id,
                    "event_type": event_type,
                })

            return success
        except Exception as e:
            self.last_sent_times[cooldown_key] = now
            print(f"[EVENT FAILED] {event_type} | 게이트웨이 연결 실패({self.endpoint}): {e}")
            return False

    def service_pending_after_captures(self, current_frame):
        if current_frame is None or not self.pending_after_captures:
            return

        now = time.time()
        still_pending = []
        for item in self.pending_after_captures:
            if now < item["due_at"]:
                still_pending.append(item)
                continue

            after_ref = save_capture_frame(current_frame, item["cam_id"], f"{item['event_type']}_after")
            if after_ref is None:
                continue

            try:
                url = f"{self.endpoint}/by-track/{item['track_id']}/captures"
                res = requests.patch(url, json={"frameRefAfter": after_ref}, headers=API_KEY_HEADERS, timeout=0.5)
                if res.status_code == 200:
                    print(f"[AFTER CAPTURE UPDATED] trackId={item['track_id']} | {after_ref}")
                else:
                    print(f"[AFTER CAPTURE FAILED] trackId={item['track_id']} | status={res.status_code}")
            except Exception as e:
                print(f"[AFTER CAPTURE FAILED] trackId={item['track_id']} | {e}")

        self.pending_after_captures = still_pending


# [하위 호환용 글로벌 싱글톤 인스턴스 및 함수]
_default_publisher = EventPublisher()

def send_event(event_type, confidence=0.0, bbox=None, cam_id='CAM_01', meta=None, frame=None):
    return _default_publisher.send_event(
        event_type=event_type,
        confidence=confidence,
        bbox=bbox,
        cam_id=cam_id,
        meta=meta,
        frame=frame
    )

def service_pending_after_captures(current_frame):
    return _default_publisher.service_pending_after_captures(current_frame)