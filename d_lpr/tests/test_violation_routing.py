"""violation 을 어디에 저장하는가 — SQLite 는 로컬, MySQL 은 게이트웨이.

ERD v1.0 결정 2번으로 `violation` 테이블은 b_gateway 의 `event` 로 흡수됐다.
그래서 `sql/schema.sql`(MySQL 용)에는 이 테이블이 없다.

그런데 `repository.py` 는 계속 `INSERT INTO violation` 을 하고 있었다. SQLite 는
자체 스키마로 테이블을 만들어서 티가 안 났지만, MySQL 로 붙이면 위반이 날 때마다
"table doesn't exist" 가 쌓인다. 예외를 삼키게 돼 있어 죽지는 않고 **로그만 조용히
못 쓰게 된다** — 통합해서 돌려보기 전에는 발견하기 어려운 종류다.

    SQLite (로컬 시연)  → 저장·조회 그대로. run_demo.py 와 /api/stats 가 쓴다
    MySQL  (팀 통합)    → 건드리지 않는다. GatewayClient 가 HTTP 로 보낸다
"""

from __future__ import annotations

import pytest

from app.core.schemas import RiskLevel, ViolationEvent, ViolationType, VehicleStatus
from app.vehicle.repository import VehicleRepository


def an_event(eid: str = "EV0000000000001") -> ViolationEvent:
    return ViolationEvent(
        violation_type=ViolationType.ILLEGAL_UTURN,
        cam_id="CAM-T", track_id=7, timestamp=1_760_000_000.0,
        plate_no="12가3456", plate_confidence=0.9,
        risk_level=RiskLevel.CAUTION, vehicle_status=VehicleStatus.REGISTERED,
        detail="테스트", event_id=eid,
    )


@pytest.fixture()
def sqlite_repo(tmp_path):
    return VehicleRepository(driver="sqlite", sqlite_path=str(tmp_path / "v.db"))


class TestSqliteKeepsWorking:
    """로컬 시연이 깨지면 안 된다 — 여기가 빈 화면이 되면 발표가 곤란해진다."""

    def test_saved_and_read_back(self, sqlite_repo):
        sqlite_repo.save_violation(an_event())
        rows = sqlite_repo.recent_violations()
        assert len(rows) == 1
        assert rows[0]["plate_no"] == "12가3456"

    def test_stats_counted(self, sqlite_repo):
        sqlite_repo.save_violation(an_event("EV0000000000001"))
        sqlite_repo.save_violation(an_event("EV0000000000002"))
        assert sqlite_repo.count_by_type()["illegal_uturn"] == 2
        assert sqlite_repo.count_by_cam()["CAM-T"] == 2
        assert sqlite_repo.count_by_risk()["caution"] == 2
        assert sum(sqlite_repo.count_by_hour().values()) == 2
        assert sum(sqlite_repo.count_by_day().values()) == 2


class TestMysqlSkipsQuietly:
    """MySQL 에서는 violation 을 건드리지 않는다.

    실제 MySQL 없이 확인하려고 driver 만 바꿔 끼운다. 쿼리가 나가면
    SQLite 연결에 `%s` 플레이스홀더가 가서 터지므로, '안 터진다' 는 것 자체가
    '쿼리를 안 보냈다' 는 증거가 된다.
    """

    def test_save_is_a_noop(self, sqlite_repo):
        sqlite_repo.driver = "mysql"
        sqlite_repo.save_violation(an_event())      # 예외 없이 지나가야 한다
        sqlite_repo.driver = "sqlite"
        assert sqlite_repo.recent_violations() == []

    def test_reads_return_empty(self, sqlite_repo):
        sqlite_repo.save_violation(an_event())      # SQLite 로 한 건 넣어 두고
        sqlite_repo.driver = "mysql"
        assert sqlite_repo.recent_violations() == []
        assert sqlite_repo.count_by_type() == {}
        assert sqlite_repo.count_by_cam() == {}
        assert sqlite_repo.count_by_risk() == {}
        assert sqlite_repo.count_by_hour() == {}
        assert sqlite_repo.count_by_day() == {}

    def test_warns_only_once(self, sqlite_repo, caplog):
        sqlite_repo.driver = "mysql"
        with caplog.at_level("INFO", logger="omeca.vehicle.repo"):
            for _ in range(5):
                sqlite_repo.save_violation(an_event())
        hits = [r for r in caplog.records if "b_gateway" in r.getMessage()]
        assert len(hits) == 1, "이벤트마다 찍으면 로그가 못 쓰게 된다"


class TestVehicleTableUnaffected:
    """vehicle / plate_read_log 는 우리 테이블이다. MySQL 에서도 그대로 쓴다."""

    def test_vehicle_still_queried_on_mysql(self, sqlite_repo):
        assert sqlite_repo.find("12가3456") is not None    # 시드에 있다
