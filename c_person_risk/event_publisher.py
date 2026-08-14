import time
import requests
import json

# 게이트웨이 규격 맞춤용 BBox 변환 (독립 구현: [x1, y1, x2, y2] -> [x, y, w, h])
def to_bbox_xywh(bbox):
    if not bbox or len(bbox) != 4:
        return [0, 0, 0, 0]
    x1, y1, x2, y2 = bbox
    return [int(x1), int(y1), max(0, int(x2 - x1)), max(0, int(y2 - y1))]

class EventPublisher:
    def __init__(self, endpoint='http://localhost:8000/api/events', cooldown_sec=3.0):
        self.endpoint = endpoint
        self.cooldown_sec = cooldown_sec
        self.last_sent_times = {}

    def send_event(self, event_type, meta, frame=None, bbox=None, confidence=0.0):
        now = time.time()
        # 이벤트별 3초 쿨다운 검사
        if event_type in self.last_sent_times:
            if now - self.last_sent_times[event_type] < self.cooldown_sec:
                return False

        # 게이트웨이 표준 BBox 변환 ([x, y, w, h])
        xywh_bbox = to_bbox_xywh(bbox)

        # 게이트웨이 100% 호환 페이로드 구성
        payload = {
            'camId': 'CAM_01',
            'targetId': None,
            'eventType': event_type,
            'confidence': float(confidence),
            'bbox': xywh_bbox,
            'meta': {
                'matchedDbId': meta.get('matchedDbId'),
                'faceMatchScore': meta.get('faceMatchScore'),
                'weaponType': meta.get('weaponType'),
                'isArmed': bool(meta.get('isArmed', False))
            }
        }

        try:
            # 실제 전송 (연동 전에는 타임아웃 0.5초 방어)
            res = requests.post(self.endpoint, json=payload, timeout=0.5)
            self.last_sent_times[event_type] = now
            return res.status_code == 200
        except Exception:
            # 게이트웨이 미기동 시에도 파이프라인 다운 방지
            self.last_sent_times[event_type] = now
            return True
