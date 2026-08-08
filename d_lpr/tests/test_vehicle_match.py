"""차량 DB 대조 및 고위험 경보 테스트."""

import time

import pytest

from app.core.bus import TOPIC_ALERT, bus
from app.core.schemas import PlateResult, RiskLevel, VehicleStatus, ViolationType


def plate(no: str, conf: float = 0.9, valid: bool = True, track: int = 1) -> PlateResult:
    return PlateResult(
        plate_no=no, confidence=conf, valid_format=valid,
        cam_id="CAM-001", track_id=track, timestamp=time.time(),
    )


class TestRepository:
    def test_seeded(self, repo):
        assert len(repo.all_plates()) >= 10

    def test_find_exact(self, repo):
        rec = repo.find("12가3456")
        assert rec is not None and rec.status is VehicleStatus.REGISTERED

    def test_find_with_region_prefix(self, repo):
        assert repo.find("서울12가3456") is not None

    def test_find_missing(self, repo):
        assert repo.find("99하9999") is None

    def test_find_similar_one_char(self, repo):
        hit = repo.find_similar("12가3457")     # 마지막 자리 오인식
        assert hit is not None
        assert hit[0].plate_no == "12가3456" and hit[1] == 1

    def test_find_similar_rejects_two_char_diff(self, repo):
        assert repo.find_similar("12가9999") is None


class TestMatching:
    def test_registered_is_normal(self, matcher):
        m = matcher.match(plate("12가3456"))
        assert m.matched and m.risk_level is RiskLevel.NORMAL

    @pytest.mark.parametrize("no,status", [
        ("11바1111", VehicleStatus.FAKE_PLATE),
        ("22사2222", VehicleStatus.STOLEN),
        ("33아3333", VehicleStatus.WANTED),
    ])
    def test_high_risk_status(self, matcher, no, status):
        m = matcher.match(plate(no))
        assert m.status is status and m.risk_level is RiskLevel.HIGH

    def test_unregistered_is_high_risk(self, matcher):
        m = matcher.match(plate("99하9999"))
        assert not m.matched
        assert m.status is VehicleStatus.UNREGISTERED
        assert m.risk_level is RiskLevel.HIGH

    def test_caution_status(self, matcher):
        assert matcher.match(plate("55저5555")).risk_level is RiskLevel.CAUTION

    def test_fuzzy_match_recovers_ocr_error(self, matcher):
        m = matcher.match(plate("33아3334"))   # 수배차량 끝자리 오인식
        assert m.matched and m.fuzzy
        assert m.matched_plate == "33아3333"
        assert m.status is VehicleStatus.WANTED

    def test_fuzzy_skipped_for_invalid_format(self, matcher):
        m = matcher.match(plate("12A3456", valid=False))
        assert not m.matched


class TestAlerting:
    def test_alert_on_wanted(self, matcher):
        ev = matcher.check_and_alert(plate("33아3333"))
        assert ev is not None
        assert ev.violation_type is ViolationType.HIGH_RISK_VEHICLE
        assert ev.risk_level is RiskLevel.HIGH
        assert "수배" in ev.detail

    def test_no_alert_for_normal(self, matcher):
        assert matcher.check_and_alert(plate("12가3456")) is None

    def test_no_alert_for_caution(self, matcher):
        assert matcher.check_and_alert(plate("55저5555")) is None

    def test_low_confidence_suppressed(self, matcher):
        assert matcher.check_and_alert(plate("33아3333", conf=0.3)) is None

    def test_unregistered_needs_higher_confidence(self, matcher):
        # 미등록 판정은 기준이 더 엄격하다 (0.55 + 0.15)
        assert matcher.check_and_alert(plate("99하9999", conf=0.6)) is None
        assert matcher.check_and_alert(plate("99하9999", conf=0.85)) is not None

    def test_cooldown_prevents_spam(self, matcher):
        p1 = plate("22사2222")
        assert matcher.check_and_alert(p1) is not None
        p2 = plate("22사2222")
        p2.timestamp = p1.timestamp + 1.0
        assert matcher.check_and_alert(p2) is None      # 쿨다운 내
        p3 = plate("22사2222")
        p3.timestamp = p1.timestamp + 60.0
        assert matcher.check_and_alert(p3) is not None  # 쿨다운 경과

    def test_alert_published_to_bus(self, matcher):
        received = []
        bus.subscribe(lambda t, p: received.append((t, p)) if t == TOPIC_ALERT else None)
        matcher.check_and_alert(plate("11바1111"))
        assert any(t == TOPIC_ALERT for t, _ in received)

    def test_alert_persisted(self, matcher, repo):
        matcher.check_and_alert(plate("33아3333"))
        rows = repo.recent_violations(limit=10)
        assert len(rows) == 1
        assert rows[0]["violation_type"] == ViolationType.HIGH_RISK_VEHICLE.value
