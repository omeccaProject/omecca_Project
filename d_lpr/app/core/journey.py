"""L010321(한강중학교) -> L010062(녹사평역) 같은 두 카메라 사이의 관제 이동 경로(Journey)를
Spring Boot(/api/cctv/journey)에 전달하는 아주 작은 헬퍼.

test_suspicious_driving.py 에도 같은 목적의 Journey 로직이 있지만, 그건 "지그재그 이상운전
패턴 + 고정 4캠 순서"를 기준으로 움직여서(번호판/track 매칭이 아님) 이번 번호판 매칭 데모에는
그대로 못 쓴다. 그 파일은 한 글자도 수정하지 않고, 여기에 아주 작게 새로 만든다. payload
형태(/api/cctv/journey가 기대하는 필드)는 그쪽과 동일하게 맞춰서 프론트
(useVehicleJourney.js / map.js의 RealVehicleJourneyListener)를 그대로 재사용할 수 있게 한다.

두 지점을 직선으로만 이으면 건물/공원을 뚫고 지나가는 것처럼 보인다. test_suspicious_driving.py
가 이미 OSRM(오픈소스 도로 라우팅)으로 실제 도로를 따라가는 좌표들을 받아오는 방식을 쓰고
있어서, 그 방식(get_road_segment 등)을 그대로 이식해서 여기서도 도로를 따라가게 한다.
"""
from __future__ import annotations

import logging
import math
import os
from typing import Optional

import requests

log = logging.getLogger("omeca.journey")

# 카메라 설치 위치(위경도). e_tracking/SmartCCTV/web/data/utic-cameras-seoul.json에서
# 실측값을 가져왔다. 새 카메라를 Journey에 추가하려면 여기에 한 줄만 추가하면 된다.
CAMERA_LOCATIONS = {
    "L010321": {"name": "한강중학교", "lat": 37.526369, "lng": 126.991889},
    "L010062": {"name": "녹사평역", "lat": 37.53396, "lng": 126.98769},
}

GATEWAY_API_KEY = os.environ.get("GATEWAY_API_KEY", "omecca-dev-key-2026")

OSRM_BASE_URL = "https://router.project-osrm.org/route/v1/driving"
_ROAD_CACHE: dict = {}


def haversine_meters(lat1, lng1, lat2, lng2):
    """두 좌표 사이의 실제 거리(m). test_suspicious_driving.py와 동일한 공식."""
    R = 6371000
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    )
    return 2 * R * math.asin(min(1, math.sqrt(a)))


def compute_bearing_deg(lat1, lng1, lat2, lng2):
    """두 좌표 사이의 진행 방위각(0~360). test_suspicious_driving.py와 동일한 공식."""
    lat1r, lat2r = math.radians(lat1), math.radians(lat2)
    dlng = math.radians(lng2 - lng1)
    y = math.sin(dlng) * math.cos(lat2r)
    x = math.cos(lat1r) * math.sin(lat2r) - math.sin(lat1r) * math.cos(lat2r) * math.cos(dlng)
    return round((math.degrees(math.atan2(y, x)) + 360) % 360)


def strip_start_uturn(points):
    """경로 시작점 부근의 U턴(되돌아오는 루프) 구간을 제거한다."""
    if len(points) < 4:
        return points

    start = points[0]
    SEARCH_LIMIT_METERS = 300
    LEFT_START_METERS = 80
    NEAR_START_METERS = 40

    cum_dist = 0.0
    left_start = False
    loop_back_idx = -1

    for i in range(1, len(points)):
        cum_dist += haversine_meters(points[i - 1][0], points[i - 1][1], points[i][0], points[i][1])
        if cum_dist > SEARCH_LIMIT_METERS:
            break

        dist_from_start = haversine_meters(start[0], start[1], points[i][0], points[i][1])
        if dist_from_start > LEFT_START_METERS:
            left_start = True
        elif left_start and dist_from_start <= NEAR_START_METERS:
            loop_back_idx = i

    if loop_back_idx > 0:
        return [start] + points[loop_back_idx + 1:]

    return points

# 새 함수 (strip_end_uturn 대신)
def _cut_at_first_approach(path, dest_lat, dest_lng, threshold_m=100.0):
    """경로를 따라가다가 목적지에 처음으로 threshold_m 이내로 가까워지는 지점에서 자른다.
    그 뒤로 OSRM 경로가 골목을 헤매든 루프를 돌든 전혀 상관없다 - 처음 근접한 순간
    이후는 전부 버리고 목적지로 바로 직선 연결한다. "되돌아옴 감지" 같은 대칭적
    휴리스틱보다 훨씬 단순하고 예측 가능해서 목적지 쪽 아티팩트에 더 안정적이다."""
    for idx, (lat, lng) in enumerate(path):
        if haversine_meters(lat, lng, dest_lat, dest_lng) <= threshold_m:
            log.info("Journey: 목적지 %.0fm 이내(경로 %d/%d번째 점)부터 직선으로 연결합니다.",
                     threshold_m, idx + 1, len(path))
            return path[:idx + 1] + [(dest_lat, dest_lng)]
    return path + [(dest_lat, dest_lng)]


    # 변경 후
