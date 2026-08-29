import os
import time
import requests
import json
import cv2
from datetime import datetime, timezone

# [추가] 캡처 이미지 저장 위치. b_dashboard가 공개 정적 파일로 서빙하는 폴더
# 바로 아래 저장해야, ReportGenerationService의 frame-base-dir 설정
# (기본값 "../b_dashboard/public")과 그대로 맞아떨어져서 b_report가 같은 파일을
# 읽을 수 있다. 이 값이 바뀌면 b_gateway의 REPORT_FRAME_BASE_DIR도 같이
# 맞춰줘야 한다.
CAPTURE_BASE_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "b_dashboard", "public", "captures"
)


def to_bbox_xywh(bbox):
    if not bbox or len(bbox) != 4:
        return [0, 0, 0, 0]
    x1, y1, x2, y2 = bbox
    return [int(x1), int(y1), max(0, int(x2 - x1)), max(0, int(y2 - y1))]


def save_capture_frame(frame, cam_id, event_type):
    """이벤트 발생 순간의 프레임을 이미지로 저장하고, b_dashboard가 서빙 가능한
    상대경로("captures/파일명.jpg")를 반환한다. frame이 없으면 None을 반환하고,
    호출 쪽(send_event)은 이 경우 frameRefBefore/After 없이 이벤트만 발행한다
    (PDF 리포트는 나중에 "이미지 없음" 에러가 나겠지만, 이벤트 발행 자체는
    캡처 실패로 막히면 안 되므로 예외를 던지지 않고 조용히 넘어간다)."""
    if frame is None:
        return None
    try:
        os.makedirs(CAPTURE_BASE_DIR, exist_ok=True)
        filename = f"{cam_id}_{event_type}_{int(time.time() * 1000)}.jpg"
        filepath = os.path.join(CAPTURE_BASE_DIR, filename)
        cv2.imwrite(filepath, frame)
        return f"captures/{filename}"
    except Exception as e:
        print(f"[캡처 저장 실패] {e}")
        return None


class EventPublisher:
    def __init__(self, endpoint='http://localhost:8080/api/events', cooldown_sec=3.0):
        self.endpoint = endpoint
        self.cooldown_sec = cooldown_sec
        self.last_sent_times = {}

    def _cooldown_key(self, event_type, cam_id, meta):
        """
        쿨다운을 event_type 단위가 아니라, 대상(사람/흉기종류)별로
        세분화하기 위한 키 생성.
        - WANTED_PERSON: cam_id + matchedDbId 조합 (같은 카메라에서
          다른 사람이 잡히면 별개로 취급)
        - WEAPON: cam_id + weaponType 조합 (matchedDbId가 없을 수
          있어서 흉기 종류로 구분)
        """
        matched_id = meta.get('matchedDbId') if meta else None
        weapon_type = meta.get('weaponType') if meta else None

        if event_type == 'WANTED_PERSON' and matched_id:
            return f"{event_type}_{cam_id}_{matched_id}"
        elif event_type == 'WEAPON' and weapon_type:
            return f"{event_type}_{cam_id}_{weapon_type}"
        else:
            # matchedDbId/weaponType 둘 다 없는 예외 케이스는
            # 기존 방식(event_type 단위)으로 폴백
            return f"{event_type}_{cam_id}"

    def send_event(self, event_type, confidence=0.0, bbox=None, cam_id='CAM_01', meta=None, frame=None):
        now = time.time()
        if meta is None:
            meta = {}

        # 쿨다운 검사 - event_type이 아니라 대상별 세분화된 키로 확인
        cooldown_key = self._cooldown_key(event_type, cam_id, meta)
        if cooldown_key in self.last_sent_times:
            if now - self.last_sent_times[cooldown_key] < self.cooldown_sec:
                return False

        # 게이트웨이 규격 [x, y, w, h] 변환
        xywh_bbox = to_bbox_xywh(bbox)

        # [추가] before/after 이미지 캡처. 지금은 이벤트 발생 시점 프레임 하나를
        # before/after 둘 다에 동일하게 사용한다 - PDF 레이아웃이 "발생 전/후" 2컷을
        # 나란히 보여주는 구조라 완전히 비워두면 생성이 아예 막히므로, 정말 다른
        # 시점의 전/후 스냅샷이 필요해지면 프레임 버퍼(deque)로 N프레임 전 것을
        # 별도 저장하도록 확장하면 된다.
        frame_ref = save_capture_frame(frame, cam_id, event_type)

        payload = {
            'camId': cam_id,
            'targetId': None,
            'eventType': event_type,
            'objectClass': 'PERSON' if event_type == 'WANTED_PERSON' else 'OBJECT',
            'confidence': float(confidence),
            'bbox': xywh_bbox,
            'occurredAt': datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z'),
            'frameRefBefore': frame_ref,
            'frameRefAfter': frame_ref,
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
            if frame_ref:
                log_items.append(f"Capture:{frame_ref}")
            details_str = " | ".join(log_items)

            tag = f"EVENT SENT {res.status_code}" if success else f"EVENT REJECTED {res.status_code}"
            print(f"[{tag}] {event_type} | {details_str}")

            return success
        except Exception as e:
            self.last_sent_times[cooldown_key] = now
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