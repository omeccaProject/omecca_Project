"""신호위반 / 불법유턴 판정 로직.

두 판정 모두 '가상 라인 통과 방향·순서' 와 '궤적 형태' 를 근거로 한다.
단일 프레임 판단이 아니라 궤적 누적으로 판정하므로 오탐이 적다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from ..core.config import settings
from ..core.geometry import angle_diff, dist, mean_heading, path_length, smooth
from ..core.schemas import ViolationType
from .roi import CameraZones, Zone
from .signal_state import SignalPhase, SignalProvider
from .trajectory import Track

log = logging.getLogger("omeca.violation.detectors")


@dataclass
class Verdict:
    """판정 결과."""

    violated: bool
    violation_type: Optional[ViolationType] = None
    zone_id: str = ""
    detail: str = ""
    frames: list[int] = None

    def __post_init__(self) -> None:
        if self.frames is None:
            self.frames = []


# ==========================================================================
# 신호 위반
# ==========================================================================
class RedLightDetector:
    """정지선 → 진출선 통과 순서와 그 시점의 신호 상태로 판정한다.

    판정 절차
      1. 차량이 정지선(stop_line)을 진행 방향으로 통과한 시점 기록
      2. 그 시점의 신호가 RED 이면 후보로 등록
         (신호 전환 직후 grace 시간 내 통과는 딜레마 존으로 보고 제외)
      3. 이어서 진출선(exit_line)까지 통과하면 위반 확정
         → 정지선만 살짝 밟고 멈춘 차량을 위반으로 잡지 않기 위함
      4. 진출선이 설정되지 않은 카메라는 정지선 통과 후 일정 거리
         이상 진행한 것으로 대체 판정한다.
    """

    def __init__(
        self,
        signal_provider: SignalProvider,
        grace_sec: Optional[float] = None,
        min_speed: Optional[float] = None,
        exit_timeout_sec: float = 6.0,
        fallback_advance_px: float = 90.0,
    ) -> None:
        cfg = settings.violation
        self.signal = signal_provider
        self.grace_sec = cfg.redlight_grace_sec if grace_sec is None else grace_sec
        self.min_speed = cfg.min_cross_speed if min_speed is None else min_speed
        self.exit_timeout_sec = exit_timeout_sec
        self.fallback_advance_px = fallback_advance_px
        # (cam_id, track_id, intersection_id) -> (정지선 통과 시각, frame, 통과 지점)
        self._pending: dict[tuple[str, int, str], tuple[float, int, tuple[float, float]]] = {}

    # ------------------------------------------------------------------
    @staticmethod
    def _cross(track: Track, line, p_cur) -> Optional[int]:
        """상태를 유지하며 라인 통과 방향을 판정한다.

        차량 좌표가 라인 위에 정확히 놓이는 프레임이 있어도 통과를 놓치지 않도록
        마지막으로 부호가 확정된 지점을 track에 보관해 두고 비교한다.
        """
        s_cur = line.side(p_cur)
        if s_cur == 0:
            return None  # 라인 위 → 판정 보류(직전 상태 유지)
        st = track.line_state.get(line.line_id)
        track.line_state[line.line_id] = (s_cur, p_cur)
        if st is None:
            return None
        prev_side, prev_pt = st
        return line.crossed_from(prev_pt, prev_side, p_cur)

    # ------------------------------------------------------------------
    def check(self, track: Track, cz: CameraZones) -> Optional[Verdict]:
        last, prev = track.last, track.prev
        if last is None or prev is None:
            return None
        if track.speed() < self.min_speed:
            return None

        p_cur = last.as_xy()

        for int_id, spec in cz.intersections.items():
            stop_line = cz.line(spec["stop_line"])
            if stop_line is None:
                continue
            key = (track.cam_id, track.track_id, int_id)
            exit_line = cz.line(spec.get("exit_line", "")) if spec.get("exit_line") else None

            # 상태 갱신은 매 프레임 수행해야 하므로 두 라인 모두 먼저 평가한다
            stop_cross = self._cross(track, stop_line, p_cur)
            exit_cross = self._cross(track, exit_line, p_cur) if exit_line else None

            # --- 1) 정지선 통과 감지 -----------------------------------
            if stop_cross is not None and stop_line.is_forward(stop_cross):
                track.crossings[stop_line.line_id] = (stop_cross, last.ts, last.frame_no)
                sig_id = spec.get("signal_id", int_id)
                phase = self.signal.phase_at(sig_id, last.ts)
                if phase is SignalPhase.RED:
                    changed_at = self.signal.last_change(sig_id, last.ts)
                    if last.ts - changed_at >= self.grace_sec:
                        self._pending[key] = (last.ts, last.frame_no, p_cur)
                        log.debug("정지선 적색 통과 후보: %s track=%s", int_id, track.track_id)
                    else:
                        log.debug("신호 전환 직후 유예 적용: track=%s", track.track_id)
                continue

            # --- 2) 진출선 통과로 위반 확정 -----------------------------
            pend = self._pending.get(key)
            if pend is None:
                continue
            start_ts, start_frame, start_pt = pend

            if last.ts - start_ts > self.exit_timeout_sec:
                del self._pending[key]      # 정지선 넘고 멈춰 섰다 → 위반 아님
                continue

            if exit_line is not None:
                confirmed = exit_cross is not None and exit_line.is_forward(exit_cross)
            else:
                confirmed = dist(start_pt, p_cur) >= self.fallback_advance_px

            if not confirmed:
                continue

            del self._pending[key]
            elapsed = last.ts - start_ts
            return Verdict(
                violated=True,
                violation_type=ViolationType.RED_LIGHT,
                zone_id=int_id,
                detail=(
                    f"적색 신호 중 정지선 통과 후 교차로 진출 "
                    f"(정지선→진출 {elapsed:.1f}초, 평균 {track.speed():.1f}px/f)"
                ),
                frames=[start_frame, last.frame_no],
            )
        return None

    def reset(self) -> None:
        self._pending.clear()


# ==========================================================================
# 불법 유턴
# ==========================================================================
class UTurnDetector:
    """진입 방향과 진출 방향의 각도 차로 유턴을 판정한다.

    판정 절차
      1. 유턴 금지 ROI 안에 있는 궤적 구간을 추출
      2. 구간 전반부 평균 진행 방향 vs 후반부 평균 진행 방향 비교
      3. 각도 차가 임계값(기본 150도) 이상이고
         이동 거리·속도가 충분하면 유턴으로 판정
      4. 좌/우회전은 각도 차가 90도 부근이라 임계값에서 자연히 걸러진다
    """

    def __init__(
        self,
        angle_threshold: Optional[float] = None,
        min_points: Optional[int] = None,
        min_speed: Optional[float] = None,
        min_path_px: float = 60.0,
    ) -> None:
        cfg = settings.violation
        self.angle_threshold = cfg.uturn_angle_deg if angle_threshold is None else angle_threshold
        self.min_points = cfg.uturn_min_points if min_points is None else min_points
        self.min_speed = cfg.uturn_min_speed if min_speed is None else min_speed
        self.min_path_px = min_path_px

    # ------------------------------------------------------------------
    def check(self, track: Track, cz: CameraZones) -> Optional[Verdict]:
        if len(track) < self.min_points:
            return None
        if track.speed() < self.min_speed:
            return None

        for zone in cz.uturn_zones():
            if zone.uturn_allowed:
                continue
            verdict = self._check_zone(track, zone)
            if verdict is not None:
                return verdict
        return None

    # ------------------------------------------------------------------
    def _check_zone(self, track: Track, zone: Zone) -> Optional[Verdict]:
        pts = track.xy_list()
        frames = track.frames()
        inside = [i for i, p in enumerate(pts) if zone.contains(p)]
        if len(inside) < self.min_points:
            return None

        lo, hi = inside[0], inside[-1] + 1
        seg = smooth(pts[lo:hi], 3)
        if len(seg) < self.min_points:
            return None
        if path_length(seg) < self.min_path_px:
            return None

        half = len(seg) // 2
        h_in = mean_heading(seg[:half])
        h_out = mean_heading(seg[half:])
        if h_in is None or h_out is None:
            return None

        diff = angle_diff(h_in, h_out)
        if diff < self.angle_threshold:
            return None

        # 실제로 되돌아왔는지 확인: 시작점과 끝점 거리가 이동 거리에 비해 짧아야 한다
        straightness = dist(seg[0], seg[-1]) / max(path_length(seg), 1e-6)
        if straightness > 0.5:
            return None

        return Verdict(
            violated=True,
            violation_type=ViolationType.ILLEGAL_UTURN,
            zone_id=zone.zone_id,
            detail=(
                f"유턴 금지 구간 내 진행 방향 반전 감지 "
                f"(진입 {h_in:.0f}° → 진출 {h_out:.0f}°, 각도차 {diff:.0f}°)"
            ),
            frames=[frames[lo], frames[min(hi, len(frames)) - 1]],
        )
