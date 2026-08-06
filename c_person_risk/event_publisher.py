import requests
import json
from datetime import datetime

# 팀 백엔드 서버 주소 (필요시 IP/포트 변경)
API_URL = "http://localhost:8080/api/events"

def send_event(event_type, confidence, bbox, details):
    """
    event_type: "WANTED_PERSON" 또는 "WEAPON_DETECTED"
    confidence: float (0.0 ~ 1.0)
    bbox: [xmin, ymin, xmax, ymax]
    details: Dict (예: {"name": "홍길동"} 또는 {"weapon_type": "knife"})
    """
    payload = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "module": "c_person_risk",
        "event_type": event_type,
        "confidence": confidence,
        "bbox": bbox,
        "details": details
    }

    try:
        response = requests.post(API_URL, json=payload, timeout=0.5)
        if response.status_code == 200:
            print(f"[EVENT SENT] {event_type}: {details}")
    except requests.exceptions.RequestException:
        # 백엔드 미구동 시 로컬 로그만 출력 후 계속 진행
        print(f"[EVENT LOG (Server Offline)] {event_type}: {details}")