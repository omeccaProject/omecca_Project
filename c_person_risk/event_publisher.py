import time
import requests
import json
from datetime import datetime, timezone


def to_bbox_xywh(bbox):
    if not bbox or len(bbox) != 4:
        return [0, 0, 0, 0]
    x1, y1, x2, y2 = bbox
    return [int(x1), int(y1), max(0, int(x2 - x1)), max(0, int(y2 - y1))]


class EventPublisher:
    def __init__(self, endpoint='http://localhost:8080/api/events', cooldown_sec=3.0):
        self.endpoint = endpoint
        self.cooldown_sec = cooldown_sec
        self.last_sent_times = {}

    def send_event(self, event_type, confidence=0.0, bbox=None, cam_id='CAM_01', meta=None, frame=None):
        now = time.time()
        if meta is None:
            meta = {}

        # 쿨다운 검사
        if event_type in self.last_sent_times:
            if now - self.last_sent_times[event_type] < self.cooldown_sec:
                return False

        # 게이트웨이 규격 [x, y, w, h] 변환
        xywh_bbox = to_bbox_xywh(bbox)

        payload = {
            'camId': cam_id,
            'targetId': None,
            'eventType': event_type,
            'objectClass': 'PERSON' if event_type == 'WANTED_PERSON' else 'OBJECT',
            'confidence': float(confidence),
            'bbox': xywh_bbox,
            'occurredAt': datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z'),
            'meta': {
                'matchedDbId': meta.get('matchedDbId'),
                'faceMatchScore': meta.get('faceMatchScore'),
                'weaponType': meta.get('weaponType'),
                'isArmed': bool(meta.get('isArmed', False))
            }
        }

        try:
            headers = {'Content-Type': 'application/json', 'X-API-Key': 'omecca-dev-key-2026'}
            res = requests.post(self.endpoint, json=payload, headers=headers, timeout=0.5)
            self.last_sent_times[event_type] = now
            success = res.status_code in (200, 201)

            # 실측용 콘솔 로깅 (isArmed E2E 검증용)
            matched_id = payload['meta'].get('matchedDbId')
            is_armed = payload['meta'].get('isArmed', False)
            weapon_type = payload['meta'].get('weaponType')

            log_items = []
            if matched_id:
                log_items.append(f"Target:{matched_id}")
            log_items.append(f"isArmed:{is_armed}")
            if weapon_type:
                log_items.append(f"Weapon:{weapon_type}")
            details_str = " | ".join(log_items)

            tag = f"EVENT SENT {res.status_code}" if success else f"EVENT REJECTED {res.status_code}"
            print(f"[{tag}] {event_type} | {details_str}")

            return success
        except Exception as e:
            self.last_sent_times[event_type] = now
            print(f"[EVENT FAILED] {event_type} | 게이트웨이(8080) 연결 실패: {e}")
            return False


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