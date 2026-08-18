"""실시간 신호 API 연동 테스트.

실제 API를 부르지 않는다. `fetcher` 를 갈아 끼워 응답을 흉내 낸다.
그래야 인증키 없이도, 인터넷 없이도, 기관 서버가 죽어도 테스트가 돈다.
"""

from __future__ import annotations

import json

import pytest

from app.core.config import load_dotenv, mask
from app.violation.signal_api import (
    ApiMapping, ApiSignal, find_items, parse_response,
)
from app.violation.signal_state import PedPhase, SignalPhase


def mapping(**kw) -> ApiMapping:
    m = ApiMapping(
        url="http://example.invalid/svc",
        params={"numOfRows": "10"},
        phase_map={"1": "green", "2": "yellow", "3": "red", "4": "left_arrow"},
        ped_map={"1": "green", "2": "red"},
    )
    for k, v in kw.items():
        setattr(m, k, v)
    return m


def json_body(sid="INT-1", phase="1", remain=None, ped=None):
    item = {"itstId": sid, "signalState": phase}
    if remain is not None:
        item["remainTime"] = remain
    if ped is not None:
        item["pedSignalState"] = ped
    return json.dumps({"response": {"body": {"items": {"item": [item]}}}})


# ==========================================================================
class TestParsing:
    def test_parses_json(self):
        obj = parse_response(json_body())
        assert find_items(obj)[0]["itstId"] == "INT-1"

    def test_parses_xml(self):
        xml = ("<response><body><items>"
               "<item><itstId>A</itstId><signalState>3</signalState></item>"
               "<item><itstId>B</itstId><signalState>1</signalState></item>"
               "</items></body></response>")
        items = find_items(parse_response(xml))
        assert [i["itstId"] for i in items] == ["A", "B"]

    def test_strips_xml_namespace(self):
        xml = ('<ns:response xmlns:ns="http://x"><ns:item>'
               '<ns:itstId>A</ns:itstId></ns:item></ns:response>')
        assert find_items(parse_response(xml))[0]["itstId"] == "A"

    def test_explicit_items_path(self):
        obj = parse_response(json_body())
        assert find_items(obj, "response.body.items.item")[0]["itstId"] == "INT-1"

    def test_empty_body_is_not_an_error(self):
        assert parse_response("") == {}

    def test_korean_phase_words_without_mapping(self):
        """매핑에 없어도 흔한 한글 표기는 알아본다."""
        sig = ApiSignal(mapping(phase_map={}), api_key="k",
                        fetcher=lambda url: json_body(phase="적색"))
        sig.poll_once(now=100.0)
        assert sig.phase_at("INT-1", 100.0) is SignalPhase.RED


# ==========================================================================
class TestHistoryLookup:
    """API는 '지금'만 알지만 판정은 '과거 그 순간'을 묻는다."""

    def test_answers_a_past_timestamp(self):
        seq = ["1", "1", "3", "3"]          # 녹색 → 적색
        box = {"i": 0}

        def fetch(url):
            v = seq[min(box["i"], len(seq) - 1)]
            box["i"] += 1
            return json_body(phase=v)

        sig = ApiSignal(mapping(), api_key="k", fetcher=fetch)
        for t in (100.0, 101.0, 102.0, 103.0):
            sig.poll_once(now=t)

        # 폴링이 끝난 뒤에도 과거 시각을 되물을 수 있어야 한다
        assert sig.phase_at("INT-1", 100.5) is SignalPhase.GREEN
        assert sig.phase_at("INT-1", 103.0) is SignalPhase.RED

    def test_remaining_time_pins_the_transition(self):
        """잔여시간이 있으면 폴링 간격보다 정밀하게 전환 시각을 잡는다."""
        seq = [("1", 0.4), ("3", 30)]       # 100초에 녹색 잔여 0.4 → 101초에 적색
        box = {"i": 0}

        def fetch(url):
            p, r = seq[min(box["i"], len(seq) - 1)]
            box["i"] += 1
            return json_body(phase=p, remain=r)

        sig = ApiSignal(mapping(), api_key="k", fetcher=fetch)
        sig.poll_once(now=100.0)
        sig.poll_once(now=101.0)

        # 중간값(100.5)이 아니라 잔여시간으로 역산한 100.4 여야 한다
        assert sig.last_change("INT-1", 101.0) == pytest.approx(100.4)
        assert sig.phase_at("INT-1", 100.3) is SignalPhase.GREEN
        assert sig.phase_at("INT-1", 100.5) is SignalPhase.RED

    def test_falls_back_to_midpoint_without_remaining(self):
        seq = ["1", "3"]
        box = {"i": 0}

        def fetch(url):
            v = seq[min(box["i"], len(seq) - 1)]
            box["i"] += 1
            return json_body(phase=v)

        sig = ApiSignal(mapping(), api_key="k", fetcher=fetch)
        sig.poll_once(now=100.0)
        sig.poll_once(now=102.0)
        assert sig.last_change("INT-1", 102.0) == pytest.approx(101.0)

    def test_absurd_remaining_time_is_ignored(self):
        """잔여시간이 두 관측 사이를 벗어나면 믿지 않는다."""
        seq = [("1", 999), ("3", 10)]
        box = {"i": 0}

        def fetch(url):
            p, r = seq[min(box["i"], len(seq) - 1)]
            box["i"] += 1
            return json_body(phase=p, remain=r)

        sig = ApiSignal(mapping(), api_key="k", fetcher=fetch)
        sig.poll_once(now=100.0)
        sig.poll_once(now=101.0)
        assert sig.last_change("INT-1", 101.0) == pytest.approx(100.5)

    def test_pedestrian_phase(self):
        sig = ApiSignal(mapping(), api_key="k",
                        fetcher=lambda url: json_body(phase="1", ped="1"))
        sig.poll_once(now=100.0)
        assert sig.ped_phase_at("INT-1", 100.0) is PedPhase.GREEN


