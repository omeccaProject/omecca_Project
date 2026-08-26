"""가상 라인 / ROI 정의 및 통과 판정.

관제 화면에서 관리자가 교차로 정지선·진출선·유턴 금지 구역을 그려두면
JSON으로 저장되고, 여기서 로드해 궤적과 대조한다.

  VirtualLine : 두 점으로 정의된 선. 어느 방향으로 넘었는지까지 판정한다.
  Zone        : 다각형 영역. 유턴 금지 구역 등에 사용.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Sequence

from ..core.geometry import Point, point_in_polygon, segments_intersect, side_of

log = logging.getLogger("omeca.violation.roi")


@dataclass
class VirtualLine:
    """가상 라인.

    direction: 이 라인을 넘어도 되는 방향
        "both"     - 방향 무관
        "positive" - 라인 왼쪽(+) → 오른쪽(-) 통과만 유효 진행으로 본다
        "negative" - 그 반대
    """

    line_id: str
    p1: tuple[float, float]
    p2: tuple[float, float]
    name: str = ""
    direction: str = "both"
    # 라인 종류
    #   stop     : 정지선        (신호위반 판정용)
    #   exit     : 진출선        (신호위반 확정용)
    #   center   : 중앙선(노란 실선) — 유턴 판정의 1차 트리거
    line_type: str = "stop"
    # 이 중앙선을 넘는 유턴이 표지판으로 허용되는 구간인지.
    # False 면 신호와 무관하게 유턴 자체가 불법이다.
    uturn_allowed: bool = False
    # 유턴 허용 구간일 때 참조할 신호등 ID (좌회전 화살표 확인용)
    signal_id: str = ""

    def side(self, point: Point) -> int:
        return side_of(self.p1, self.p2, point)

    def crossed(self, prev: Point, cur: Point) -> Optional[int]:
        """이전 위치 → 현재 위치 이동이 라인을 넘었는지.

        넘었으면 통과 방향(+1 / -1)을, 아니면 None을 반환한다.
        선분 교차와 부호 변화를 함께 확인해 라인 연장선 통과를 오탐하지 않는다.
        """
        s_prev, s_cur = self.side(prev), self.side(cur)
        if s_prev == 0 or s_cur == 0 or s_prev == s_cur:
            return None
        if not segments_intersect(prev, cur, self.p1, self.p2):
            return None
        return 1 if s_prev > 0 else -1

    def crossed_from(
        self, prev_point: Point, prev_side: int, cur: Point
    ) -> Optional[int]:
        """마지막으로 부호가 확정된 지점 기준 통과 판정.

        차량 좌표가 라인 위에 정확히 놓이면(side == 0) 단순 이전 프레임 비교는
        통과를 놓친다. 마지막 비영(非零) 부호와 그 지점을 넘겨 받아 판정한다.
        """
        s_cur = self.side(cur)
        if s_cur == 0 or prev_side == 0 or s_cur == prev_side:
            return None
        if not segments_intersect(prev_point, cur, self.p1, self.p2):
            return None
        return 1 if prev_side > 0 else -1

    def is_forward(self, cross_dir: int) -> bool:
        """정상 진행 방향으로 통과했는지."""
        if self.direction == "both":
            return True
        if self.direction == "positive":
            return cross_dir == 1
        return cross_dir == -1


@dataclass
class Zone:
    """다각형 ROI."""

    zone_id: str
    polygon: list[tuple[float, float]]
    name: str = ""
    zone_type: str = "generic"      # intersection | uturn | generic
    uturn_allowed: bool = False     # 유턴 허용 구간이면 True (판정 제외)

    def contains(self, point: Point) -> bool:
        return point_in_polygon(point, self.polygon)


@dataclass
class CameraZones:
    """카메라 한 대에 설정된 라인·구역 묶음."""

    cam_id: str
    lines: dict[str, VirtualLine] = field(default_factory=dict)
    zones: dict[str, Zone] = field(default_factory=dict)
    # 교차로 정의: {intersection_id: {"stop_line": id, "exit_line": id, "signal_id": id}}
    intersections: dict[str, dict[str, str]] = field(default_factory=dict)
    location: Optional[tuple[float, float]] = None   # (lat, lon)
    # 1인칭 게임 신호위반 데모에서만 True.
    # 일반 CCTV와 불법유턴 ROI에는 기본값 False가 유지된다.
    demo_moving_roi_active: bool = False

    def line(self, line_id: str) -> Optional[VirtualLine]:
        return self.lines.get(line_id)

    def uturn_zones(self) -> list[Zone]:
        return [z for z in self.zones.values() if z.zone_type == "uturn"]

    def center_lines(self) -> list[VirtualLine]:
        """중앙선(노란 실선) 목록. 유턴 판정의 1차 트리거로 쓴다."""
        return [l for l in self.lines.values() if l.line_type == "center"]


class ZoneRegistry:
    """카메라별 ROI 설정 저장소."""

    def __init__(self) -> None:
        self._cams: dict[str, CameraZones] = {}

    def add(self, cz: CameraZones) -> None:
        self._cams[cz.cam_id] = cz

    def get(self, cam_id: str) -> Optional[CameraZones]:
        return self._cams.get(cam_id)

    def cam_ids(self) -> list[str]:
        return list(self._cams)

    def __len__(self) -> int:
        return len(self._cams)

    # ------------------------------------------------------------------
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ZoneRegistry":
        reg = cls()
        for cam in data.get("cameras", []):
            cz = CameraZones(cam_id=cam["cam_id"])
            loc = cam.get("location")
            if loc and len(loc) == 2:
                cz.location = (float(loc[0]), float(loc[1]))

            for ln in cam.get("lines", []):
                cz.lines[ln["line_id"]] = VirtualLine(
                    line_id=ln["line_id"],
                    p1=tuple(ln["p1"]), p2=tuple(ln["p2"]),
                    name=ln.get("name", ""), direction=ln.get("direction", "both"),
                    line_type=ln.get("line_type", "stop"),
                    uturn_allowed=bool(ln.get("uturn_allowed", False)),
                    signal_id=ln.get("signal_id", ""),
                )
            for z in cam.get("zones", []):
                cz.zones[z["zone_id"]] = Zone(
                    zone_id=z["zone_id"],
                    polygon=[tuple(p) for p in z["polygon"]],
                    name=z.get("name", ""),
                    zone_type=z.get("zone_type", "generic"),
                    uturn_allowed=bool(z.get("uturn_allowed", False)),
                )
            for it in cam.get("intersections", []):
                cz.intersections[it["intersection_id"]] = {
                    "stop_line": it["stop_line"],
                    "exit_line": it.get("exit_line", ""),
                    "signal_id": it.get("signal_id", it["intersection_id"]),
                }
            reg.add(cz)
        return reg

    @classmethod
    def load(cls, path: str | Path) -> "ZoneRegistry":
        p = Path(path)
        if not p.exists():
            log.warning("ROI 설정 파일 없음(%s) → 기본 설정 사용", p)
            return default_registry()
        try:
            return cls.from_dict(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            log.exception("ROI 설정 로드 실패 → 기본 설정 사용")
            return default_registry()


def default_registry() -> ZoneRegistry:
    """설정 파일이 없을 때 쓰는 예시 구성 (1920x1080 기준)."""
    return ZoneRegistry.from_dict(
        {
            "cameras": [
                {
                    "cam_id": "CAM-001",
                    "location": [37.5665, 126.9780],
                    "lines": [
                        {"line_id": "stop_A", "name": "정지선(북→남)",
                         "p1": [300, 700], "p2": [1600, 700], "direction": "negative"},
                        {"line_id": "exit_A", "name": "진출선(북→남)",
                         "p1": [300, 950], "p2": [1600, 950], "direction": "negative"},
                    ],
                    "zones": [
                        {"zone_id": "uturn_A", "name": "유턴 금지 구간",
                         "zone_type": "uturn", "uturn_allowed": False,
                         "polygon": [[250, 600], [1650, 600], [1650, 1020], [250, 1020]]},
                    ],
                    "intersections": [
                        {"intersection_id": "INT-A", "stop_line": "stop_A",
                         "exit_line": "exit_A", "signal_id": "SIG-A"},
                    ],
                }
            ]
        }
    )
