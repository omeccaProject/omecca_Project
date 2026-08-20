"""MySQL 방언 검증.

팀 통합 서버는 MySQL 을 쓰지만 테스트 환경에 서버를 띄울 수 없으므로,
다음 두 가지를 정적으로 검증한다.

  1. sql/schema.sql, sql/seed.sql 이 MySQL 문법으로 파싱되는지
  2. repository 가 mysql 드라이버로 동작할 때 실제로 내보내는 모든 SQL 이
     MySQL 문법으로 유효하고, 플레이스홀더(%s) 개수가 파라미터 수와 맞는지

실제 서버 연결 테스트는 통합 환경에서 별도로 수행한다.
"""

from __future__ import annotations

import sys
import time
import types
from pathlib import Path

import pytest

sqlglot = pytest.importorskip("sqlglot", reason="sqlglot 미설치 - SQL 방언 검증 생략")

from app.core.schemas import (  # noqa: E402
    RiskLevel, VehicleRecord, VehicleStatus, ViolationEvent, ViolationType,
)

ROOT = Path(__file__).resolve().parents[1]


# ==========================================================================
# 1. DDL 파일 검증
# ==========================================================================
class TestSchemaFiles:
    @pytest.mark.parametrize("name", ["schema.sql", "seed.sql"])
    def test_parses_as_mysql(self, name):
        sql = (ROOT / "sql" / name).read_text(encoding="utf-8")
        stmts = [s for s in sqlglot.parse(sql, dialect="mysql") if s]
        assert stmts, f"{name}: 구문이 하나도 파싱되지 않았습니다"

    def test_expected_tables_defined(self):
        from sqlglot import exp

        sql = (ROOT / "sql" / "schema.sql").read_text(encoding="utf-8")
        tables = {
            s.this.this.name
            for s in sqlglot.parse(sql, dialect="mysql")
            if isinstance(s, exp.Create) and s.args.get("kind") == "TABLE"
        }
        # violation 은 ERD v1.0 결정 2번으로 event 로 흡수됐다.
        # repository.py 가 자체 DDL 로 로컬 저장소(SQLite/MySQL)에만 만든다.
        assert {"vehicle", "plate_read_log"} <= tables
        assert "violation" not in tables

    def test_seed_plates_are_valid_format(self):
        """시드에 실재하지 않는 번호판이 섞이면 대조 테스트가 무의미해진다."""
        from app.lpr import plate_format as pf
        from app.vehicle.repository import SEED_VEHICLES

        invalid = [r[0] for r in SEED_VEHICLES if not pf.is_valid(r[0])]
        assert not invalid, f"유효하지 않은 번호판: {invalid}"

    def test_seed_matches_sql_file(self):
        """repository 의 시드와 seed.sql 이 어긋나면 환경별로 결과가 달라진다."""
        from app.vehicle.repository import SEED_VEHICLES

        sql = (ROOT / "sql" / "seed.sql").read_text(encoding="utf-8")
        for row in SEED_VEHICLES:
            assert f"'{row[0]}'" in sql, f"seed.sql 에 {row[0]} 누락"

    def test_violation_has_no_fk_to_vehicle(self):
        """미등록 차량도 기록해야 하므로 vehicle 로의 FK 가 있으면 안 된다.

        violation 테이블은 sql/schema.sql 에서 빠지고 repository.py 의
        자체 DDL 로만 만들어지므로, 검사 대상도 그쪽으로 옮긴다.
        """
        src = (ROOT / "app" / "vehicle" / "repository.py").read_text(encoding="utf-8")
        body = src.split("CREATE TABLE IF NOT EXISTS violation")[1].split(")\"\"\"")[0]
        assert "FOREIGN KEY" not in body.upper()


# ==========================================================================
# 2. 런타임 SQL 검증 (pymysql 대역)
# ==========================================================================
class RecordingCursor:
    """실행되는 SQL 을 모두 검증하고 기록하는 커서 대역."""

    def __init__(self, log: list):
        self.log = log
        self.description = None
        self.rowcount = 0

    def execute(self, sql, params=()):
        params = params or ()
        # MySQL 문법으로 파싱되는지 확인.
        # sqlglot 은 %s 를 나머지 연산자로 해석하므로 리터럴로 치환한 뒤 검사한다.
        probe = sql.replace("%s", "1")
        try:
            sqlglot.parse_one(probe, dialect="mysql")
        except Exception as e:  # pragma: no cover - 실패 시 메시지 확인용
            raise AssertionError(f"MySQL 문법 오류: {sql!r}\n{e}") from e
        # 플레이스홀더와 파라미터 개수가 맞는지
        assert sql.count("%s") == len(params), (
            f"플레이스홀더 {sql.count('%s')}개 / 파라미터 {len(params)}개 불일치: {sql!r}"
        )
        assert "?" not in sql, f"sqlite 플레이스홀더가 남아 있습니다: {sql!r}"
        self.log.append((sql, params))

    def fetchall(self):
        return []

    def close(self):
        pass


class FakeConnection:
    def __init__(self):
        self.log: list = []

    def cursor(self):
        return RecordingCursor(self.log)

    def commit(self):
        pass

    def close(self):
        pass


