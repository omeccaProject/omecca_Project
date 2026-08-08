from datetime import datetime, timezone


def build_event_payload(cam_id, event, roi_id=None, track_id=None):
    """낙하물(방치물) 이벤트 - 정지판별 거쳐서 생성"""
    x1, y1, x2, y2 = event["bbox"]
    bbox_xywh = [x1, y1, x2 - x1, y2 - y1]
    occurred_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

    return {
        "camId": cam_id,
        "trackId": track_id,
        "eventType": "DEBRIS",
        "objectClass": "OBJECT",
        "bbox": bbox_xywh,
        "confidence": event.get("confidence"),
        "occurredAt": occurred_at,
        "location": None,
        "isRegisteredTarget": False,
        "targetId": None,
        "roiId": roi_id,
        "meta": {
            "stationaryDurationSec": event["duration_sec"]
        },
        "frameRefBefore": None,
        "frameRefAfter": None
    }


def build_weapon_event_payload(cam_id, detection):
    """흉기 이벤트 - 탐지 즉시 생성 (정지판별 불필요)"""
    x1, y1, x2, y2 = detection["bbox"]
    bbox_xywh = [x1, y1, x2 - x1, y2 - y1]
    occurred_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

    return {
        "camId": cam_id,
        "trackId": None,
        "eventType": "WEAPON",
        "objectClass": "OBJECT",
        "bbox": bbox_xywh,
        "confidence": detection["confidence"],
        "occurredAt": occurred_at,
        "location": None,
        "isRegisteredTarget": False,
        "targetId": None,
        "roiId": None,
        "meta": {},
        "frameRefBefore": None,
        "frameRefAfter": None
    }