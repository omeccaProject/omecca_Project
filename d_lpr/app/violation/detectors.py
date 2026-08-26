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
from .roi import VirtualLine
from .signal_state import (
    UTURN_ALLOWED_PHASES, Movement, PedPhase, SignalPhase, SignalProvider,
)
from .trajectory import Track

log = logging.getLogger("omeca.violation.detectors")


@dataclass
class Verdict:
    """판정 결과."""

    violated: bool
    violation_type: Optional[ViolationType] = None
    zone_id: str = ""
    detail: str = ""
    # 유턴 위반 세부 유형 (발표·통계용)
    #   no_sign      : 유턴 표지 없는 구간에서 유턴
    #   wrong_signal : 좌회전 신호가 아닌데 유턴
    #   red_light    : 적색 신호에 유턴
    subtype: str = ""
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
    def _cross(
        track: Track,
        line,
        p_cur,
        moving_roi: bool = False,
    ) -> Optional[int]:
        """차량 또는 데모용 이동 ROI의 선 통과를 판정한다."""

        s_cur = line.side(p_cur)

        if s_cur == 0:
            return None

        st = track.line_state.get(line.line_id)
        track.line_state[line.line_id] = (s_cur, p_cur)

        if st is None:
            return None

        prev_side, prev_pt = st

        # 1인칭 게임 데모:
        # 이전 프레임의 ROI 기준 부호와 현재 ROI 기준 부호가 바뀌면,
        # 차량이 아니라 이동한 ROI가 차량 기준점을 지나간 것으로 판단한다.
        # 고정 CCTV에서는 이 분기가 절대 실행되지 않는다.
        if moving_roi:
            if prev_side == s_cur:
                return None
            return 1 if prev_side > 0 else -1

        # 실제 CCTV: 기존 고정 ROI 교차 판정
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
            moving_roi = cz.demo_moving_roi_active

            stop_cross = self._cross(
                track, stop_line, p_cur, moving_roi=moving_roi
            )

            exit_cross = (
                self._cross(track, exit_line, p_cur, moving_roi=moving_roi)
                if exit_line else None
            )

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
    """중앙선(노란 실선) 통과를 1차 트리거로 삼는 유턴 판정.

    정상 주행에서 중앙 실선을 넘는 일은 거의 없다. 그래서 '선을 넘었다'는
    사건 자체가 강력한 신호다. 다만 선을 넘는다고 모두 유턴은 아니므로
    (불법 좌회전, 회차 등) 넘은 **그 차량만 짧게** 더 지켜보고 확정한다.

    판정 절차
      1. 차량이 중앙선을 넘는 순간을 잡는다                → 후보 등록
      2. 그 차량만 confirm_sec 동안 진행 방향 변화를 본다   → 유턴 여부
      3. 방향이 반전됐고 되돌아왔으면 유턴으로 확정
      4. 그 시점의 신호·표지 조건으로 합법/불법을 가른다

    전 차량을 계속 추적하지 않는다. 화면에 40대가 있어도 실제로 지켜보는
    것은 선을 넘은 1~2대뿐이다.

    위반 유형 (subtype)
      no_sign      : 유턴 표지가 없는 구간에서 유턴 (신호 무관 · 항상 위반)
      red_light    : 적색 신호에 유턴
      wrong_signal : 좌회전 화살표가 아닌데 유턴 (직진 녹색 중 유턴 등)
    """

    def __init__(
        self,
        signal_provider: Optional[SignalProvider] = None,
        angle_threshold: Optional[float] = None,
        min_speed: Optional[float] = None,
        confirm_sec: Optional[float] = None,
        min_points_after: int = 5,
        min_path_px: Optional[float] = None,
        use_ped_signal: Optional[bool] = None,
    ) -> None:
        cfg = settings.violation
        self.signal = signal_provider
        self.angle_threshold = cfg.uturn_angle_deg if angle_threshold is None else angle_threshold
        self.min_speed = cfg.uturn_min_speed if min_speed is None else min_speed
        self.confirm_sec = cfg.uturn_confirm_sec if confirm_sec is None else confirm_sec
        self.min_points_after = min_points_after
        self.min_path_px = cfg.uturn_min_path_px if min_path_px is None else min_path_px
        self.use_ped_signal = (cfg.uturn_use_ped_signal
                               if use_ped_signal is None else use_ped_signal)
        self.heading_window = cfg.uturn_heading_window
        self.lookback_px = cfg.uturn_lookback_px
        self.lookback_cars = cfg.uturn_lookback_cars
        self.min_move_px = cfg.uturn_min_move_px
        # (cam_id, track_id, line_id) -> (통과 시각, 통과 frame, 통과 전 진행방향)
        self._pending: dict[tuple[str, int, str], tuple[float, int, float]] = {}

    # ------------------------------------------------------------------
    def check(self, track: Track, cz: CameraZones) -> Optional[Verdict]:
        last, prev = track.last, track.prev
        if last is None or prev is None:
            return None

        p_cur = last.as_xy()

        for line in cz.center_lines():
            key = (track.cam_id, track.track_id, line.line_id)
            crossed = RedLightDetector._cross(track, line, p_cur)

            # --- 1) 중앙선 통과 → 후보 등록 ---------------------------
            if crossed is not None:
                if track.speed() < self.min_speed:
                    continue        # 정차 중 좌표 흔들림 무시
                heading_in = self._approach_heading(track)
                if heading_in is None:
                    continue
                self._pending[key] = (last.ts, last.frame_no, heading_in)
                log.debug("중앙선 통과 후보: %s track=%s", line.line_id, track.track_id)
                continue

            # --- 2) 통과한 차량만 짧게 확인 ---------------------------
            pend = self._pending.get(key)
            if pend is None:
                continue
            cross_ts, cross_frame, heading_in = pend

            if last.ts - cross_ts > self.confirm_sec:
                del self._pending[key]      # 시간 내 방향 반전 없음 → 유턴 아님
                continue

            # 통과 이후 구간은 **시각**으로 자른다.
            # 궤적 버퍼는 오래된 점을 밀어내는 링버퍼라, 통과 시점의 '인덱스'를
            # 들고 있으면 버퍼가 한 바퀴 돈 뒤 엉뚱한 구간을 가리키게 된다.
            after = [p.as_xy() for p in track.points if p.ts >= cross_ts]
            if len(after) < self.min_points_after:
                continue
            if path_length(after) < self.min_path_px:
                continue

            # 진출 방향은 선회가 끝난 뒤 최근 구간에서 잰다
            tail = after[-self.heading_window:]
            heading_out = mean_heading(smooth(tail, 3))
            if heading_out is None:
                continue

            diff = angle_diff(heading_in, heading_out)
            if diff < self.angle_threshold:
                continue                    # 좌회전(약 90도) 등은 여기서 걸러진다

            del self._pending[key]
            return self._judge(track, line, heading_in, heading_out, diff,
                               cross_ts, cross_frame, last.ts, last.frame_no)
        return None

    # ------------------------------------------------------------------
    def _approach_heading(self, track: Track) -> Optional[float]:
        """중앙선을 넘기 **전**의 진행 방향.

        두 가지를 조심해야 한다.

        1. 선을 넘는 순간에는 이미 핸들을 꺾고 있다. 그 구간의 방향은 진입
           방향이 아니므로 조금 앞으로 되돌아가야 한다.
        2. 유턴하려는 차는 보통 **신호를 기다리며 정차**한다. 그래서 "몇 초 전"
           으로 되돌아가면 멈춰 있던 구간에 떨어져 방향이 엉뚱하게 나온다.

        그래서 시간이 아니라 **이동 거리**를 기준으로 되돌아간다. 멈춰 있던
        시간은 이동 거리가 0이라 자동으로 건너뛰어진다. 되돌아갈 거리는 화면상
        차량 크기에 맞춰 정하므로 4K든 720p든, 멀든 가깝든 같게 동작한다.
        """
        pts = track.xy_list()
        if len(pts) < 3:
            return None

        # 정지 구간 제거 — 신호 대기 중 좌표에는 방향 정보가 없다
        moving = [pts[0]]
        for p in pts[1:]:
            if dist(moving[-1], p) >= self.min_move_px:
                moving.append(p)
        if len(moving) < 2:
            return None

        # 통과 지점에서 선회 구간만큼 되돌아간다
        back = max(self.lookback_px, self.lookback_cars * track.car_size())
        acc = 0.0
        hi = 1
        for i in range(len(moving) - 1, 0, -1):
            acc += dist(moving[i - 1], moving[i])
            hi = i
            if acc >= back:
                break

        seg = moving[max(0, hi - self.heading_window): hi + 1]
        if len(seg) < 2:                       # 궤적이 짧으면 가진 것 중 가장 앞 구간
            seg = moving[: max(2, self.heading_window)]
        return mean_heading(smooth(seg, 3))

    # ------------------------------------------------------------------
    def _judge(self, track, line: VirtualLine, h_in: float, h_out: float,
               diff: float, cross_ts: float, cross_frame: int,
               now_ts: float, now_frame: int) -> Optional[Verdict]:
        """유턴은 확정. 이제 합법인지 불법인지 가른다."""
        base = (f"중앙선 통과 후 진행 방향 반전 "
                f"(진입 {h_in:.0f}° → 진출 {h_out:.0f}°, 각도차 {diff:.0f}°)")
        frames = [cross_frame, now_frame]

        def verdict(subtype: str, why: str) -> Verdict:
            return Verdict(
                violated=True, violation_type=ViolationType.ILLEGAL_UTURN,
                zone_id=line.line_id, subtype=subtype,
                detail=f"{why} — {base}", frames=frames,
            )

        # ① 유턴 표지가 없는 구간 → 신호와 무관하게 위반
        if not line.uturn_allowed:
            return verdict("no_sign", "유턴 금지 구간에서 유턴")

        # 여기부터는 유턴 허용 구간. 신호를 봐야 한다.
        if self.signal is None:
            return None                    # 신호 정보가 없으면 판정 보류
        sig_id = line.signal_id or line.line_id

        # ①-2 유턴 신호가 따로 오면 그게 가장 확실한 근거다.
        #     (KLID 실시간 신호 API는 유턴 신호를 방향별로 직접 준다)
        #     좌회전 화살표를 보고 "유턴도 되겠지" 추론할 필요가 없어진다.
        uturn_sig = self.signal.movement_at(sig_id, cross_ts, Movement.UTURN)
        if uturn_sig is SignalPhase.GREEN:
            return None                                  # 유턴 신호 녹색 → 합법
        if uturn_sig is SignalPhase.RED:
            return verdict("red_light", "유턴 신호가 적색인데 유턴")
        if uturn_sig is SignalPhase.YELLOW:
            return verdict("wrong_signal", "유턴 신호가 황색인데 유턴")

        # --- 유턴 신호를 못 받는 경우: 좌회전·보행 신호로 추론한다 ---
        phase = self.signal.phase_at(sig_id, cross_ts)

        if phase is SignalPhase.UNKNOWN:
            return None                    # 근거 없이 위반 처리하지 않는다

        # ② 적색 신호에 유턴
        if phase is SignalPhase.RED:
            return verdict("red_light", "적색 신호에 유턴")

        # ③ 좌회전 화살표가 켜진 상태면 합법
        if phase in UTURN_ALLOWED_PHASES:
            return None

        # ④ 보행 녹색이면 허용하는 교차로가 있다 (보행신호 연동 시)
        if self.use_ped_signal:
            ped = self.signal.ped_phase_at(sig_id, cross_ts)
            if ped is PedPhase.GREEN:
                return None

        # ⑤ 직진 녹색·황색 중 유턴 → 위반
        return verdict("wrong_signal", f"좌회전 신호가 아닌 상태({phase.value})에서 유턴")

    def reset(self) -> None:
        self._pending.clear()
