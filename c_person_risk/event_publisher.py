import os
import time
import random
import requests
import json
import cv2
from datetime import datetime, timezone

# 캡처 이미지 저장 위치. b_dashboard가 공개 정적 파일로 서빙하는 폴더 바로 아래
# 저장해야, ReportGenerationService의 frame-base-dir 설정(기본값
# "../b_dashboard/public")과 맞아떨어져서 b_report가 같은 파일을 읽을 수 있다.
CAPTURE_BASE_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "b_dashboard", "public", "captures"
)

# "사건 발생 후" 사진을 몇 초 뒤에 찍을지 - 매번 정확히 같은 간격이면 부자연스러워
# 보일 수 있어 3~5초 사이 랜덤으로 잡는다.
AFTER_CAPTURE_DELAY_MIN_SEC = 3.0
AFTER_CAPTURE_DELAY_MAX_SEC = 5.0

# [추가] 실시간 바운딩박스 스트리밍 대상 (CctvDetectionController.java 참고).
# 기존 이벤트(/api/events, DB 저장용)와 완전히 별개의 채널 - 여기는 "지금 이 순간
# 화면 위치"만 매 프레임 쏘고 서버가 DB에 저장하지 않는다.
DETECTIONS_ENDPOINT = 'http://localhost:8080/api/cctv/detections'
API_KEY_HEADERS = {'Content-Type': 'application/json', 'X-API-Key': 'omecca-dev-key-2026'}


def to_bbox_xywh(bbox):
    if not bbox or len(bbox) != 4:
        return [0, 0, 0, 0]
    x1, y1, x2, y2 = bbox
    return [int(x1), int(y1), max(0, int(x2 - x1)), max(0, int(y2 - y1))]


def save_capture_frame(frame, cam_id, tag):
    """프레임을 이미지로 저장하고, b_dashboard가 서빙 가능한 상대경로
    ("captures/파일명.jpg")를 반환한다. frame이 없으면 None."""
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


# [추가] 실시간 바운딩박스 스트리밍. CctvDetectionController.DetectionBatch/Detection/Bbox
# 형식에 정확히 맞춘다 - trackId는 Integer 타입이라, 문자열이 아니라 정수를 넘겨야 한다.
# 우리는 이 프레임 안에서만 서로 안 겹치면 되는 "그 순간의 임시 번호"만 있으면 되고
# (useCctvDetections.js가 매 프레임 통째로 교체하는 방식이라 여러 프레임에 걸친
# 진짜 추적/트래킹 ID가 필요하지 않다), 그래서 얼굴은 1000번대, 흉기는 2000번대로
# 겹치지 않게 간단히 번호를 매긴다.
_last_detection_send_time = 0.0
DETECTIONS_MIN_INTERVAL_SEC = 0.0  # 필요하면 초당 전송 횟수를 제한할 수 있게 남겨둠(기본 무제한)


def send_detections(cam_id, frame_width, frame_height, faces=None, weapons=None):
    """매 프레임 호출해서 현재 화면의 얼굴/흉기 박스를 실시간 스트리밍한다.
    faces: [{"bbox": [x1,y1,x2,y2], "alert": bool}, ...] (얼굴 - 수배자만 보통 넘김)
    weapons: [{"bbox": [x1,y1,x2,y2]}, ...] (흉기 - 있으면 항상 alert=True로 취급)
    실패해도 예외를 던지지 않는다 - 이 스트리밍이 막혀도 이벤트 발행(send_event)이나
    감지 자체에는 전혀 영향이 없어야 하기 때문(화면 실시간 표시는 "덤" 기능).
    """
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
            "alert": True,  # 흉기는 항상 위험 표시(빨간 박스)로 취급
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
        # 실시간 스트리밍용이라 실패해도 조용히 넘어간다(로그도 안 남김 - 매 프레임
        # 실패할 경우 콘솔이 도배되는 걸 방지). 게이트웨이가 꺼져 있어도 감지/이벤트
        # 발행 자체는 계속 정상 동작해야 한다.
        pass


class EventPublisher:
    def __init__(self, endpoint='http://localhost:8080/api/events', cooldown_sec=3.0):
        self.endpoint = endpoint
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
            headers = {'Content-Type': 'application/json', 'X-API-Key': 'omecca-dev-key-2026'}
            res = requests.post(self.endpoint, json=payload, headers=headers, timeout=0.5)
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
            print(f"[EVENT FAILED] {event_type} | 게이트웨이(8080) 연결 실패: {e}")
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
                headers = {'Content-Type': 'application/json', 'X-API-Key': 'omecca-dev-key-2026'}
                res = requests.patch(url, json={"frameRefAfter": after_ref}, headers=headers, timeout=0.5)
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