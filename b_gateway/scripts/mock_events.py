#!/usr/bin/env python3
"""Mock 이벤트 생성기 — YOLO 연동 전 파이프라인 검증용.

공통 이벤트 스키마 규격서(원본 설계) 기준으로 페이로드를 생성한다.
- eventType: 원래 합의된 6종 (DEBRIS/UTURN_VIOLATION 등, FALLING_OBJECT/ILLEGAL_UTURN 아님)
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
    "SIGNAL_VIOLATION",
    "UTURN_VIOLATION",
]

# objectClass는 스키마 규격서 기준 3종만 허용. 세부 종류(흉기/트럭 등)는 meta에 담는다.
OBJECT_CLASSES = ["PERSON", "VEHICLE", "OBJECT"]

# meta.detailType 용 - 실제 탐지 세부 라벨 예시 (참고용, 팀 공통 규격은 아님)
DETAIL_TYPES = ["person", "knife", "car", "truck", "bag", "motorcycle"]

# [수정: "화면 중앙 알림 팝업 → '지도에서 실시간으로 보기' → CCTV 화면"이 mock 이벤트로는
# 동작하지 않던 문제] 예전엔 "CAM-01"~"CAM-04"라는 존재하지 않는 임시 라벨을 썼다 -
# UTIC CCTV 데이터셋(map.js의 uticCameraManager, 303건)에도 CCTV 관리(/api/cameras)에도
# 이 ID들은 없어서, 이벤트 자체는 떠도 지도가 카메라를 못 찾아 "CCTV 연동 대상이 아닙니다"
# 토스트만 뜨고 끝났다(사건 전/후 캡처도, CCTV 화면 자동전환도 안 됨).
# 대신 e_tracking/SmartCCTV/test_suspicious_driving.py의 데모 카메라 4대(CCTV-A~D)와
# 똑같은 실제 UTIC cam_id를 쓴다 - 이 4개는 CCTV 관리에도 등록돼 있고(연결됨) UTIC
# 데이터셋에도 있어서, mock 이벤트만으로도 지도 포커스 + CCTV 전환 + before/after
# 캡처(실제로는 mock 샘플 이미지) + PDF 리포트까지 끝까지 테스트할 수 있다.
CAM_IDS = ["L010111", "L010271", "L010128", "L010481"]

# 서울 시내 임의 좌표 범위 (테스트용)
LAT_RANGE = (37.45, 37.65)
LNG_RANGE = (126.90, 127.10)


def build_payload() -> dict:
    event_type = random.choice(EVENT_TYPES)
    sample_idx = random.randint(1, 3)
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
        # 예전엔 존재하지도 않는 임의 파일명(mock/before_{random}.jpg)을 만들어 보냈는데,
        # b_dashboard/public/mock/ 안에는 sample_before_1~3.jpg / sample_after_1~3.jpg
        # 3쌍만 실제로 존재한다. 실존하지 않는 경로를 보내면 대시보드에서 증거 이미지가
        # 깨져 보이는 건 물론이고, b_gateway의 리포트 자동생성(ReportTriggerService)도
        # "파일이 없다"며 조용히 스킵해버려서 데모/테스트가 안 된다. 그래서 실제 존재하는
        # 3쌍 중 하나를 순환해서 쓰도록 고쳤다 - 이러면 mock 데이터만으로도 b_report
        # 자동생성 파이프라인 전체를 끝까지 테스트할 수 있다.
        "frameRefBefore": f"mock/sample_before_{sample_idx}.jpg",
        "frameRefAfter": f"mock/sample_after_{sample_idx}.jpg",
    }


def post_event(base_url: str, payload: dict, api_key: str) -> None:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/events",
        data=data,
        # ApiKeyFilter가 /api/events를 포함한 대부분의 /api/** 경로를 X-API-Key로 막아뒀음
        # (가이드/이 스크립트가 먼저 작성되고 나서 나중에 추가된 필터라, 헤더 없이 보내면
        # 401 {"error":"UNAUTHORIZED", ...}로 거절당한다).
        headers={"Content-Type": "application/json", "X-API-Key": api_key},
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
    # b_gateway의 GATEWAY_API_KEY 환경변수와 같은 값이어야 함 (기본값: omecca-dev-key-2026,
    # application.yml의 gateway.api-key 기본값 및 b_dashboard/src/config.js와 동일).
    parser.add_argument("--api-key", default="omecca-dev-key-2026")
    args = parser.parse_args()

    for i in range(args.count):
        payload = build_payload()
        try:
            post_event(args.base_url, payload, args.api_key)
        except urllib.error.URLError as exc:
            print(f"요청 실패 ({i + 1}/{args.count}): {exc}")
            break
        if i < args.count - 1:
            time.sleep(args.interval)


if __name__ == "__main__":
    main()