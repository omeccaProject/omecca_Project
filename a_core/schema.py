from datetime import datetime, timezone


def _to_bbox_xywh(bbox):
    """[x1,y1,x2,y2] -> [x,y,w,h] 변환 (두 함수에서 중복되던 로직 분리)"""
    x1, y1, x2, y2 = bbox
    return [x1, y1, x2 - x1, y2 - y1]


def _now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def build_event_payload(cam_id, event, roi_id=None, track_id=None,
                         frame_ref_before=None, frame_ref_after=None):
    """낙하물(방치물) 이벤트 - 정지판별 거쳐서 생성"""
    return {
        "camId": cam_id,
        "trackId": track_id,
        "eventType": "DEBRIS",
        "objectClass": "OBJECT",
        "bbox": _to_bbox_xywh(event["bbox"]),
        "confidence": event.get("confidence"),
        "occurredAt": _now_iso(),
        "location": {
            "lat": None,       # 담당: 김준호(E). A는 채우지 않음
            "lng": None,
        },
        "isRegisteredTarget": False,
        "targetId": None,
        "roiId": roi_id,
        "meta": {
            "stationaryDurationSec": event["duration_sec"]
        },
        "frameRefBefore": frame_ref_before,
        "frameRefAfter": frame_ref_after
    }

def build_weapon_event_payload(cam_id, detection, frame_ref_before=None, frame_ref_after=None):
    """흉기 이벤트 - 탐지 즉시 생성 (정지판별 불필요)"""
    return {
        "camId": cam_id,
        "trackId": None,
        "eventType": "WEAPON",
        "objectClass": "OBJECT",
        "detectedClass": detection["class"],   # knife 또는 blunt_weapon
        "bbox": _to_bbox_xywh(detection["bbox"]),
        "confidence": detection["confidence"],
        "occurredAt": _now_iso(),
        "location": {                       # ← 중첩 객체로 변경
            "lat": None,                    # 담당: 김준호(E). A는 채우지 않음
            "lng": None,
        },
        "isRegisteredTarget": False,
        "targetId": None,
        "roiId": None,
        "meta": {
            "weaponType": detection["class"]
        },
        "frameRefBefore": frame_ref_before,
        "frameRefAfter": frame_ref_after
    }