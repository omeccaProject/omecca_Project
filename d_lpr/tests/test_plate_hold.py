"""번호판 확정 대기 전송(`app.core.plate_hold`) 검증.

지키려는 것은 세 가지다.

1. 발행 시점에 번호판이 이미 있으면 기다리지 않고 바로 보낸다.
2. 번호판이 없으면 보류했다가, 확정되는 순간 **그 번호판을 실어서** 보낸다.
   → 이게 없으면 대시보드 이벤트 리포트의 "차량 번호판"이 빈 채로 굳는다.
3. 끝내 확정되지 않아도 대기 시간이 지나면 **반드시** 보낸다.
   → 번호판을 못 읽었다고 위반 이벤트 자체가 사라지면 안 된다.
"""

from __future__ import annotations

import pytest

from app.core.bus import TOPIC_VIOLATION, bus
from app.core.plate_hold import PlateHoldForwarder


class FakeGateway:
    """GatewayClient 대역. enqueue 된 payload 를 그대로 모아 둔다."""

    def __init__(self):
        self.sent: list[dict] = []

    def enqueue(self, payload):
        self.sent.append(payload)
        return True


class FakeLPR:
    """LPRPipeline 대역. 테스트가 원하는 시점에 번호판을 '확정' 시킨다."""

    def __init__(self):
        self.plates: dict[tuple[str, int], str] = {}

    def confirm(self, cam_id, track_id, plate_no):
        self.plates[(cam_id, int(track_id))] = plate_no

    def confirmed_plate(self, cam_id, track_id):
        return self.plates.get((cam_id, int(track_id)))

    def confidence_of(self, cam_id, track_id):
        return 0.91 if (cam_id, int(track_id)) in self.plates else 0.0


def make_payload(plate_no="", ts=10.0, cam_id="CAM-T", track_id=7):
    """버스에 흐르는 ViolationEvent.to_payload() 와 같은 모양."""
    return {
        "event_id": "ev-1",
        "type": "illegal_uturn",
        "cam_id": cam_id,
        "track_id": track_id,
        "timestamp": ts,
        "plate_no": plate_no,
        "plate_confidence": 0.0,
        "risk_level": "normal",
        "vehicle_status": "registered",
        "zone_id": "center-1",
        "subtype": "no_sign",
        "detail": "중앙선 통과",
        "evidence_frames": [],
        "trajectory": [],
        "location": None,
    }


@pytest.fixture
def rig():
    gw, lpr = FakeGateway(), FakeLPR()
    fwd = PlateHoldForwarder(gateway=gw, lpr=lpr, hold_sec=2.0).attach()
    yield gw, lpr, fwd
    fwd.detach()
    bus.clear()


class TestPlateHold:
    def test_번호판이_있으면_즉시_보낸다(self, rig):
        gw, _lpr, fwd = rig
        bus.publish(TOPIC_VIOLATION, make_payload(plate_no="12가3456"))

        assert len(gw.sent) == 1
        assert gw.sent[0]["meta"]["plateNumber"] == "12가3456"
        assert fwd.pending_count == 0
        assert fwd.stats["immediate"] == 1

    def test_번호판이_없으면_보류한다(self, rig):
        gw, _lpr, fwd = rig
        bus.publish(TOPIC_VIOLATION, make_payload(plate_no="", ts=10.0))

        assert gw.sent == []
        assert fwd.pending_count == 1

        fwd.tick(11.0)          # 아직 대기 시간(2초) 안
        assert gw.sent == []

    def test_보류_중_확정되면_그_번호판을_실어_보낸다(self, rig):
        gw, lpr, fwd = rig
        bus.publish(TOPIC_VIOLATION, make_payload(plate_no="", ts=10.0))

        lpr.confirm("CAM-T", 7, "34나5678")
        fwd.tick(10.5)

        assert len(gw.sent) == 1
        assert gw.sent[0]["meta"]["plateNumber"] == "34나5678"
        assert gw.sent[0]["meta"]["plateConfidence"] == 0.91
        assert fwd.stats["resolved"] == 1
        assert fwd.pending_count == 0

    def test_대기시간이_지나면_번호판_없이라도_보낸다(self, rig):
        gw, _lpr, fwd = rig
        bus.publish(TOPIC_VIOLATION, make_payload(plate_no="", ts=10.0))

        fwd.tick(12.5)          # hold_sec=2.0 초과

        assert len(gw.sent) == 1
        assert gw.sent[0]["meta"]["plateNumber"] is None
        assert gw.sent[0]["eventType"] == "UTURN_VIOLATION"   # 이벤트는 살아 있어야 한다
        assert fwd.stats["timeout"] == 1

    def test_flush_는_남은_보류를_전부_내보낸다(self, rig):
        gw, _lpr, fwd = rig
        bus.publish(TOPIC_VIOLATION, make_payload(plate_no="", ts=10.0, track_id=1))
        bus.publish(TOPIC_VIOLATION, make_payload(plate_no="", ts=10.0, track_id=2))
        assert fwd.pending_count == 2

        fwd.flush()

        assert len(gw.sent) == 2
        assert fwd.pending_count == 0

    def test_위반이_아닌_토픽은_건드리지_않는다(self, rig):
        gw, _lpr, fwd = rig
        bus.publish("lpr.plate", {"plate_no": "99하1111"})

        assert gw.sent == []
        assert fwd.pending_count == 0

    def test_detach_후에는_받지_않는다(self, rig):
        gw, _lpr, fwd = rig
        fwd.detach()
        bus.publish(TOPIC_VIOLATION, make_payload(plate_no="12가3456"))

        assert gw.sent == []
