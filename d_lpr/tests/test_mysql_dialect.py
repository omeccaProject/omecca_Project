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
        assert {"vehicle", "violation", "plate_read_log"} <= tables

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
        """미등록 차량도 기록해야 하므로 vehicle 로의 FK 가 있으면 안 된다."""
        sql = (ROOT / "sql" / "schema.sql").read_text(encoding="utf-8")
        body = sql.split("CREATE TABLE IF NOT EXISTS violation")[1].split(";")[0]
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
        repo.recent_violations(limit=10)
        repo.recent_violations(limit=10, violation_type="red_light",
                               cam_id="CAM-001", risk_level="high")
        assert len(conn.log) >= 7

    def test_all_aggregate_queries_valid(self, mysql_repo):
        repo, conn = mysql_repo
        repo.count_by_type()
        repo.count_by_cam()
        repo.count_by_risk()
        repo.count_by_hour()      # MySQL 전용 분기 (LPAD/HOUR)
        repo.count_by_day(14)     # MySQL 전용 분기 (DATE)
        repo.plate_read_summary()
        assert len(conn.log) == 6

    def test_hour_query_uses_mysql_functions(self, mysql_repo):
        repo, conn = mysql_repo
        repo.count_by_hour()
        sql = conn.log[-1][0].upper()
        assert "HOUR(" in sql and "STRFTIME" not in sql

    def test_day_query_uses_mysql_functions(self, mysql_repo):
        repo, conn = mysql_repo
        repo.count_by_day()
        sql = conn.log[-1][0].upper()
        assert "DATE(" in sql and "SUBSTR" not in sql

    def test_write_queries_valid(self, mysql_repo):
        repo, conn = mysql_repo
        repo.save_violation(make_event())
        repo.log_plate_read("CAM-001", 1, "12가3456", "12가3456",
                            0.9, True, "easyocr", time.time())
        repo.upsert(VehicleRecord(plate_no="99하9999", status=VehicleStatus.WANTED))
        repo.clear()
        assert len(conn.log) >= 5

    def test_violation_insert_param_count(self, mysql_repo):
        repo, conn = mysql_repo
        repo.save_violation(make_event())
        sql, params = conn.log[-1]
        assert sql.upper().startswith("INSERT INTO VIOLATION")
        assert len(params) == 13

    def test_filters_append_conditions(self, mysql_repo):
        repo, conn = mysql_repo
        repo.recent_violations(limit=5, violation_type="red_light", cam_id="CAM-001")
        sql, params = conn.log[-1]
        assert sql.count("%s") == 3        # type, cam_id, limit
        assert params[-1] == 5


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
