import requests
import json
from datetime import datetime

API_URL = "http://localhost:8080/api/events"

def send_event(event_type, confidence, bbox, cam_id="CAM-01", meta=None):
    """
    event_type: "WANTED_PERSON" 또는 "WEAPON"
    confidence: float (0.0 ~ 1.0)
    bbox: [xmin, ymin, xmax, ymax]
    cam_id: 카메라 ID (테스트용 기본값, 나중에 실제 CCTV ID로 교체)
    meta: Dict (예: {"matchedDbId": "W001"} 또는 {"weaponType": "knife"})
    """
    payload = {
        "camId": cam_id,
        "trackId": None,
        "eventType": event_type,
        "objectClass": "PERSON" if event_type == "WANTED_PERSON" else "OBJECT",
        "bbox": bbox,
        "confidence": confidence,
        "occurredAt": datetime.utcnow().isoformat() + "Z",
        "location": None,
        "isRegisteredTarget": False,
        "targetId": None,
        "roiId": None,
        "meta": meta or {},
        "frameRefBefore": None,
        "frameRefAfter": None,
    }

    try:
        response = requests.post(API_URL, json=payload, timeout=0.5)
        if response.status_code == 201:
            print(f"[EVENT SENT] {event_type}: {meta}")
        else:
            print(f"[EVENT REJECTED {response.status_code}] {event_type}: {response.text}")
    except requests.exceptions.RequestException:
        print(f"[EVENT LOG (Server Offline)] {event_type}: {meta}")