# ==========================================================================
class TestFailureIsHeldNotGuessed:
    """장애 시 판정 보류 — 신호를 모르는 채로 위반 딱지를 붙이지 않는다."""

    def test_stale_data_becomes_unknown(self):
        sig = ApiSignal(mapping(), api_key="k", max_age_sec=5.0,
                        fetcher=lambda url: json_body(phase="3"))
        sig.poll_once(now=100.0)
        assert sig.phase_at("INT-1", 103.0) is SignalPhase.RED     # 아직 신선
        assert sig.phase_at("INT-1", 120.0) is SignalPhase.UNKNOWN  # 20초 지남

    def test_network_error_keeps_serving_recent_data(self):
        state = {"fail": False}

        def fetch(url):
            if state["fail"]:
                raise OSError("연결 끊김")
            return json_body(phase="3")

        sig = ApiSignal(mapping(), api_key="k", fetcher=fetch)
        sig.poll_once(now=100.0)
        state["fail"] = True
        sig.poll_once(now=101.0)

        assert sig.stats["failed"] == 1
        assert sig.phase_at("INT-1", 101.0) is SignalPhase.RED      # 직전 값 유효
        assert sig.phase_at("INT-1", 200.0) is SignalPhase.UNKNOWN  # 오래되면 보류

    def test_unknown_signal_id_is_unknown(self):
        sig = ApiSignal(mapping(), api_key="k",
                        fetcher=lambda url: json_body(phase="3"))
        sig.poll_once(now=100.0)
        assert sig.phase_at("없는교차로", 100.0) is SignalPhase.UNKNOWN

    def test_garbage_response_does_not_crash(self):
        sig = ApiSignal(mapping(), api_key="k", fetcher=lambda url: "<<깨진 응답")
        assert sig.poll_once(now=100.0) == 0
        assert sig.stats["failed"] == 1
        assert sig.phase_at("INT-1", 100.0) is SignalPhase.UNKNOWN

    def test_error_body_without_items(self):
        """포털이 인증 실패를 200 + XML 에러로 주는 경우."""
        body = ("<OpenAPI_ServiceResponse><cmmMsgHeader>"
                "<returnReasonCode>30</returnReasonCode>"
                "</cmmMsgHeader></OpenAPI_ServiceResponse>")
        sig = ApiSignal(mapping(items_path="response.body.items.item"),
                        api_key="k", fetcher=lambda url: body)
        assert sig.poll_once(now=100.0) == 0
        assert sig.phase_at("INT-1", 100.0) is SignalPhase.UNKNOWN


