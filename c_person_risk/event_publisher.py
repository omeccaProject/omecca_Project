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


class EventPublisher:
    def __init__(self, endpoint='http://localhost:8080/api/events', cooldown_sec=3.0):
        self.endpoint = endpoint
        self.cooldown_sec = cooldown_sec
        self.last_sent_times = {}
        # [추가] "사건 발생 후" 사진을 나중에 찍기 위한 예약 목록.
        # 각 항목: {"due_at": 찍을 시각(epoch), "track_id": ..., "cam_id": ...}
        # test_run.py가 메인 루프에서 매 프레임 service_pending_after_captures()를
        # 불러줘야 실제로 소비된다 - 별도 스레드를 안 쓰는 이유는, 영상 프레임
        # 객체를 여러 스레드가 동시에 건드리면 경쟁 상태(race condition)가 생길
        # 위험이 있어서, "메인 루프가 매번 알아서 확인하는" 더 단순하고 안전한
        # 방식을 택했다.
        self.pending_after_captures = []

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

        xywh_bbox = to_bbox_xywh(bbox)

        # "사건 발생 전" 사진은 이벤트 발생 즉시(지금 이 프레임) 찍는다.
        before_ref = save_capture_frame(frame, cam_id, f"{event_type}_before")

        # [추가] 이 이벤트를 나중에 찾아서 "사건 발생 후" 사진을 업데이트할 수 있도록,
        # 매 이벤트마다 고유한 임시 trackId를 발급해 같이 보낸다. 게이트웨이에
        # 이미 있는 PATCH /api/events/by-track/{trackId}/captures API를 그대로
        # 재사용하기 위한 것 - 우리는 실제 다중 프레임 추적(tracking)을 하지 않지만,
        # "이 이벤트 하나를 나중에 다시 찾아 업데이트하는 용도"로만 trackId를 빌려 쓴다.
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
            'frameRefAfter': before_ref,  # 3~5초 뒤 실제 "발생 후" 사진으로 PATCH 업데이트됨
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

            # [추가] 전송 성공 시에만 "발생 후" 캡처를 예약한다 - 이벤트 자체가
            # 등록 안 됐으면 나중에 PATCH할 대상도 없기 때문.
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
        """메인 루프가 매 프레임 호출해야 하는 함수. 예약된 것 중 시간이 된 게
        있으면 지금 프레임으로 "발생 후" 사진을 찍어서 게이트웨이에 PATCH로
        업데이트한다. current_frame이 None이면 아무것도 안 하고 넘어간다."""
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
                continue  # 저장 실패 - 조용히 포기 (before 사진은 이미 있으니 리포트 생성 자체는 가능)

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
    """test_run.py 메인 루프에서 매 프레임 호출 - '발생 후' 사진 예약 처리."""
    return _default_publisher.service_pending_after_captures(current_frame)