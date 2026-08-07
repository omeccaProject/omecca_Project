"""신호위반 / 불법유턴 판정 및 엔진 통합 테스트."""

import time

import pytest

from app.core.bus import TOPIC_VIOLATION, bus
from app.core.schemas import ViolationType
from app.simulator import left_turn, straight_down, uturn_path
from app.violation.signal_state import FixedCycleSignal, SignalPhase


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
    def test_uturn_detected_in_forbidden_zone(self, engine):
        evs = feed(engine, uturn_path(900, 700, 640, 960), track_id=11, plate="44자4444")
        assert ViolationType.ILLEGAL_UTURN in types_of(evs)

    def test_straight_is_not_uturn(self, engine):
        evs = feed(engine, straight_down(1150, 480, 1030), track_id=12, plate="34나5678")
        assert ViolationType.ILLEGAL_UTURN not in types_of(evs)

    def test_left_turn_is_not_uturn(self, engine):
        evs = feed(engine, left_turn(1300, 480, 900, 500), track_id=13, plate="56다7890")
        assert ViolationType.ILLEGAL_UTURN not in types_of(evs)

    def test_uturn_allowed_zone_is_skipped(self, engine):
        """CAM-002 동측은 유턴 허용 구간이므로 판정에서 제외된다."""
        pts = uturn_path(1400, 1200, 250, 850)
        evs = feed(engine, pts, cam_id="CAM-002", track_id=14, plate="12가3456")
        assert ViolationType.ILLEGAL_UTURN not in types_of(evs)

    def test_uturn_in_forbidden_zone_of_same_camera(self, engine):
        pts = uturn_path(500, 300, 250, 850)
        evs = feed(engine, pts, cam_id="CAM-002", track_id=15, plate="12가3456")
        assert ViolationType.ILLEGAL_UTURN in types_of(evs)

    def test_stationary_vehicle_ignored(self, engine):
        evs = feed(engine, [(900, 800)] * 40, track_id=16, plate="12가3456")
        assert ViolationType.ILLEGAL_UTURN not in types_of(evs)


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
