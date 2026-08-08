"""vehicle / violation 테이블 접근 계층.

driver 설정에 따라 SQLite(로컬·시연) 또는 MySQL(운영)을 쓴다.
SQL 방언 차이는 이 계층에서 흡수하므로 상위 모듈은 드라이버를 몰라도 된다.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional

from ..core.config import settings
from ..core.schemas import RiskLevel, VehicleRecord, VehicleStatus, ViolationEvent
from ..lpr import plate_format as pf

log = logging.getLogger("omeca.vehicle.repo")

SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS vehicle (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    plate_no      TEXT NOT NULL UNIQUE,
    owner_name    TEXT,
    model         TEXT,
    color         TEXT,
    status        TEXT NOT NULL DEFAULT 'registered',
    registered_at TEXT,
    memo          TEXT
);
CREATE INDEX IF NOT EXISTS idx_vehicle_status ON vehicle(status);

CREATE TABLE IF NOT EXISTS violation (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id         TEXT NOT NULL UNIQUE,
    violation_type   TEXT NOT NULL,
    cam_id           TEXT NOT NULL,
    track_id         INTEGER NOT NULL,
    plate_no         TEXT,
    plate_confidence REAL NOT NULL DEFAULT 0,
    vehicle_status   TEXT,
    risk_level       TEXT NOT NULL DEFAULT 'normal',
    zone_id          TEXT,
    detail           TEXT,
    occurred_at      TEXT NOT NULL,
    lat              REAL,
    lon              REAL,
    report_path      TEXT
);
CREATE INDEX IF NOT EXISTS idx_violation_time ON violation(occurred_at);
CREATE INDEX IF NOT EXISTS idx_violation_type ON violation(violation_type);
CREATE INDEX IF NOT EXISTS idx_violation_plate ON violation(plate_no);

CREATE TABLE IF NOT EXISTS plate_read_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    cam_id       TEXT NOT NULL,
    track_id     INTEGER NOT NULL,
    plate_no     TEXT,
    raw_text     TEXT,
    confidence   REAL NOT NULL DEFAULT 0,
    valid_format INTEGER NOT NULL DEFAULT 0,
    engine       TEXT NOT NULL DEFAULT 'easyocr',
    read_at      TEXT NOT NULL
);
"""

SEED_VEHICLES: list[tuple] = [
    ("12가3456", "김철수", "아반떼 CN7", "흰색", "registered", "2021-03-14", None),
    ("34나5678", "이영희", "K5 DL3", "검정", "registered", "2020-11-02", None),
    ("56다7890", "박민수", "쏘렌토 MQ4", "회색", "registered", "2022-06-21", None),
    ("78라1234", "최지훈", "그랜저 GN7", "남색", "registered", "2023-01-09", None),
    ("90마2345", "정수민", "레이", "노랑", "registered", "2019-08-30", None),
    ("11바1111", "(불명)", "스타렉스", "흰색", "fake_plate", "2018-02-11", "명의 불일치 - 대포차 의심"),
    ("22사2222", "(불명)", "카니발", "검정", "stolen", "2017-05-23", "2026-05-02 도난 신고 접수"),
    ("33아3333", "(불명)", "BMW 520d", "흰색", "wanted", "2016-09-14", "수배 대상 차량 - 강력 5팀"),
    ("44자4444", "한도윤", "티볼리", "빨강", "impound", "2019-12-01", "과태료 체납 영치 대상"),
    ("55저5555", "오세훈", "모닝", "파랑", "insurance_expired", "2020-04-17", "책임보험 만료"),
    ("123허4567", "(렌터카)", "아반떼 CN7", "흰색", "registered", "2024-02-20", "렌터카"),
    ("67바8901", "(운수)", "카운티", "흰색", "registered", "2021-07-07", "영업용"),
]


