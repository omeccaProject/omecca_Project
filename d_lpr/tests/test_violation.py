"""신호위반 / 불법유턴 판정 및 엔진 통합 테스트."""

import time

import pytest

from app.core.bus import TOPIC_VIOLATION, bus
from app.core.schemas import ViolationType
from app.simulator import left_turn, straight_down, uturn_path
from app.violation.signal_state import FixedCycleSignal, PedPhase, SignalPhase


def feed(engine, scenario_points, cam_id="CAM-001", track_id=1, plate=None, t0=None):
    """궤적을 엔진에 흘려 넣고 발생한 이벤트를 모은다."""
    from app.core.schemas import BBox, Detection, ObjectClass

    t0 = t0 or time.time()
    events = []
    for i, (x, y) in enumerate(scenario_points):
        d = Detection(
            cam_id=cam_id, track_id=track_id, cls=ObjectClass.CAR,
            bbox=BBox(x - 45, y - 120, x + 45, y),
            timestamp=t0 + i * 0.1, frame_no=i,
        )
        events.extend(engine.process(d, frame=None, plate_hint=plate))
    return events


def types_of(events):
    return [e.violation_type for e in events]


class TestRedLight:
    def test_violation_on_red(self, engine, signal):
        t0 = time.time()
        signal.update("SIG-A", SignalPhase.RED, ts=t0 - 5)
        evs = feed(engine, straight_down(760, 480, 1030), plate="12가3456", t0=t0)
        assert ViolationType.RED_LIGHT in types_of(evs)

    def test_no_violation_on_green(self, engine, signal):
        t0 = time.time()
        signal.update("SIG-A", SignalPhase.GREEN, ts=t0 - 5)
        evs = feed(engine, straight_down(760, 480, 1030), plate="12가3456", t0=t0)
        assert ViolationType.RED_LIGHT not in types_of(evs)

    def test_no_violation_on_yellow(self, engine, signal):
        t0 = time.time()
        signal.update("SIG-A", SignalPhase.YELLOW, ts=t0 - 5)
        evs = feed(engine, straight_down(760, 480, 1030), plate="12가3456", t0=t0)
        assert ViolationType.RED_LIGHT not in types_of(evs)

    def test_grace_period_after_signal_change(self, engine, signal):
        """신호가 막 적색으로 바뀐 직후(딜레마 존) 통과는 위반으로 잡지 않는다."""
        t0 = time.time()
        signal.update("SIG-A", SignalPhase.RED, ts=t0 + 0.95)  # 정지선 통과 직전 전환
        evs = feed(engine, straight_down(760, 480, 1030), plate="12가3456", t0=t0)
        assert ViolationType.RED_LIGHT not in types_of(evs)

    def test_stop_before_exit_line_is_not_violation(self, engine, signal):
        """정지선을 살짝 넘고 멈춘 차량은 위반이 아니다."""
        t0 = time.time()
        signal.update("SIG-A", SignalPhase.RED, ts=t0 - 5)
        pts = straight_down(760, 480, 730)          # 정지선 직후에서 종료
        pts += [(760, 730)] * 5                     # 정지
        evs = feed(engine, pts, plate="12가3456", t0=t0)
        assert ViolationType.RED_LIGHT not in types_of(evs)

    def test_reverse_direction_not_counted(self, engine, signal):
        """역방향(남→북) 통과는 해당 정지선의 위반 대상이 아니다."""
        t0 = time.time()
        signal.update("SIG-A", SignalPhase.RED, ts=t0 - 5)
        pts = list(reversed(straight_down(760, 480, 1030)))
        evs = feed(engine, pts, plate="12가3456", t0=t0)
        assert ViolationType.RED_LIGHT not in types_of(evs)

    def test_cooldown_blocks_repeat(self, engine, signal):
        t0 = time.time()
        signal.update("SIG-A", SignalPhase.RED, ts=t0 - 5)
        pts = straight_down(760, 480, 1030) + straight_down(760, 480, 1030)
        evs = feed(engine, pts, plate="12가3456", t0=t0)
        assert types_of(evs).count(ViolationType.RED_LIGHT) == 1