@pytest.fixture
def mysql_repo(monkeypatch):
    """pymysql 대역을 주입해 mysql 드라이버 경로로 동작하는 저장소."""
    conn = FakeConnection()
    fake = types.ModuleType("pymysql")
    fake.connect = lambda **kwargs: conn          # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "pymysql", fake)

    from app.vehicle.repository import VehicleRepository

    repo = VehicleRepository(driver="mysql")
    assert repo.driver == "mysql", "pymysql 이 있으면 sqlite 로 폴백하면 안 됩니다"
    return repo, conn


def make_event() -> ViolationEvent:
    return ViolationEvent(
        violation_type=ViolationType.RED_LIGHT, cam_id="CAM-001", track_id=7,
        timestamp=time.time(), plate_no="12가3456", plate_confidence=0.91,
        risk_level=RiskLevel.NORMAL, vehicle_status=VehicleStatus.REGISTERED,
        zone_id="INT-A", detail="테스트", location=(37.5665, 126.978),
    )


class TestRuntimeSQL:
    def test_uses_percent_placeholder(self, mysql_repo):
        repo, conn = mysql_repo
        repo.find("12가3456")
        sql, params = conn.log[-1]
        assert "%s" in sql and len(params) == 1

    def test_all_read_queries_valid(self, mysql_repo):
        repo, conn = mysql_repo
        repo.find("12가3456")
        repo.find_similar("12가3457")
        repo.list_vehicles()
        repo.list_vehicles(status="wanted")
        repo.all_plates()
        assert len(conn.log) >= 5

    def test_all_aggregate_queries_valid(self, mysql_repo):
        repo, conn = mysql_repo
        repo.plate_read_summary()
        assert len(conn.log) == 1

    def test_write_queries_valid(self, mysql_repo):
        repo, conn = mysql_repo
        repo.log_plate_read("CAM-001", 1, "12가3456", "12가3456",
                            0.9, True, "easyocr", time.time())
        repo.upsert(VehicleRecord(plate_no="99하9999", status=VehicleStatus.WANTED))
        repo.clear()
        assert len(conn.log) >= 3


class TestViolationNotOnMysql:
    """MySQL 에서는 violation 쿼리가 **한 줄도 나가면 안 된다.**

    ERD v1.0 결정 2번으로 violation 은 b_gateway 의 event 로 흡수됐고
    `sql/schema.sql` 에서도 빠졌다. 그런데 repository 는 계속 INSERT 를 하고
    있었다 — SQLite 는 자체 스키마로 테이블을 만들어서 티가 안 났고, MySQL 로
    붙여야만 "table doesn't exist" 가 이벤트마다 쌓인다. 예외를 삼키게 돼 있어
    **죽지도 않고 로그만 조용히 못 쓰게 되는** 종류의 문제다.

    아래 테스트가 그 회귀를 막는다. 전송은 GatewayClient 가 HTTP 로 한다
    (`run_uturn.py --gateway http://localhost:8080`).
    """

    def test_save_emits_nothing(self, mysql_repo):
        repo, conn = mysql_repo
        before = len(conn.log)
        repo.save_violation(make_event())
        assert len(conn.log) == before

    def test_reads_emit_nothing(self, mysql_repo):
        repo, conn = mysql_repo
        before = len(conn.log)
        assert repo.recent_violations(limit=10) == []
        assert repo.recent_violations(limit=5, violation_type="red_light",
                                      cam_id="CAM-001") == []
        assert repo.count_by_type() == {}
        assert repo.count_by_cam() == {}
        assert repo.count_by_risk() == {}
        assert repo.count_by_hour() == {}
        assert repo.count_by_day(14) == {}
        assert len(conn.log) == before

    def test_no_violation_sql_anywhere(self, mysql_repo):
        """혹시라도 다른 경로로 새어 나가는지 전수 확인."""
        repo, conn = mysql_repo
        repo.save_violation(make_event())
        repo.recent_violations()
        repo.count_by_type()
        repo.plate_read_summary()
        repo.find("12가3456")
        leaked = [s for s, _ in conn.log if "violation" in s.lower()]
        assert leaked == [], f"MySQL 로 violation 쿼리가 나갔습니다: {leaked}"


class TestViolationStillLocalOnSqlite:
    """반대로 SQLite 에서는 그대로 동작해야 한다 — 로컬 시연이 여기에 달려 있다."""

    def test_sqlite_keeps_filters(self, tmp_path):
        from app.vehicle.repository import VehicleRepository
        repo = VehicleRepository(driver="sqlite", sqlite_path=str(tmp_path / "d.db"))
        repo.save_violation(make_event())
        assert len(repo.recent_violations()) == 1
        assert repo.recent_violations(violation_type="illegal_uturn") == []
        assert len(repo.recent_violations(violation_type="red_light")) == 1
        assert repo.count_by_type()["red_light"] == 1


class TestDriverFallback:
    def test_falls_back_to_sqlite_without_pymysql(self, monkeypatch):
        """pymysql 미설치 환경에서도 기동은 되어야 한다."""
        monkeypatch.setitem(sys.modules, "pymysql", None)
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *a, **k):
            if name == "pymysql":
                raise ImportError("no pymysql")
            return real_import(name, *a, **k)

        monkeypatch.setattr(builtins, "__import__", fake_import)

        from app.vehicle.repository import VehicleRepository

        repo = VehicleRepository(driver="mysql", sqlite_path=":memory:")
        assert repo.driver == "sqlite"
        assert repo.find("12가3456") is not None
