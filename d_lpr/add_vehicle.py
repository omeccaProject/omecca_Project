#!/usr/bin/env python3
"""차량 DB에 번호판을 등록/변경한다 — 미등록 판정을 실제로 검증하기 위한 도구.

왜 필요한가
    `sql/seed.sql` 에 들어 있는 12대는 `12가3456` 같은 **가짜 번호**다.
    그래서 실제 도로 영상을 돌리면 **읽힌 번호가 전부 '미등록'** 으로 뜬다.
    "미등록이 잘 뜨나?" 는 확인되지만 "등록된 차를 등록으로 보나?" 는
    확인이 안 된다. 둘 다 봐야 판정이 맞는지 알 수 있다.

    그래서 영상에서 읽힌 번호 몇 개를 여기로 등록해 넣고 다시 돌린다.
    그러면 같은 영상에서 등록/미등록이 갈리는 것을 눈으로 볼 수 있다.

사용법
    python add_vehicle.py --list                        # 지금 등록된 차량 보기
    python add_vehicle.py 12가3456                       # 정상 등록 차량으로 추가
    python add_vehicle.py 12가3456 --status stolen       # 도난 차량으로 추가
    python add_vehicle.py 12가3456 34나5678 56다7890     # 여러 대 한 번에
    python add_vehicle.py --remove 12가3456              # 지우기

상태값
    registered          정상 등록          (위험도 낮음)
    unregistered        미등록
    stolen              도난 신고
    wanted              수배
    fake_plate          대포차 의심
    impound             과태료 체납 영치 대상
    insurance_expired   책임보험 만료

주의
    `--status` 를 안 주면 `registered` 다. 시연용으로 한두 대를 `stolen` 등으로
    넣어 두면 경보(ALERT) 가 뜨는 것까지 확인할 수 있다.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from app.core.schemas import VehicleRecord, VehicleStatus   # noqa: E402
from app.lpr import plate_format as pf                      # noqa: E402
from app.vehicle.repository import get_repository           # noqa: E402

LINE = "─" * 66

STATUSES = [s.value for s in VehicleStatus]


def show(repo) -> None:
    rows = repo.list_vehicles(limit=500)
    print(f"\n등록된 차량 {len(rows)}대  (driver = {repo.driver})")
    print(LINE)
    if not rows:
        print("  (없음)")
        return
    for r in rows:
        owner = getattr(r, "owner_name", "") or ""
        print(f"  {r.plate_no:14} {str(r.status):20} {owner}")
    print(LINE)


def main() -> int:
    ap = argparse.ArgumentParser(description="차량 DB 등록/변경")
    ap.add_argument("plates", nargs="*", help="번호판 (여러 개 가능)")
    ap.add_argument("--status", default="registered", choices=STATUSES,
                    help="차량 상태 (기본 registered)")
    ap.add_argument("--owner", default="", help="소유자명 (선택)")
    ap.add_argument("--list", action="store_true", help="등록 목록만 보기")
    ap.add_argument("--remove", action="store_true", help="지정한 번호판을 지운다")
    a = ap.parse_args()

    repo = get_repository()

    if a.list or not a.plates:
        show(repo)
        if not a.plates:
            print("\n등록하려면:  python add_vehicle.py 12가3456")
        return 0

    # 형식 검사를 먼저 한다. 오타로 이상한 값이 들어가면 나중에 원인을 못 찾는다.
    bad = [p for p in a.plates if not pf.is_valid(pf.strip_noise(p))]
    if bad:
        print("번호판 형식이 아닙니다:", ", ".join(bad))
        print("  예)  12가3456   서울78바9012   123허4567")
        return 1

    for raw in a.plates:
        plate = pf.canonical(pf.strip_noise(raw))   # 지역명을 떼고 저장 형태로
        if a.remove:
            n = repo._exec("DELETE FROM vehicle WHERE plate_no = %s"
                           if repo.driver == "mysql" else
                           "DELETE FROM vehicle WHERE plate_no = ?", (plate,))
            print(f"  삭제 {plate}  ({n}행)")
            continue
        repo.upsert(VehicleRecord(
            plate_no=plate,
            owner_name=a.owner or "테스트 등록",
            status=VehicleStatus(a.status),
        ))
        print(f"  등록 {plate}  → {a.status}")

    show(repo)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