class TestUTurn:
    """중앙선(노란 실선) 통과를 트리거로 하는 유턴 판정.

    좌표는 config_zones.json 기준.
      CAM-001 center_A  : x=800 세로선, 유턴 금지
      CAM-002 center_B  : x=1300 세로선, 유턴 허용(표지판)
      CAM-002 center_B2 : x=400 세로선, 유턴 금지
    """

    def uturn_of(self, evs):
        return [e for e in evs if e.violation_type is ViolationType.ILLEGAL_UTURN]

    # --- 금지 구간 ----------------------------------------------------
    def test_uturn_without_sign_is_violation(self, engine):
        """유턴 표지가 없는 중앙선을 넘어 유턴 → 신호와 무관하게 위반."""
        evs = feed(engine, uturn_path(900, 700, 640, 960), track_id=11, plate="44자4444")
        found = self.uturn_of(evs)
        assert found, "금지 구간 유턴이 검출되지 않았다"
        assert found[0].subtype == "no_sign"
        assert found[0].zone_id == "center_A"

    def test_uturn_in_forbidden_side_of_same_camera(self, engine):
        pts = uturn_path(500, 300, 250, 850)
        evs = feed(engine, pts, cam_id="CAM-002", track_id=15, plate="12가3456")
        found = self.uturn_of(evs)
        assert found and found[0].subtype == "no_sign"

    # --- 허용 구간: 신호에 따라 갈린다 --------------------------------
    def _allowed_zone(self, engine, signal, phase, track_id, ped=None):
        t0 = time.time()
        signal.update("SIG-B", phase, ts=t0 - 5)
        if ped is not None:
            signal.update_ped("SIG-B", ped)
        evs = feed(engine, uturn_path(1400, 1200, 250, 850),
                   cam_id="CAM-002", track_id=track_id, plate="12가3456", t0=t0)
        return self.uturn_of(evs)

    def test_uturn_on_left_arrow_is_legal(self, engine, signal):
        assert not self._allowed_zone(engine, signal, SignalPhase.LEFT_ARROW, 31)

    def test_uturn_on_green_left_is_legal(self, engine, signal):
        assert not self._allowed_zone(engine, signal, SignalPhase.GREEN_LEFT, 32)

    def test_uturn_on_straight_green_is_wrong_signal(self, engine, signal):
        """직진 녹색만 켜진 곳에서의 유턴은 위반."""
        found = self._allowed_zone(engine, signal, SignalPhase.GREEN, 33)
        assert found and found[0].subtype == "wrong_signal"

    def test_uturn_on_red_is_violation(self, engine, signal):
        found = self._allowed_zone(engine, signal, SignalPhase.RED, 34)
        assert found and found[0].subtype == "red_light"

    def test_uturn_on_ped_green_is_legal(self, engine, signal):
        """보행 녹색에 유턴을 허용하는 교차로 (보행신호 연동 가정)."""
        assert not self._allowed_zone(engine, signal, SignalPhase.GREEN, 35,
                                      ped=PedPhase.GREEN)

    def test_unknown_signal_is_not_judged(self, engine, signal):
        """신호를 모르면 위반으로 단정하지 않는다."""
        assert not self._allowed_zone(engine, signal, SignalPhase.UNKNOWN, 36)

    # --- 반례: 유턴이 아닌 궤적 ---------------------------------------
    def test_straight_is_not_uturn(self, engine):
        evs = feed(engine, straight_down(1150, 480, 1030), track_id=12, plate="34나5678")
        assert not self.uturn_of(evs)

    def test_left_turn_is_not_uturn(self, engine):
        """좌회전은 중앙선을 넘더라도 방향 반전이 아니므로 유턴이 아니다."""
        evs = feed(engine, left_turn(1300, 480, 900, 500), track_id=13, plate="56다7890")
        assert not self.uturn_of(evs)

    def test_stationary_vehicle_ignored(self, engine):
        evs = feed(engine, [(900, 800)] * 40, track_id=16, plate="12가3456")
        assert not self.uturn_of(evs)

    def test_crossing_center_line_alone_is_not_uturn(self, engine):
        """중앙선을 넘기만 하고 그대로 직진하면 유턴이 아니다."""
        pts = [(900 - i * 12, 800) for i in range(30)]     # 좌측으로 가로지르기만 함
        evs = feed(engine, pts, track_id=17, plate="12가3456")
        assert not self.uturn_of(evs)