# ==========================================================================
class TestConfigAndSecrets:
    def test_service_key_is_not_double_encoded(self):
        """포털 Encoding 키의 %2B 를 %252B 로 만들면 인증이 깨진다."""
        key = "abc%2Bdef%3D%3D"
        sig = ApiSignal(mapping(), api_key=key, fetcher=lambda url: "{}")
        url = sig.build_url()
        assert f"serviceKey={key}" in url
        assert "%252B" not in url

    def test_extra_params_are_appended(self):
        sig = ApiSignal(mapping(), api_key="k", fetcher=lambda url: "{}")
        assert "numOfRows=10" in sig.build_url()

    def test_not_ready_without_key(self, monkeypatch):
        # 실제 .env 가 있는 환경에서도 결과가 같아야 하므로 환경변수를 비운다
        monkeypatch.delenv("SIGNAL_API_KEY", raising=False)
        sig = ApiSignal(mapping(), api_key="", fetcher=lambda url: "{}")
        ok, why = sig.ready()
        assert not ok and "SIGNAL_API_KEY" in why

    def test_not_ready_without_url(self, monkeypatch):
        monkeypatch.delenv("SIGNAL_API_URL", raising=False)
        sig = ApiSignal(mapping(url=""), api_key="k", fetcher=lambda url: "{}")
        assert not sig.ready()[0]

    def test_key_comes_from_env_when_not_passed(self, monkeypatch):
        """인증키를 코드에 안 넘겨도 .env 에서 알아서 읽는다."""
        monkeypatch.setenv("SIGNAL_API_KEY", "env_key_123")
        sig = ApiSignal(mapping(), fetcher=lambda url: "{}")
        assert sig.key == "env_key_123"
        assert sig.ready()[0]

    def test_mask_hides_the_key(self):
        # 실제 키의 조각도 커밋되는 파일에 남기지 않는다. 형태만 흉내 낸 값.
        key = "AbCd1234efGH5678ijKL9012mnOP3456qrST7890uvWX"
        m = mask(key)
        assert key not in m and m.startswith("AbCd")

    def test_dotenv_reader(self, tmp_path, monkeypatch):
        f = tmp_path / ".env"
        f.write_text('# 주석\nexport SIGNAL_API_KEY=abc%2B==\n'
                     'X="따옴표 안 # 은 값"\nY=plain  # 뒤 주석\n', encoding="utf-8")
        monkeypatch.delenv("SIGNAL_API_KEY", raising=False)
        monkeypatch.delenv("X", raising=False)
        monkeypatch.delenv("Y", raising=False)
        assert load_dotenv(f) == 3
        import os
        assert os.environ["SIGNAL_API_KEY"] == "abc%2B=="
        assert os.environ["X"] == "따옴표 안 # 은 값"
        assert os.environ["Y"] == "plain"

    def test_dotenv_does_not_override_real_env(self, tmp_path, monkeypatch):
        f = tmp_path / ".env"
        f.write_text("SIGNAL_API_KEY=from_file\n", encoding="utf-8")
        monkeypatch.setenv("SIGNAL_API_KEY", "from_shell")
        load_dotenv(f)
        import os
        assert os.environ["SIGNAL_API_KEY"] == "from_shell"


# ==========================================================================
class TestRedLightWithLiveSignal:
    """실시간 신호로 신호위반 판정이 실제로 도는지."""

    def _feed(self, engine, pts, t0, track_id=1):
        from app.core.schemas import BBox, Detection, ObjectClass

        evs = []
        for i, (x, y) in enumerate(pts):
            d = Detection(cam_id="CAM-001", track_id=track_id, cls=ObjectClass.CAR,
                          bbox=BBox(x - 45, y - 120, x + 45, y),
                          timestamp=t0 + i * 0.1, frame_no=i)
            evs.extend(engine.process(d, frame=None, plate_hint="12가3456"))
        return [e.violation_type.value for e in evs]

    def _engine(self, repo, zones, signal):
        from app.lpr.pipeline import LPRPipeline
        from app.lpr.recognizer import PlateRecognizer
        from app.vehicle.matcher import VehicleMatcher
        from app.violation.engine import ViolationEngine

        return ViolationEngine(
            zones=zones, signal_provider=signal,
            lpr=LPRPipeline(recognizer=PlateRecognizer(mock=True), publish=False),
            matcher=VehicleMatcher(repo=repo), repo=repo,
        )

    def test_red_light_violation_from_api(self, repo, zones):
        from app.simulator import straight_down

        t0 = 1000.0
        sig = ApiSignal(mapping(id_fields=["itstId"]), api_key="k",
                        max_age_sec=30.0,
                        fetcher=lambda url: json_body(sid="SIG-A", phase="3"))
        sig.poll_once(now=t0 - 10)          # 통과 10초 전부터 적색

        engine = self._engine(repo, zones, sig)
        assert "red_light" in self._feed(engine, straight_down(760, 480, 1030), t0)

    def test_no_violation_on_green_from_api(self, repo, zones):
        from app.simulator import straight_down

        t0 = 1000.0
        sig = ApiSignal(mapping(), api_key="k", max_age_sec=30.0,
                        fetcher=lambda url: json_body(sid="SIG-A", phase="1"))
        sig.poll_once(now=t0 - 10)

        engine = self._engine(repo, zones, sig)
        assert "red_light" not in self._feed(engine, straight_down(760, 480, 1030), t0)

    def test_api_outage_holds_judgement(self, repo, zones):
        """API가 죽어 신호를 모르면 위반으로 단정하지 않는다."""
        from app.simulator import straight_down

        t0 = 1000.0
        sig = ApiSignal(mapping(), api_key="k", max_age_sec=5.0,
                        fetcher=lambda url: json_body(sid="SIG-A", phase="3"))
        sig.poll_once(now=t0 - 600)          # 10분 전 값 = 오래됨

        engine = self._engine(repo, zones, sig)
        assert "red_light" not in self._feed(engine, straight_down(760, 480, 1030), t0)


