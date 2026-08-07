"""위반 유형별 발생 현황·통계 집계.

대시보드와 REST API가 공유하는 집계 로직. 여기에 모아두면
Spring Boot 게이트웨이(장성혁)가 같은 수치를 그대로 가져다 쓸 수 있다.
"""

from __future__ import annotations

from typing import Any, Optional

from ..core.schemas import VIOLATION_LABEL_KO, ViolationType
from ..vehicle.repository import VehicleRepository, get_repository


def summary(repo: Optional[VehicleRepository] = None) -> dict[str, Any]:
    """대시보드 상단 요약 카드용 지표."""
    repo = repo or get_repository()
    by_type = repo.count_by_type()
    by_risk = repo.count_by_risk()
    total = sum(by_type.values())
    reads = repo.plate_read_summary()

    return {
        "total_violations": total,
        "high_risk": by_risk.get("high", 0),
        "red_light": by_type.get(ViolationType.RED_LIGHT.value, 0),
        "illegal_uturn": by_type.get(ViolationType.ILLEGAL_UTURN.value, 0),
        "high_risk_vehicle": by_type.get(ViolationType.HIGH_RISK_VEHICLE.value, 0),
        "plate_reads": reads["total"],
        "plate_valid_rate": reads["valid_rate"],
        "plate_avg_confidence": reads["avg_confidence"],
    }


def by_type(repo: Optional[VehicleRepository] = None) -> list[dict[str, Any]]:
    repo = repo or get_repository()
    counts = repo.count_by_type()
    out = []
    for vt in ViolationType:
        out.append({
            "type": vt.value,
            "label": VIOLATION_LABEL_KO[vt],
            "count": counts.get(vt.value, 0),
        })
    return out


def by_camera(repo: Optional[VehicleRepository] = None, limit: int = 10) -> list[dict[str, Any]]:
    repo = repo or get_repository()
    items = list(repo.count_by_cam().items())[:limit]
    return [{"cam_id": c, "count": n} for c, n in items]


def by_hour(repo: Optional[VehicleRepository] = None) -> list[dict[str, Any]]:
    """0~23시 전 구간을 채워 반환한다 (빈 시간대는 0)."""
    repo = repo or get_repository()
    counts = repo.count_by_hour()
    return [{"hour": f"{h:02d}", "count": counts.get(f"{h:02d}", 0)} for h in range(24)]


def by_day(repo: Optional[VehicleRepository] = None, days: int = 14) -> list[dict[str, Any]]:
    repo = repo or get_repository()
    return [{"date": d, "count": n} for d, n in repo.count_by_day(days).items()]


def by_risk(repo: Optional[VehicleRepository] = None) -> list[dict[str, Any]]:
    repo = repo or get_repository()
    counts = repo.count_by_risk()
    labels = {"high": "고위험", "caution": "주의", "normal": "일반"}
    return [
        {"risk_level": k, "label": labels.get(k, k), "count": counts.get(k, 0)}
        for k in ("high", "caution", "normal")
    ]


def full(repo: Optional[VehicleRepository] = None) -> dict[str, Any]:
    """대시보드가 한 번의 호출로 전체 통계를 받아가는 엔드포인트용."""
    repo = repo or get_repository()
    return {
        "summary": summary(repo),
        "by_type": by_type(repo),
        "by_camera": by_camera(repo),
        "by_hour": by_hour(repo),
        "by_day": by_day(repo),
        "by_risk": by_risk(repo),
    }