class TestEngineIntegration:
    def test_high_risk_alert_during_normal_drive(self, engine, signal):
        t0 = time.time()
        signal.update("SIG-A", SignalPhase.GREEN, ts=t0 - 5)
        evs = feed(engine, straight_down(880, 480, 1030), track_id=21, plate="33아3333", t0=t0)
        assert ViolationType.HIGH_RISK_VEHICLE in types_of(evs)

    def test_events_published_to_bus(self, engine, signal):
        t0 = time.time()
        signal.update("SIG-A", SignalPhase.RED, ts=t0 - 5)
        feed(engine, straight_down(760, 480, 1030), track_id=22, plate="12가3456", t0=t0)
        assert len(bus.recent(TOPIC_VIOLATION, limit=50)) >= 1

    def test_events_persisted_with_plate(self, engine, repo, signal):
        t0 = time.time()
        signal.update("SIG-A", SignalPhase.RED, ts=t0 - 5)
        feed(engine, straight_down(760, 480, 1030), track_id=23, plate="12가3456", t0=t0)
        rows = repo.recent_violations(limit=10, violation_type="red_light")
        assert rows and rows[0]["plate_no"] == "12가3456"

    def test_evidence_frames_recorded(self, engine, signal):
        t0 = time.time()
        signal.update("SIG-A", SignalPhase.RED, ts=t0 - 5)
        evs = feed(engine, straight_down(760, 480, 1030), track_id=24, plate="12가3456", t0=t0)
        red = [e for e in evs if e.violation_type is ViolationType.RED_LIGHT][0]
        assert len(red.evidence_frames) == 2
        assert red.evidence_frames[0] < red.evidence_frames[1]
        assert red.trajectory                       # 궤적이 함께 저장된다
        assert red.location is not None             # GIS 좌표 포함

    def test_unknown_camera_is_ignored(self, engine):
        evs = feed(engine, straight_down(760, 480, 1030), cam_id="CAM-999", track_id=25)
        assert not [e for e in evs if e.violation_type is not ViolationType.HIGH_RISK_VEHICLE]


class TestFixedCycleSignal:
    @pytest.mark.parametrize("t,expected", [
        (0, SignalPhase.GREEN),
        (29, SignalPhase.GREEN),
        (31, SignalPhase.YELLOW),
        (40, SignalPhase.RED),
        (60, SignalPhase.GREEN),
    ])
    def test_phase_cycle(self, t, expected):
        s = FixedCycleSignal(green_sec=30, yellow_sec=4, red_sec=26, offset=0)
        assert s.phase_at("SIG", t) is expected

    def test_last_change(self):
        s = FixedCycleSignal(green_sec=30, yellow_sec=4, red_sec=26, offset=0)
        assert s.last_change("SIG", 40) == pytest.approx(34)