def get_road_segment(from_loc: dict, to_loc: dict, cache: Optional[dict] = None) -> list:
    """두 지점 사이의 실제 도로 경로(위경도 리스트)를 OSRM에서 받아온다.
    실패하면(네트워크 문제 등) 직선 2점으로 대체한다 - 지도 표시 자체가 아예 안 되는
    것보다는 직선이라도 나오는 게 낫다.

    진입 방향(bearings)을 강제하지 않는다 - 강제하면 실제 도로 구조상 그 방향으로
    못 들어가는 경우 OSRM이 블록을 한 바퀴 돌아서 진입하는 경로를 만들어(루프 아티팩트)
    지도에 이상한 사각형 모양이 그려진다. 그냥 최단/최적 경로를 그대로 쓴다.
    """
    if cache is None:
        cache = _ROAD_CACHE

    key = (from_loc["lat"], from_loc["lng"], to_loc["lat"], to_loc["lng"])
    if key in cache:
        return cache[key]

    straight = [(from_loc["lat"], from_loc["lng"]), (to_loc["lat"], to_loc["lng"])]
    # 변경 후
    url = (
        f"{OSRM_BASE_URL}/{from_loc['lng']},{from_loc['lat']};{to_loc['lng']},{to_loc['lat']}"
        f"?overview=full&geometries=geojson&radiuses=20;20"
    )

    try:
        res = requests.get(url, timeout=5)
        res.raise_for_status()
        data = res.json()
        # 변경 후
        coords = data["routes"][0]["geometry"]["coordinates"]  # [[lng,lat], ...]
        path = [(lat, lng) for lng, lat in coords]
        path = strip_start_uturn(path)
        path = _cut_at_first_approach(path, to_loc["lat"], to_loc["lng"])
        cache[key] = path
        return path
    except Exception as e:
        log.warning("OSRM 도로 경로 조회 실패 - 직선으로 대체합니다: %s", e)
        cache[key] = straight
        return straight

    # 변경 후 (원래대로 — get_road_segment에 이미 있는 strip_start/end_uturn에 맡긴다)
def build_route_points(from_loc: dict, to_loc: dict) -> list:
    """send_journey_update()의 points 인자로 바로 넣을 수 있는 {lat,lng} 리스트를 만든다."""
    path = get_road_segment(from_loc, to_loc)
    return [{"lat": lat, "lng": lng} for lat, lng in path]

def send_journey_update(gateway_origin: str, active: bool, cam_id: Optional[str],
                         points: list) -> None:
    """VehicleJourneyController(/api/cctv/journey)로 여정 상태를 보낸다.

    실패해도(게이트웨이 미기동 등) 예외를 던지지 않는다 - 지도 표시 실패가 위반 감지
    자체를 막으면 안 된다(test_suspicious_driving.py의 send_journey_update와 같은 방침).
    """
    loc = CAMERA_LOCATIONS.get(cam_id) if active and cam_id else None
    payload = {
        "active": active,
        "currentCamId": cam_id,
        "currentCamName": loc["name"] if loc else None,
        "currentLat": loc["lat"] if loc else None,
        "currentLng": loc["lng"] if loc else None,
        "points": points,
    }
    url = gateway_origin.rstrip("/") + "/api/cctv/journey"
    headers = {"X-API-Key": GATEWAY_API_KEY, "Content-Type": "application/json"}
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=5)
        if not resp.ok:
            log.warning("Journey 전송 실패 | %s | %s", resp.status_code, resp.text[:200])
    except requests.RequestException as e:
        log.warning("Journey 전송 실패(게이트웨이 연결 안 됨) - 지도 표시에는 영향 없음: %s", e)


def fetch_latest_plate(gateway_origin: str, cam_id: str,
                        event_type: str = "SIGNAL_VIOLATION") -> str:
    """이 카메라에서 가장 최근에 확정된 위반 이벤트의 번호판을 게이트웨이에서 조회한다.
    다음 카메라(journey의 다음 지점)가 같은 번호판으로 강제 매칭할 때 쓴다.
    """
    url = gateway_origin.rstrip("/") + "/api/events"
    headers = {"X-API-Key": GATEWAY_API_KEY}
    params = {"camId": cam_id, "eventType": event_type, "size": 1}
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=5)
        resp.raise_for_status()
        content = resp.json().get("content") or []
        if not content:
            return ""
        meta = content[0].get("meta") or {}
        return meta.get("plateNumber") or ""
    except requests.RequestException as e:
        log.warning("이전 카메라(%s) 이벤트 조회 실패: %s", cam_id, e)
        return ""