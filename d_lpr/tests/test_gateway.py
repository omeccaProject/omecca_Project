"""b_gateway 공통 규격 변환 테스트.

규격 출처: shared/schemas/이벤트_스키마_규격서.md
게이트웨이는 잘못된 eventType/objectClass 를 400 으로 거부하므로,
보내기 전에 여기서 막는다.
"""

from __future__ import annotations

import time

import pytest

from app.core.gateway import (
    EVENT_TYPE, GatewayClient, _payload_from_bus, to_gateway_payload,
)
from app.core.schemas import (
    BBox, RiskLevel, VehicleStatus, ViolationEvent, ViolationType,
)

# 규격서 3.2 에 정의된 7종
ALLOWED_EVENT_TYPES = {
    "WANTED_PERSON", "WEAPON", "UNREGISTERED_VEHICLE", "DEBRIS",
    "DUI_PATTERN", "SIGNAL_VIOLATION", "UTURN_VIOLATION",
}
ALLOWED_OBJECT_CLASSES = {"PERSON", "VEHICLE", "OBJECT"}


def make_event(vtype=ViolationType.RED_LIGHT, **kw) -> ViolationEvent:
    base = dict(
        violation_type=vtype, cam_id="CAM-001", track_id=101,
        timestamp=time.mktime((2026, 8, 6, 10, 12, 33, 0, 0, -1)),
        plate_no="12가3456", plate_confidence=0.93,
        risk_level=RiskLevel.HIGH, vehicle_status=VehicleStatus.WANTED,
        zone_id="INT-A", detail="적색 신호 중 정지선 통과",
        evidence_frames=[1520, 1560], trajectory=[(760.0, 480.0), (760.0, 700.0)],
        location=(37.5326, 127.0246),
    )
    base.update(kw)
    return ViolationEvent(**base)


class TestEventType:
    @pytest.mark.parametrize("vtype,expected", [
        (ViolationType.HIGH_RISK_VEHICLE, "UNREGISTERED_VEHICLE"),
        (ViolationType.RED_LIGHT, "SIGNAL_VIOLATION"),
        (ViolationType.ILLEGAL_UTURN, "UTURN_VIOLATION"),
    ])
    def test_maps_to_spec_enum(self, vtype, expected):
        p = to_gateway_payload(make_event(vtype))
        assert p["eventType"] == expected

    def test_all_mapped_values_are_allowed(self):
        assert set(EVENT_TYPE.values()) <= ALLOWED_EVENT_TYPES

    def test_never_sends_internal_names(self):
        """규격서가 금지한 값(ILLEGAL_UTURN 등)을 보내면 400 이 난다."""
        for vtype in EVENT_TYPE:
            p = to_gateway_payload(make_event(vtype))
            assert p["eventType"] not in {"ILLEGAL_UTURN", "FALLING_OBJECT", "TRACKING"}
            assert p["eventType"] == p["eventType"].upper()

    def test_object_class_is_vehicle(self):
        p = to_gateway_payload(make_event())
        assert p["objectClass"] in ALLOWED_OBJECT_CLASSES
        assert p["objectClass"] == "VEHICLE"


class TestFieldFormat:
    def test_uses_camel_case_top_level(self):
        p = to_gateway_payload(make_event())
        for k in ("camId", "trackId", "eventType", "objectClass", "bbox",
                  "confidence", "occurredAt", "location", "isRegisteredTarget",
                  "targetId", "roiId", "meta", "frameRefBefore", "frameRefAfter"):
            assert k in p, f"규격 필드 누락: {k}"
        # 내부 snake_case 가 최상위로 새어나가면 안 된다
        assert not any("_" in k for k in p)

    def test_track_id_is_string(self):
        p = to_gateway_payload(make_event())
        assert isinstance(p["trackId"], str)
        assert p["trackId"] == "trk-101"

    def test_bbox_is_xywh_not_xyxy(self):
        """내부는 좌상단/우하단, 규격은 좌상단 + 폭/높이."""
        p = to_gateway_payload(make_event(), bbox=BBox(120, 80, 210, 220))
        assert p["bbox"] == [120, 80, 90, 140]

    def test_occurred_at_is_iso8601(self):
        from datetime import datetime

        p = to_gateway_payload(make_event())
        datetime.strptime(p["occurredAt"], "%Y-%m-%dT%H:%M:%S")   # 파싱되면 통과

    def test_location_is_object_not_array(self):
        p = to_gateway_payload(make_event())
        assert p["location"] == {"lat": 37.5326, "lng": 127.0246}

    def test_location_none_when_missing(self):
        assert to_gateway_payload(make_event(location=None))["location"] is None

    def test_confidence_in_range(self):
        p = to_gateway_payload(make_event())
        assert 0.0 <= p["confidence"] <= 1.0


class TestMeta:
    def test_our_fields_go_into_meta(self):
        """규격 4장: 임의로 새 최상위 필드를 추가하지 않는다."""
        p = to_gateway_payload(make_event())
        m = p["meta"]
        assert m["plateNumber"] == "12가3456"
        assert m["riskLevel"] == "high"
        assert m["vehicleStatus"] == "wanted"
        assert m["detail"]
        assert m["evidenceFrames"] == [1520, 1560]
        assert m["trajectory"]

    def test_spec_meta_keys_present(self):
        m = to_gateway_payload(make_event())["meta"]
        for k in ("plateNumber", "matchedDbId", "faceMatchScore",
                  "stationaryDurationSec", "trajectoryFeatures"):
            assert k in m

    def test_roi_id_always_null(self):
        # b_gateway 의 roi.id 와 대응 관계가 없으므로 숫자를 만들지 않는다.
        # 원본 zone_id 는 meta.roiName 으로 전달한다.
        for z in ("INT-12", "uturn_A", "uturn_B2", "center_uturn3"):
            p = to_gateway_payload(make_event(zone_id=z))
            assert p["roiId"] is None
            assert p["meta"]["roiName"] == z


class TestBusPayload:
    def test_same_shape_as_direct(self):
        ev = make_event()
        direct = to_gateway_payload(ev)
        via_bus = _payload_from_bus(ev.to_payload())
        assert set(direct) == set(via_bus)
        for k in ("camId", "trackId", "eventType", "objectClass", "occurredAt"):
            assert direct[k] == via_bus[k]

    def test_bus_event_type_mapped(self):
        ev = make_event(ViolationType.ILLEGAL_UTURN)
        assert _payload_from_bus(ev.to_payload())["eventType"] == "UTURN_VIOLATION"


class TestClient:
    def test_disabled_client_does_not_queue(self):
        c = GatewayClient(enabled=False)
        assert c.send(make_event()) is False

    def test_send_queues_payload(self):
        c = GatewayClient(enabled=True)
        assert c.send(make_event()) is True
        assert c._q.qsize() == 1

    def test_queue_full_drops_not_raises(self):
        c = GatewayClient(enabled=True, queue_size=1)
        c.send(make_event())
        assert c.send(make_event()) is False      # 예외 없이 폐기
        assert c.stats["dropped"] == 1

    def test_send_failure_does_not_raise(self):
        """게이트웨이가 죽어 있어도 우리 탐지는 계속 돌아야 한다."""
        c = GatewayClient(base_url="http://127.0.0.1:1", timeout=0.2)
        assert c.send_now({"camId": "X"}) is False
        assert c.stats["failed"] == 1
