#!/usr/bin/env python3
"""MySQL 실접속 점검 — '코드만 있고 붙여본 적 없음' 상태를 끝낸다.

왜 따로 만드나
    `VehicleRepository` 는 MySQL 접속에 실패하면 **조용히 SQLite 로 넘어간다.**
    시연이 멈추지 않게 하려는 설계인데, 그래서 평소에 돌려서는
    "정말 MySQL 에 붙었는지" 알 수가 없다. 이 스크립트는 폴백 없이
    직접 붙어 보고, 실패하면 실패한 이유를 그대로 보여준다.

무엇을 확인하나
    1) pymysql 설치 여부
    2) 서버 접속        (호스트·포트·계정)
    3) 데이터베이스 존재 (없으면 --create 로 만든다)
    4) 스키마 적용      (sql/schema.sql)
    5) 읽기/쓰기        (seed 넣고 조회)
    6) 한글 저장        (utf8mb4 가 아니면 '가' 가 깨진다)
    7) 실제 조회 경로   (VehicleMatcher 가 MySQL 로 판별하는지)

사용법
    python check_mysql.py                     # 접속만 확인
    python check_mysql.py --create            # DB·스키마·시드까지 만든다
    python check_mysql.py --host 192.168.0.5 --user omeca --password 1234
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from app.core.config import settings          # noqa: E402

LINE = "─" * 70
OK, NO = "  [OK]", "  [실패]"


def step(n: int, title: str) -> None:
    print(f"\n{n}. {title}")


def split_sql(text: str) -> list[str]:
    """.sql 파일을 실행 가능한 문장 목록으로 나눈다.

    단순히 ';' 로 쪼개고 "'--' 로 시작하면 주석" 으로 넘기면 안 된다.
    우리 schema.sql 은 문장마다 앞에 주석 줄이 붙어 있어서, 그렇게 하면
    **`CREATE TABLE` 이 통째로 주석 취급되어 테이블이 하나도 안 생긴다.**

        -- ------------------------
        -- 차량 원장
        -- ------------------------
        CREATE TABLE vehicle (...)      ← 이게 같은 '문장'에 들어 있다

    그래서 주석 '줄'을 먼저 걷어내고 남은 것이 있는지 본다.
    `USE ...` 는 건너뛴다 — 접속할 때 이미 데이터베이스를 지정했고,
    파일에 박힌 이름(`omeca`)이 --database 지정을 덮어쓰면 안 된다.
    """
    out: list[str] = []
    for chunk in text.split(";"):
        lines = [ln for ln in chunk.splitlines()
                 if not ln.strip().startswith("--")]
        stmt = "\n".join(lines).strip()
        if not stmt:
            continue
        if stmt.upper().startswith("USE "):
            continue
        out.append(stmt)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="MySQL 실접속 점검")
    ap.add_argument("--host", default=settings.db.host)
    ap.add_argument("--port", type=int, default=settings.db.port)
    ap.add_argument("--user", default=settings.db.user)
    ap.add_argument("--password", default=settings.db.password)
    ap.add_argument("--database", default=settings.db.database)
    ap.add_argument("--create", action="store_true",
                    help="DB·스키마·시드를 만든다 (없을 때만)")
    a = ap.parse_args()

    print(f"{LINE}\nMySQL 실접속 점검\n{LINE}")
    print(f"  대상  {a.user}@{a.host}:{a.port}/{a.database}")
    print(f"  설정  config.yaml driver = {settings.db.driver}")

    # ---------------------------------------------------------------- 1
    step(1, "pymysql 설치 확인")
    try:
        import pymysql
    except ImportError:
        print(NO, "pymysql 이 없습니다.")
        print("        pip install pymysql")
        return 1
    print(OK, f"pymysql {pymysql.__version__}")

    # ---------------------------------------------------------------- 2
    step(2, "서버 접속 (DB 지정 없이)")
    try:
        srv = pymysql.connect(host=a.host, port=a.port, user=a.user,
                              password=a.password, charset="utf8mb4",
                              autocommit=True, connect_timeout=5)
    except Exception as e:
        print(NO, f"{type(e).__name__}: {e}")
        print("\n   자주 나는 원인")
        print("     · MySQL 이 안 켜져 있음  → services.msc 에서 MySQL 시작")
        print("     · 계정/비밀번호 틀림      → --user --password 로 지정")
        print("     · 아직 설치 안 함         → MySQL Community Server 설치")
        return 1
    with srv.cursor() as c:
        c.execute("SELECT VERSION()")
        ver = c.fetchone()[0]
    print(OK, f"접속 성공, 서버 버전 {ver}")

    # ---------------------------------------------------------------- 3
    step(3, f"데이터베이스 '{a.database}' 확인")
    with srv.cursor() as c:
        c.execute("SHOW DATABASES LIKE %s", (a.database,))
        exists = c.fetchone() is not None
    if exists:
        print(OK, "존재함")
    elif a.create:
        with srv.cursor() as c:
            c.execute(f"CREATE DATABASE `{a.database}` "
                      "DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        print(OK, "새로 만들었습니다")
    else:
        print(NO, "없습니다.  --create 를 붙이면 만듭니다.")
        return 1
    srv.close()

    # ---------------------------------------------------------------- 4
    conn = pymysql.connect(host=a.host, port=a.port, user=a.user,
                           password=a.password, database=a.database,
                           charset="utf8mb4", autocommit=True)

    step(4, "스키마 적용")
    with conn.cursor() as c:
        c.execute("SHOW TABLES")
        tables = {r[0] for r in c.fetchall()}
    need = {"vehicle", "violation", "plate_read_log"}
    missing = need - tables
    if not missing:
        print(OK, f"테이블 {sorted(need)} 모두 존재")
    elif a.create:
        sql = (BASE / "sql" / "schema.sql").read_text(encoding="utf-8")
        done, failed = 0, []
        for stmt in split_sql(sql):
            try:
                with conn.cursor() as c:
                    c.execute(stmt)
                done += 1
            except Exception as e:
                head = " ".join(stmt.split()[:5])
                failed.append((head, f"{type(e).__name__}: {str(e)[:100]}"))
        print(f"     {done}개 성공 / {len(failed)}개 실패")
        for head, err in failed:
            print(f"       실패: {head}\n              {err}")

        # **만들었다고 믿지 말고 다시 센다.** 문장이 실패해도 다음 단계로
        # 넘어가면 'no such table' 같은 파이썬 오류가 나서 원인을 못 찾는다.
        with conn.cursor() as c:
            c.execute("SHOW TABLES")
            tables = {r[0] for r in c.fetchall()}
        missing = need - tables
        if missing:
            print(NO, f"만들었는데도 없는 테이블: {sorted(missing)}")
            print("        위 '실패' 메시지가 원인입니다. sql/schema.sql 을 확인하세요.")
            return 1
        print(OK, f"테이블 {sorted(need)} 생성 확인")
    else:
        print(NO, f"없는 테이블: {sorted(missing)}.  --create 를 붙이세요.")
        return 1

    # ---------------------------------------------------------------- 5
    step(5, "읽기 / 쓰기")
    with conn.cursor() as c:
        c.execute("SELECT COUNT(*) FROM vehicle")
        n = c.fetchone()[0]
    print(f"     vehicle 행 수 {n}")
    if n == 0 and a.create:
        seed = BASE / "sql" / "seed.sql"
        if seed.exists():
            done = 0
            for stmt in split_sql(seed.read_text(encoding="utf-8")):
                try:
                    with conn.cursor() as c:
                        c.execute(stmt)
                    done += 1
                except Exception as e:
                    print(f"     건너뜀: {str(e)[:80]}")
            with conn.cursor() as c:
                c.execute("SELECT COUNT(*) FROM vehicle")
                n = c.fetchone()[0]
            print(OK, f"시드 {done}개 문장 실행 → {n}행")
    if n == 0:
        print(NO, "데이터가 없습니다. --create 로 시드를 넣으세요.")
        return 1
    print(OK, "읽기 성공")

    # ---------------------------------------------------------------- 6
    step(6, "한글 저장 (utf8mb4 확인)")
    #   문자셋이 latin1 이면 여기서 '가' 가 '?' 로 바뀐다. 실제로 넣고 꺼내 본다.
    probe = "99하9999"
    with conn.cursor() as c:
        c.execute("DELETE FROM vehicle WHERE plate_no = %s", (probe,))
        c.execute("INSERT INTO vehicle (plate_no, owner_name, status) "
                  "VALUES (%s, %s, %s)", (probe, "점검용-한글", "registered"))
        c.execute("SELECT plate_no, owner_name FROM vehicle WHERE plate_no = %s", (probe,))
        got = c.fetchone()
        c.execute("DELETE FROM vehicle WHERE plate_no = %s", (probe,))
    if got and got[0] == probe and got[1] == "점검용-한글":
        print(OK, f"한글 왕복 성공 ({got[0]} / {got[1]})")
    else:
        print(NO, f"한글이 깨졌습니다: {got}")
        print("        DB 문자셋을 utf8mb4 로 바꿔야 합니다.")
        return 1
    conn.close()

    # ---------------------------------------------------------------- 7
    step(7, "실제 조회 경로 (VehicleMatcher)")
    #   설정을 mysql 로 바꿔 우리 코드가 정말 MySQL 을 쓰는지 본다.
    settings.db.driver = "mysql"
    settings.db.host, settings.db.port = a.host, a.port
    settings.db.user, settings.db.password = a.user, a.password
    settings.db.database = a.database
    from app.vehicle.repository import VehicleRepository
    repo = VehicleRepository()
    if repo.driver != "mysql":
        print(NO, "SQLite 로 폴백했습니다. 위 단계는 통과했는데 여기서 실패했다면")
        print("        VehicleRepository._connect() 의 예외를 확인하세요.")
        return 1
    print(OK, f"driver = {repo.driver}")

    with repo._conn.cursor() as c:
        c.execute("SELECT plate_no, status FROM vehicle LIMIT 3")
        rows = c.fetchall()
    print("     조회 예:")
    for r in rows:
        print(f"       {r[0]:12} {r[1]}")

    print(f"\n{LINE}")
    print("모든 단계 통과. MySQL 로 실제 조회가 됩니다.")
    print(LINE)
    print("\n운영에서 MySQL 을 쓰려면 config.yaml 을 고칩니다.")
    print("    db:\n      driver: mysql")
    print(f"      host: {a.host}\n      port: {a.port}")
    print(f"      user: {a.user}\n      database: {a.database}")
    print("\n비밀번호는 config.yaml 에 적지 말고 .env 의 OMECA_DB_PASSWORD 를 쓴다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
