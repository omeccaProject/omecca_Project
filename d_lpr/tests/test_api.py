"""REST API / 통계 집계 테스트."""

import time

import pytest
from fastapi.testclient import TestClient

from app.api import stats as stats_mod
from app.core.schemas import RiskLevel, VehicleStatus, ViolationEvent, ViolationType


def make_event(vtype: ViolationType, plate: str = "12가3456", cam: str = "CAM-001",
               risk: RiskLevel = RiskLevel.NORMAL, ts: float = None) -> ViolationEvent:
    return ViolationEvent(
        violation_type=vtype, cam_id=cam, track_id=1,
        timestamp=ts or time.time(), plate_no=plate, plate_confidence=0.9,
        risk_level=risk, vehicle_status=VehicleStatus.REGISTERED,
        zone_id="INT-A", detail="테스트 이벤트",
    )


@pytest.fixture
def seeded(repo):
    repo.save_violation(make_event(ViolationType.RED_LIGHT))
    repo.save_violation(make_event(ViolationType.RED_LIGHT, cam="CAM-002"))
    repo.save_violation(make_event(ViolationType.ILLEGAL_UTURN))
    repo.save_violation(
        make_event(ViolationType.HIGH_RISK_VEHICLE, plate="33아3333", risk=RiskLevel.HIGH)
    )
    repo.log_plate_read("CAM-001", 1, "12가3456", "12가3456", 0.9, True, "mock", time.time())
    repo.log_plate_read("CAM-001", 2, "12가345", "12가345", 0.4, False, "mock", time.time())
    return repo


class TestStatsAggregation:
    def test_summary(self, seeded):
        s = stats_mod.summary(seeded)
        assert s["total_violations"] == 4
        assert s["red_light"] == 2
        assert s["illegal_uturn"] == 1
        assert s["high_risk_vehicle"] == 1
        assert s["high_risk"] == 1
        assert s["plate_reads"] == 2
        assert s["plate_valid_rate"] == 0.5

    def test_by_type_includes_zero_counts(self, repo):
        rows = stats_mod.by_type(repo)
        assert len(rows) == 3
        assert all(r["count"] == 0 for r in rows)

    def test_by_hour_has_24_buckets(self, seeded):
        rows = stats_mod.by_hour(seeded)
        assert len(rows) == 24
        assert sum(r["count"] for r in rows) == 4

    def test_by_camera(self, seeded):
        rows = stats_mod.by_camera(seeded)
        counts = {r["cam_id"]: r["count"] for r in rows}
        assert counts["CAM-001"] == 3 and counts["CAM-002"] == 1

    def test_by_risk(self, seeded):
        rows = {r["risk_level"]: r["count"] for r in stats_mod.by_risk(seeded)}
        assert rows["high"] == 1 and rows["normal"] == 3

    def test_full_payload_shape(self, seeded):
        d = stats_mod.full(seeded)
        assert set(d) == {"summary", "by_type", "by_camera", "by_hour", "by_day", "by_risk"}


@pytest.fixture
def client(seeded):
    from app.api.server import app

    with TestClient(app) as c:
        yield c


class TestEndpoints:
    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_dashboard_served(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert "위반" in r.text

    def test_list_violations(self, client):
        d = client.get("/api/violations").json()
        assert d["count"] == 4

    def test_filter_by_type(self, client):
        d = client.get("/api/violations", params={"type": "red_light"}).json()
        assert d["count"] == 2

    def test_filter_by_risk(self, client):
        d = client.get("/api/violations", params={"risk_level": "high"}).json()
        assert d["count"] == 1

    def test_filter_by_cam(self, client):
        d = client.get("/api/violations", params={"cam_id": "CAM-002"}).json()
        assert d["count"] == 1

    def test_violation_not_found(self, client):
        assert client.get("/api/violations/nonexistent").status_code == 404

    def test_stats_endpoint(self, client):
        d = client.get("/api/stats").json()
        assert d["summary"]["total_violations"] == 4

    def test_vehicle_lookup_registered(self, client):
        d = client.get("/api/vehicles/12가3456").json()
        assert d["matched"] and d["risk_level"] == "normal"

    def test_vehicle_lookup_wanted(self, client):
        d = client.get("/api/vehicles/33아3333").json()
        assert d["status"] == "wanted" and d["risk_level"] == "high"

    def test_vehicle_lookup_fuzzy(self, client):
        d = client.get("/api/vehicles/33아3334").json()
        assert d["matched"] and d["fuzzy"] and d["char_diff"] == 1

    def test_vehicle_lookup_unregistered(self, client):
        d = client.get("/api/vehicles/99하9999").json()
        assert not d["matched"] and d["risk_level"] == "high"

    def test_vehicle_list_filter(self, client):
        d = client.get("/api/vehicles", params={"status": "wanted"}).json()
        assert d["count"] == 1

    def test_zones_endpoint(self, client):
        d = client.get("/api/zones").json()
        cams = {c["cam_id"] for c in d["cameras"]}
        assert "CAM-001" in cams
        cam1 = [c for c in d["cameras"] if c["cam_id"] == "CAM-001"][0]
        assert any(l["line_id"] == "stop_A" for l in cam1["lines"])

    def test_websocket_receives_events(self, client):
        from app.core.bus import TOPIC_VIOLATION, bus

        with client.websocket_connect("/ws") as ws:
            bus.publish(TOPIC_VIOLATION, {"type": "red_light", "cam_id": "CAM-001"})
            msg = ws.receive_json()
            assert msg["topic"] == TOPIC_VIOLATION
            assert msg["data"]["type"] == "red_light"