class VehicleRepository:
    def __init__(self, driver: Optional[str] = None, sqlite_path: Optional[str] = None) -> None:
        self.driver = (driver or settings.db.driver).lower()
        self.sqlite_path = sqlite_path or settings.db.sqlite_path
        self._lock = threading.Lock()
        self._conn = self._connect()
        self._ph = "?" if self.driver == "sqlite" else "%s"
        if self.driver == "sqlite":
            self._init_sqlite()

    # ------------------------------------------------------------------
    def _connect(self):
        if self.driver == "mysql":  # pragma: no cover - 운영 환경 의존
            try:
                import pymysql  # type: ignore
                return pymysql.connect(
                    host=settings.db.host, port=int(settings.db.port),
                    user=settings.db.user, password=settings.db.password,
                    database=settings.db.database, charset="utf8mb4",
                    autocommit=True,
                )
            except ImportError:
                log.warning("pymysql 미설치 → SQLite로 폴백")
                self.driver = "sqlite"
            except Exception:
                log.exception("MySQL 접속 실패 → SQLite로 폴백")
                self.driver = "sqlite"

        return self._open_sqlite(self.sqlite_path)

    @staticmethod
    def _open_sqlite(path: str):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _fallback_sqlite(self) -> None:
        """네트워크/공유 폴더 등 파일 잠금이 안 되는 위치일 때 임시 경로로 전환.

        일부 마운트(FUSE, 네트워크 드라이브)는 SQLite 잠금을 지원하지 않아
        'disk I/O error' 가 난다. 시연이 멈추지 않도록 임시 디렉터리로 옮긴다.
        """
        import tempfile

        alt = os.path.join(tempfile.gettempdir(), "omeca_lpr.db")
        log.warning("SQLite 파일 잠금 불가(%s) → 임시 경로로 전환: %s", self.sqlite_path, alt)
        try:
            self._conn.close()
        except Exception:
            pass
        self.sqlite_path = alt
        self._conn = self._open_sqlite(alt)

    def _init_sqlite(self) -> None:
        try:
            self._run_schema()
        except sqlite3.OperationalError:
            self._fallback_sqlite()
            self._run_schema()

    def _run_schema(self) -> None:
        with self._lock:
            self._conn.executescript(SQLITE_SCHEMA)
            cnt = self._conn.execute("SELECT COUNT(*) c FROM vehicle").fetchone()["c"]
            if cnt == 0:
                self._conn.executemany(
                    "INSERT OR IGNORE INTO vehicle "
                    "(plate_no, owner_name, model, color, status, registered_at, memo) "
                    "VALUES (?,?,?,?,?,?,?)",
                    SEED_VEHICLES,
                )
            self._conn.commit()

    def _rows(self, sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
        sql = sql.replace("?", self._ph) if self._ph != "?" else sql
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(sql, tuple(params))
            cols = [d[0] for d in cur.description] if cur.description else []
            return [dict(zip(cols, r)) for r in cur.fetchall()]

    def _exec(self, sql: str, params: Iterable[Any] = ()) -> int:
        sql = sql.replace("?", self._ph) if self._ph != "?" else sql
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(sql, tuple(params))
            self._conn.commit()
            return cur.rowcount

    # ------------------------------------------------------------------
    # vehicle
    # ------------------------------------------------------------------
    def find(self, plate_no: str) -> Optional[VehicleRecord]:
        key = pf.canonical(plate_no)
        if not key:
            return None
        rows = self._rows("SELECT * FROM vehicle WHERE plate_no = ?", (key,))
        return self._to_record(rows[0]) if rows else None

    def find_similar(self, plate_no: str, max_diff: int = 1) -> Optional[tuple[VehicleRecord, int]]:
        """1글자 오차 유사 매칭.

        OCR이 한 글자를 놓쳐도 후보를 건지되, 오검거를 막기 위해
        후보가 유일할 때만 채택한다(동점이면 포기).
        """
        key = pf.canonical(plate_no)
        if len(key) < 6:
            return None
        rows = self._rows(
            "SELECT * FROM vehicle WHERE LENGTH(plate_no) = ?", (len(key),)
        )
        hits: list[tuple[VehicleRecord, int]] = []
        for r in rows:
            d = pf.similarity(key, r["plate_no"])
            if d <= max_diff:
                hits.append((self._to_record(r), d))
        if not hits:
            return None
        hits.sort(key=lambda t: t[1])
        if len(hits) > 1 and hits[0][1] == hits[1][1]:
            return None  # 동점 후보 다수 → 오검거 방지를 위해 미채택
        return hits[0]

    def upsert(self, rec: VehicleRecord) -> None:
        key = pf.canonical(rec.plate_no)
        exists = self._rows("SELECT id FROM vehicle WHERE plate_no = ?", (key,))
        status = rec.status.value if isinstance(rec.status, VehicleStatus) else str(rec.status)
        if exists:
            self._exec(
                "UPDATE vehicle SET owner_name=?, model=?, color=?, status=?, "
                "registered_at=?, memo=? WHERE plate_no=?",
                (rec.owner_name, rec.model, rec.color, status, rec.registered_at, rec.memo, key),
            )
        else:
            self._exec(
                "INSERT INTO vehicle (plate_no, owner_name, model, color, status, "
                "registered_at, memo) VALUES (?,?,?,?,?,?,?)",
                (key, rec.owner_name, rec.model, rec.color, status, rec.registered_at, rec.memo),
            )

    def list_vehicles(self, status: Optional[str] = None, limit: int = 200) -> list[VehicleRecord]:
        if status:
            rows = self._rows(
                "SELECT * FROM vehicle WHERE status = ? ORDER BY id LIMIT ?", (status, limit)
            )
        else:
            rows = self._rows("SELECT * FROM vehicle ORDER BY id LIMIT ?", (limit,))
        return [self._to_record(r) for r in rows]

    def all_plates(self) -> list[str]:
        return [r["plate_no"] for r in self._rows("SELECT plate_no FROM vehicle")]

    @staticmethod
    def _to_record(row: dict[str, Any]) -> VehicleRecord:
        try:
            status = VehicleStatus(row.get("status") or "registered")
        except ValueError:
            status = VehicleStatus.REGISTERED
        return VehicleRecord(
            plate_no=row["plate_no"],
            owner_name=row.get("owner_name") or "",
            model=row.get("model") or "",
            color=row.get("color") or "",
            status=status,
            registered_at=str(row.get("registered_at") or ""),
            memo=row.get("memo") or "",
        )

    # ------------------------------------------------------------------
    # violation
    # ------------------------------------------------------------------
    def save_violation(self, ev: ViolationEvent) -> None:
        occurred = datetime.fromtimestamp(ev.timestamp).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        lat, lon = (ev.location or (None, None))
        self._exec(
            "INSERT INTO violation (event_id, violation_type, cam_id, track_id, plate_no, "
            "plate_confidence, vehicle_status, risk_level, zone_id, detail, occurred_at, lat, lon) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                ev.event_id, ev.violation_type.value, ev.cam_id, ev.track_id,
                ev.plate_no or None, float(ev.plate_confidence),
                ev.vehicle_status.value, ev.risk_level.value,
                ev.zone_id, ev.detail, occurred, lat, lon,
            ),
        )

    def log_plate_read(
        self, cam_id: str, track_id: int, plate_no: str, raw_text: str,
        confidence: float, valid_format: bool, engine: str, ts: float,
    ) -> None:
        self._exec(
            "INSERT INTO plate_read_log (cam_id, track_id, plate_no, raw_text, confidence, "
            "valid_format, engine, read_at) VALUES (?,?,?,?,?,?,?,?)",
            (
                cam_id, track_id, plate_no, raw_text, float(confidence),
                1 if valid_format else 0, engine,
                datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
            ),
        )

    def recent_violations(
        self, limit: int = 100, violation_type: Optional[str] = None,
        cam_id: Optional[str] = None, risk_level: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM violation WHERE 1=1"
        params: list[Any] = []
        if violation_type:
            sql += " AND violation_type = ?"; params.append(violation_type)
        if cam_id:
            sql += " AND cam_id = ?"; params.append(cam_id)
        if risk_level:
            sql += " AND risk_level = ?"; params.append(risk_level)
        sql += " ORDER BY occurred_at DESC LIMIT ?"
        params.append(limit)
        return self._rows(sql, params)

    def count_by_type(self) -> dict[str, int]:
        rows = self._rows("SELECT violation_type, COUNT(*) AS cnt FROM violation GROUP BY violation_type")
        return {r["violation_type"]: int(r["cnt"]) for r in rows}

    def count_by_cam(self) -> dict[str, int]:
        rows = self._rows("SELECT cam_id, COUNT(*) AS cnt FROM violation GROUP BY cam_id ORDER BY cnt DESC")
        return {r["cam_id"]: int(r["cnt"]) for r in rows}

    def count_by_risk(self) -> dict[str, int]:
        rows = self._rows("SELECT risk_level, COUNT(*) AS cnt FROM violation GROUP BY risk_level")
        return {r["risk_level"]: int(r["cnt"]) for r in rows}

    def count_by_hour(self) -> dict[str, int]:
        """시간대별 발생 건수. 관제 인력 배치 근거 자료로 쓴다."""
        if self.driver == "sqlite":
            sql = "SELECT strftime('%H', occurred_at) AS h, COUNT(*) AS cnt FROM violation GROUP BY h ORDER BY h"
        else:  # pragma: no cover
            sql = "SELECT LPAD(HOUR(occurred_at),2,'0') AS h, COUNT(*) AS cnt FROM violation GROUP BY h ORDER BY h"
        return {r["h"]: int(r["cnt"]) for r in self._rows(sql) if r["h"] is not None}

    def count_by_day(self, days: int = 14) -> dict[str, int]:
        if self.driver == "sqlite":
            sql = ("SELECT substr(occurred_at,1,10) AS d, COUNT(*) AS cnt FROM violation "
                   "GROUP BY d ORDER BY d DESC LIMIT ?")
        else:  # pragma: no cover
            sql = ("SELECT DATE(occurred_at) AS d, COUNT(*) AS cnt FROM violation "
                   "GROUP BY d ORDER BY d DESC LIMIT ?")
        rows = self._rows(sql, (days,))
        return {str(r["d"]): int(r["cnt"]) for r in reversed(rows)}

    def plate_read_summary(self) -> dict[str, Any]:
        rows = self._rows(
            "SELECT COUNT(*) AS total, "
            "SUM(valid_format) AS valid, "
            "AVG(confidence) AS avg_conf FROM plate_read_log"
        )
        r = rows[0] if rows else {}
        total = int(r.get("total") or 0)
        valid = int(r.get("valid") or 0)
        return {
            "total": total,
            "valid": valid,
            "valid_rate": round(valid / total, 4) if total else 0.0,
            "avg_confidence": round(float(r.get("avg_conf") or 0.0), 4),
        }

    # ------------------------------------------------------------------
    def clear(self) -> None:
        """테스트용 초기화."""
        for t in ("violation", "plate_read_log"):
            self._exec(f"DELETE FROM {t}")

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass


_repo: Optional[VehicleRepository] = None
_repo_lock = threading.Lock()


def get_repository() -> VehicleRepository:
    global _repo
    if _repo is None:
        with _repo_lock:
            if _repo is None:
                _repo = VehicleRepository()
    return _repo


def reset_repository(repo: Optional[VehicleRepository] = None) -> None:
    """테스트에서 인메모리 저장소로 교체할 때 사용."""
    global _repo
    with _repo_lock:
        if _repo is not None and repo is not _repo:
            _repo.close()
        _repo = repo
