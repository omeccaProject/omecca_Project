import requests
import json
import os
from datetime import datetime

API_URL = os.environ.get("GATEWAY_URL", "http://172.30.1.74:8080/api/events")
API_KEY = os.environ.get("GATEWAY_API_KEY", "omecca-dev-key-2026")

def send_event(event_type, confidence, bbox, cam_id="CAM-01", meta=None):
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
        response = requests.post(API_URL, json=payload, headers={"X-API-Key": API_KEY}, timeout=0.5)
        if response.status_code in (200, 201):
            print(f"[EVENT SENT {response.status_code}] {event_type}: {meta}")
        else:
            print(f"[EVENT REJECTED {response.status_code}] {event_type}: {response.text}")
    except requests.exceptions.RequestException:
        print(f"[EVENT LOG (Server Offline)] {event_type}: {meta}")
