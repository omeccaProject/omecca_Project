#!/usr/bin/env python3
"""Mock 이벤트 생성기 — YOLO 연동 전 파이프라인 검증용.

공통 이벤트 스키마 규격서(원본 설계) 기준으로 페이로드를 생성한다.
- eventType: 원래 합의된 7종 (DEBRIS/UTURN_VIOLATION 등, FALLING_OBJECT/ILLEGAL_UTURN 아님)
- objectClass: PERSON/VEHICLE/OBJECT 3종만 (세부 종류는 meta로)
- location: {lat, lng} 좌표 객체 (문자열 아님)

사용:
  python scripts/mock_events.py
  python scripts/mock_events.py --count 20 --interval 1.5
"""

from __future__ import annotations

import argparse
import json
import random
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

# 원래 합의된 이벤트 스키마 규격서 기준 (팀 공통 규격)
EVENT_TYPES = [
    "WANTED_PERSON",
    "WEAPON",
    "UNREGISTERED_VEHICLE",
    "DEBRIS",
    "DUI_PATTERN",
    "SIGNAL_VIOLATION",
    "UTURN_VIOLATION",
]

# objectClass는 스키마 규격서 기준 3종만 허용. 세부 종류(흉기/트럭 등)는 meta에 담는다.
OBJECT_CLASSES = ["PERSON", "VEHICLE", "OBJECT"]

# meta.detailType 용 - 실제 탐지 세부 라벨 예시 (참고용, 팀 공통 규격은 아님)
DETAIL_TYPES = ["person", "knife", "car", "truck", "bag", "motorcycle"]

CAM_IDS = ["CAM-01", "CAM-02", "CAM-03", "CAM-04"]

# 서울 시내 임의 좌표 범위 (테스트용)
LAT_RANGE = (37.45, 37.65)
LNG_RANGE = (126.90, 127.10)


def build_payload() -> dict:
    event_type = random.choice(EVENT_TYPES)
    return {
        "camId": random.choice(CAM_IDS),
        "trackId": f"trk-{random.randint(1000, 9999)}",
        "eventType": event_type,
        "objectClass": random.choice(OBJECT_CLASSES),
        "bbox": [
            random.randint(50, 400),
            random.randint(50, 300),
            random.randint(40, 180),
            random.randint(40, 220),
        ],
        "confidence": round(random.uniform(0.55, 0.99), 3),
        "occurredAt": datetime.now(timezone.utc).astimezone().replace(tzinfo=None).isoformat(timespec="milliseconds"),
        "location": {
            "lat": round(random.uniform(*LAT_RANGE), 7),
            "lng": round(random.uniform(*LNG_RANGE), 7),
        },
        "isRegisteredTarget": random.choice([True, False]),
        "targetId": None,
        "roiId": None,
        "meta": {
            "source": "mock",
            "detailType": random.choice(DETAIL_TYPES),
        },
        "frameRefBefore": f"mock/before_{random.randint(1, 9999)}.jpg",
        "frameRefAfter": f"mock/after_{random.randint(1, 9999)}.jpg",
    }


def post_event(base_url: str, payload: dict) -> None:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/events",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = resp.read().decode("utf-8")
        print(f"[{resp.status}] {body}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Omecca mock event sender")
    parser.add_argument("--base-url", default="http://localhost:8080")
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--interval", type=float, default=1.0)
    args = parser.parse_args()

    for i in range(args.count):
        payload = build_payload()
        try:
            post_event(args.base_url, payload)
        except urllib.error.URLError as exc:
            print(f"요청 실패 ({i + 1}/{args.count}): {exc}")
            break
        if i < args.count - 1:
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
