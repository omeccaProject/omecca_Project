"""경보 경로와 위반 기록 경로가 같은 답을 내는가.

실측으로 찾은 버그다. 영상(`123.mp4`)에서 OCR 이 번호판을 `15무4755` 로 읽었고
DB 에는 `17무4755` 가 있었다. 한 글자 차이다.

    경보      match()      → 유사 매칭으로 DB 를 찾음  → 등록 차량
    위반 기록 status_of()  → 정확 매칭만 하므로 못 찾음 → 미등록

같은 차량이 관제 화면에서는 '등록', 대시보드 위반 목록에서는 '미등록' 으로
나온다. 둘 다 우리 화면이라 발표 중에 바로 들통난다.

원인은 대조 논리가 두 군데 있었다는 것. 지금은 `resolve()` 한 곳으로 모았다.
이 파일은 그게 다시 갈라지지 않는지 지킨다.
"""

from __future__ import annotations

import pytest

from app.core.schemas import (
    PlateResult,
    RiskLevel,
    VehicleRecord,
    VehicleStatus,
)
from app.vehicle.matcher import VehicleMatcher
from app.vehicle.repository import VehicleRepository


@pytest.fixture()
def matcher(tmp_path):
    """실제 DB 를 건드리지 않도록 임시 SQLite 로 띄운다."""
    repo = VehicleRepository(driver="sqlite", sqlite_path=str(tmp_path / "t.db"))
    repo.clear()
    repo.upsert(VehicleRecord(plate_no="17무4755", owner_name="테스트",
                              status=VehicleStatus.REGISTERED))
    repo.upsert(VehicleRecord(plate_no="22사2222", owner_name="테스트",
                              status=VehicleStatus.STOLEN))
    return VehicleMatcher(repo=repo, log_reads=False)


def as_plate(text: str) -> PlateResult:
    return PlateResult(plate_no=text, raw_text=text, confidence=0.88,
                       cam_id="CAM-T", track_id=1, valid_format=True,
                       engine="test")


class TestTwoPathsAgree:
    """같은 번호를 두 입구로 넣으면 같은 답이 나와야 한다."""

    @pytest.mark.parametrize("plate", [
        "17무4755",   # 정확 매칭
        "15무4755",   # 1글자 오차 → 유사 매칭
        "99하9999",   # 미등록
        "22사2222",   # 도난
    ])
    def test_match_and_status_of_agree(self, matcher, plate):
        m = matcher.match(as_plate(plate))
        status, risk = matcher.status_of(plate)
        assert m.status == status, f"{plate}: 경보 {m.status} vs 기록 {status}"
        assert m.risk_level == risk


class TestFuzzyReachesBothPaths:
    def test_status_of_uses_fuzzy(self, matcher):
        """이게 버그의 핵심이었다 — status_of 가 유사 매칭을 안 했다."""
        status, risk = matcher.status_of("15무4755")
        assert status == VehicleStatus.REGISTERED
        assert risk != RiskLevel.HIGH

    def test_resolve_reports_matched_plate(self, matcher):
        m = matcher.resolve("15무4755")
        assert m.fuzzy is True
        assert m.matched_plate == "17무4755"

    def test_exact_match_is_not_marked_fuzzy(self, matcher):
        m = matcher.resolve("17무4755")
        assert m.fuzzy is False
        assert m.matched_plate == "17무4755"


class TestGuardsStillHold:
    """오검거를 막는 장치들이 살아 있는지 — 관대해지기만 하면 안 된다."""

    def test_two_char_error_is_not_matched(self, matcher):
        """2글자 이상 틀리면 남의 차다. 붙이면 안 된다."""
        assert matcher.resolve("15무4700").status == VehicleStatus.UNREGISTERED

    def test_invalid_format_skips_fuzzy(self, matcher):
        """번호판 형식이 아니면 유사 매칭을 시도조차 하지 않는다."""
        m = matcher.resolve("ANNA123", valid_format=False)
        assert m.matched is False
        assert m.fuzzy is False

    def test_tie_is_rejected(self, tmp_path):
        """동점 후보가 둘이면 채택하지 않는다 (누구인지 모르니까)."""
        repo = VehicleRepository(driver="sqlite", sqlite_path=str(tmp_path / "t2.db"))
        repo.clear()
        repo.upsert(VehicleRecord(plate_no="11가1111", status=VehicleStatus.REGISTERED))
        repo.upsert(VehicleRecord(plate_no="11가1112", status=VehicleStatus.REGISTERED))
        m = VehicleMatcher(repo=repo, log_reads=False)
        # '11가1110' 은 둘 다에서 1글자 차이 → 동점 → 미채택
        assert m.resolve("11가1110").status == VehicleStatus.UNREGISTERED


class TestStatsNotDoubleCounted:
    def test_count_false_does_not_increment(self, matcher):
        matcher.match(as_plate("17무4755"))
        before = dict(matcher.stats)
        matcher.resolve("17무4755", count=False)
        matcher.status_of("17무4755")
        assert matcher.stats == before