class TestSyntheticScene:
    """합성 장면 전체 검증.

    유턴 1대 · 좌회전 1대 · 직진 1대가 같은 화면에 있을 때
    유턴 1건만 잡히는지 본다. `run_uturn.py --fake` 와 같은 시나리오다.
    """

    def _run_scene(self, repo, matcher, signal=None):
        """합성 4대 장면을 엔진에 흘려 넣고 나온 위반을 모은다."""
        from app.core.schemas import BBox, Detection, ObjectClass
        from app.lpr.pipeline import LPRPipeline
        from app.lpr.recognizer import PlateRecognizer
        from app.violation.engine import ViolationEngine
        from app.violation.roi import ZoneRegistry
        from app.violation.signal_state import TimelineSignal
        from app.violation.synthetic import ACTORS, default_zone_dict

        engine = ViolationEngine(
            zones=ZoneRegistry.from_dict(default_zone_dict("CAM-FAKE")),
            signal_provider=signal or TimelineSignal(),
            lpr=LPRPipeline(recognizer=PlateRecognizer(mock=True), publish=False),
            matcher=matcher, repo=repo,
        )
        found = []
        for frame_no in range(150):
            ts = frame_no / 15.0
            for tid, fn, _ in ACTORS:
                xy = fn(ts)
                if xy is None:
                    continue
                x, y = xy
                d = Detection(cam_id="CAM-FAKE", track_id=tid, cls=ObjectClass.CAR,
                              bbox=BBox(x - 42, y - 105, x + 42, y),
                              timestamp=ts, frame_no=frame_no)
                found.extend(engine.process(d, frame=None))
        return found

    def test_both_violations_are_detected(self, repo, matcher):
        """⑦ 담당 두 가지가 한 번에 나와야 한다 — 유턴 1건 + 신호위반 1건.

        예전엔 실행기가 유턴만 담아서 신호위반이 조용히 버려졌다.
        """
        from app.violation.signal_state import TimelineSignal
        from app.violation.synthetic import fake_signal_timeline

        sig = TimelineSignal(fake_signal_timeline(), start_ts=0.0)
        found = self._run_scene(repo, matcher, signal=sig)

        uturn = [e for e in found if e.violation_type is ViolationType.ILLEGAL_UTURN]
        red = [e for e in found if e.violation_type is ViolationType.RED_LIGHT]

        assert len(uturn) == 1 and uturn[0].track_id == 101, \
            [(e.track_id, e.subtype) for e in uturn]
        assert len(red) == 1 and red[0].track_id == 104, \
            [(e.track_id, e.zone_id) for e in red]

    def test_left_turn_is_not_a_signal_violation(self, repo, matcher):
        """좌회전 차(#102)는 적색 구간을 지나도 신호위반이 아니다.

        정지선이 그 차로에 안 걸려 있기 때문. 배우마다 한 가지만 검증한다.
        """
        from app.violation.signal_state import TimelineSignal
        from app.violation.synthetic import fake_signal_timeline

        sig = TimelineSignal(fake_signal_timeline(), start_ts=0.0)
        found = self._run_scene(repo, matcher, signal=sig)
        assert 102 not in [e.track_id for e in found]
        assert 103 not in [e.track_id for e in found]

    def test_no_signal_means_no_red_light_event(self, repo, matcher):
        """신호를 모르면 신호위반은 안 낸다 (유턴 no_sign 은 그대로 나온다)."""
        found = self._run_scene(repo, matcher)          # 타임라인 비어 있음
        assert not [e for e in found if e.violation_type is ViolationType.RED_LIGHT]
        assert [e for e in found if e.violation_type is ViolationType.ILLEGAL_UTURN]

    def test_only_the_uturn_car_is_flagged(self, repo, matcher):
        from app.core.schemas import BBox, Detection, ObjectClass
        from app.lpr.pipeline import LPRPipeline
        from app.lpr.recognizer import PlateRecognizer
        from app.violation.engine import ViolationEngine
        from app.violation.roi import ZoneRegistry
        from app.violation.synthetic import ACTORS, default_zone_dict
        from app.violation.signal_state import TimelineSignal

        zones = ZoneRegistry.from_dict(default_zone_dict("CAM-FAKE"))
        engine = ViolationEngine(
            zones=zones, signal_provider=TimelineSignal(),
            lpr=LPRPipeline(recognizer=PlateRecognizer(mock=True), publish=False),
            matcher=matcher, repo=repo,
        )

        found = []
        for frame_no in range(150):
            ts = frame_no / 15.0
            for tid, fn, _ in ACTORS:
                xy = fn(ts)
                if xy is None:
                    continue
                x, y = xy
                d = Detection(cam_id="CAM-FAKE", track_id=tid, cls=ObjectClass.CAR,
                              bbox=BBox(x - 42, y - 105, x + 42, y),
                              timestamp=ts, frame_no=frame_no)
                for ev in engine.process(d, frame=None):
                    if ev.violation_type is ViolationType.ILLEGAL_UTURN:
                        found.append(ev)

        assert len(found) == 1, [(e.track_id, e.subtype) for e in found]
        assert found[0].track_id == 101       # 유턴 차량
        assert found[0].subtype == "no_sign"


    def test_uturn_after_waiting_at_the_light(self, repo, matcher):
        """신호 대기로 5초 정차했다가 유턴 — 실제 교차로에서 가장 흔한 형태.

        진입 방향을 '시간' 기준으로 되돌아가서 재면 정차 구간에 떨어져
        방향이 엉뚱하게 나온다. 이동 거리 기준이라야 잡힌다.
        """
        from app.core.schemas import BBox, Detection, ObjectClass
        from app.lpr.pipeline import LPRPipeline
        from app.lpr.recognizer import PlateRecognizer
        from app.violation.engine import ViolationEngine
        from app.violation.roi import ZoneRegistry
        from app.violation.synthetic import _uturn_after_wait_xy, default_zone_dict
        from app.violation.signal_state import TimelineSignal

        zones = ZoneRegistry.from_dict(default_zone_dict("CAM-FAKE"))
        engine = ViolationEngine(
            zones=zones, signal_provider=TimelineSignal(),
            lpr=LPRPipeline(recognizer=PlateRecognizer(mock=True), publish=False),
            matcher=matcher, repo=repo,
        )

        found = []
        for frame_no in range(int(13.5 * 15)):
            ts = frame_no / 15.0
            xy = _uturn_after_wait_xy(ts)
            if xy is None:
                continue
            x, y = xy
            d = Detection(cam_id="CAM-FAKE", track_id=201, cls=ObjectClass.CAR,
                          bbox=BBox(x - 42, y - 105, x + 42, y),
                          timestamp=ts, frame_no=frame_no)
            for ev in engine.process(d, frame=None):
                if ev.violation_type is ViolationType.ILLEGAL_UTURN:
                    found.append(ev)

        assert found, "신호 대기 후 유턴을 놓쳤다"
        assert found[0].subtype == "no_sign"