# ==========================================================================
class TestRiskCategoryGrouping:
    """대시보드 "이상운전" 묶음 — eventType 은 규격 7종 그대로 두고 meta 로만 묶는다."""

    def _payload(self, vtype, subtype=""):
        from app.core.gateway import to_gateway_payload
        from app.core.schemas import ViolationEvent

        ev = ViolationEvent(violation_type=vtype, cam_id="CAM-1", track_id=1,
                            subtype=subtype)
        return to_gateway_payload(ev)

    def test_uturn_is_grouped_as_abnormal_driving(self):
        from app.core.schemas import ViolationType

        p = self._payload(ViolationType.ILLEGAL_UTURN, "no_sign")
        assert p["meta"]["riskCategory"] == "abnormal_driving"
        assert p["meta"]["riskCategoryLabel"] == "이상운전"

    def test_red_light_is_grouped_as_abnormal_driving(self):
        from app.core.schemas import ViolationType

        assert self._payload(ViolationType.RED_LIGHT)["meta"]["riskCategory"] \
            == "abnormal_driving"

    def test_high_risk_vehicle_is_a_different_group(self):
        """미등록·수배 차량은 주행 행태가 아니라 조회 결과다. 같이 묶으면 안 된다."""
        from app.core.schemas import ViolationType

        assert self._payload(ViolationType.HIGH_RISK_VEHICLE)["meta"]["riskCategory"] \
            == "vehicle_alert"

    def test_event_type_is_unchanged(self):
        """묶기 위해 eventType 을 바꾸지 않는다 — 규격 7종 그대로."""
        from app.core.schemas import ViolationType

        assert self._payload(ViolationType.ILLEGAL_UTURN)["eventType"] == "UTURN_VIOLATION"
        assert self._payload(ViolationType.RED_LIGHT)["eventType"] == "SIGNAL_VIOLATION"

    def test_no_new_top_level_fields(self):
        """규격서 4장: 최상위 필드를 임의로 늘리지 않는다."""
        from app.core.schemas import ViolationType

        allowed = {"camId", "trackId", "eventType", "objectClass", "bbox",
                   "confidence", "occurredAt", "location", "isRegisteredTarget",
                   "targetId", "roiId", "meta", "frameRefBefore", "frameRefAfter"}
        assert set(self._payload(ViolationType.ILLEGAL_UTURN)) <= allowed

    def test_one_event_per_violation(self):
        """묶는다고 이벤트를 두 번 만들지 않는다 (통계 부풀림 방지)."""
        from app.core.schemas import ViolationType

        p = self._payload(ViolationType.ILLEGAL_UTURN)
        assert isinstance(p, dict) and p["eventType"] == "UTURN_VIOLATION"
        # DUI_PATTERN 으로 새는 경로가 없어야 한다
        assert "DUI_PATTERN" not in str(p)

    def test_bus_path_matches_direct_path(self):
        """버스 경유로 나가도 같은 카테고리가 붙는다."""
        from app.core.gateway import _payload_from_bus
        from app.core.schemas import ViolationEvent, ViolationType

        ev = ViolationEvent(violation_type=ViolationType.ILLEGAL_UTURN,
                            cam_id="CAM-1", track_id=1, subtype="red_light")
        assert (_payload_from_bus(ev.to_payload())["meta"]["riskCategory"]
                == self._payload(ViolationType.ILLEGAL_UTURN)["meta"]["riskCategory"])
