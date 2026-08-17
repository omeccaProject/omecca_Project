"""KLID 실시간 신호 API 연동 테스트.

여기 쓰인 응답은 **2026-08-13 실제 호출로 받은 원문**이다 (서울 교차로 1057·1062).
지어낸 형식이 아니라서, 이 테스트가 통과하면 실제 응답도 파싱된다.
네트워크는 타지 않는다 — `fetcher` 를 갈아 끼운다.
"""

from __future__ import annotations

import json

import pytest

from app.violation.signal_klid import (
    DIRECTIONS, KlidSignal, field_name, split_signal_id, to_phase,
)
from app.violation.signal_state import Movement, PedPhase, SignalPhase

# --------------------------------------------------------------------------
# 실제 응답 (numOfRows=2). 길어서 필요한 필드만 남기고 나머지는 빈 문자열 그대로.
REAL_ROW_1057 = {
    "stdgCd": "1100000000", "lclgvNm": "서울특별시", "crsrdId": "1057",
    "regId": "v2x", "regDt": "2026-08-13 00:00:00",
    # 서쪽 진입: 보행 정지(잔여 32.7초) / 직진 녹색(잔여 25.7초)
    "wtPdsgRmndCs": "327", "wtPdsgSttsNm": "stop-And-Remain",
    "wtStsgRmndCs": "257", "wtStsgSttsNm": "protected-Movement-Allowed",
    # 북동 진입: 직진 녹색
    "neStsgRmndCs": "257", "neStsgSttsNm": "protected-Movement-Allowed",
    "totDt": "20260813165601",
}

REAL_ROW_1062 = {
    "stdgCd": "1100000000", "lclgvNm": "서울특별시", "crsrdId": "1062",
    # 남동 진입: 좌회전 적색 / 보행 비보호녹색 / 직진 보호녹색
    "seLtsgRmndCs": "138", "seLtsgSttsNm": "stop-And-Remain",
    "sePdsgRmndCs": "78", "sePdsgSttsNm": "permissive-Movement-Allowed",
    "seStsgRmndCs": "78", "seStsgSttsNm": "protected-Movement-Allowed",
    # 남쪽 진입: 전부 적색
    "stLtsgRmndCs": "808", "stLtsgSttsNm": "stop-And-Remain",
    "stPdsgRmndCs": "468", "stPdsgSttsNm": "stop-And-Remain",
    "stStsgRmndCs": "468", "stStsgSttsNm": "stop-And-Remain",
    "totDt": "20260813165601",
}


def body(*rows) -> str:
    return json.dumps({
        "header": {"resultCode": "K0", "resultMsg": "NORMAL_SERVICE"},
        "body": {"totalCount": len(rows), "pageNo": 1, "numOfRows": len(rows),
                 "items": {"item": list(rows)}},
    })


def row(cid="1057", direction="wt", **movements) -> dict:
    """방향 하나에 이동류 상태를 지정한 행을 만든다.

    row("1", "wt", Utsg=("protected-Movement-Allowed", 120))
    """
    out = {"crsrdId": cid}
    for token, val in movements.items():
        state, remain = val if isinstance(val, tuple) else (val, None)
        out[f"{direction}{token}SttsNm"] = state
        if remain is not None:
            out[f"{direction}{token}RmndCs"] = str(remain)
    return out


def sig(**kw) -> KlidSignal:
    kw.setdefault("api_key", "test-key")
    kw.setdefault("fetcher", lambda url: body())
    return KlidSignal(**kw)


# ==========================================================================
class TestFieldNaming:
    def test_builds_field_names(self):
        assert field_name("wt", Movement.UTURN, "SttsNm") == "wtUtsgSttsNm"
        assert field_name("se", Movement.PED, "RmndCs") == "sePdsgRmndCs"
        assert field_name("nt", Movement.STRAIGHT, "SttsNm") == "ntStsgSttsNm"

    def test_eight_directions(self):
        assert len(DIRECTIONS) == 8
        assert set(DIRECTIONS) == {"nt", "et", "st", "wt", "ne", "se", "sw", "nw"}

    def test_signal_id_split(self):
        assert split_signal_id("1057:wt") == ("1057", "wt")
        assert split_signal_id("1057") == ("1057", "")


class TestJ2735States:
    @pytest.mark.parametrize("raw,expect", [
        ("stop-And-Remain", SignalPhase.RED),
        ("stop-Then-Proceed", SignalPhase.RED),          # 적색 점멸
        ("pre-Movement", SignalPhase.RED),               # 적+황, 아직 정지
        ("protected-Movement-Allowed", SignalPhase.GREEN),
        ("permissive-Movement-Allowed", SignalPhase.GREEN),   # 비보호 녹색
        ("protected-Clearance", SignalPhase.YELLOW),
        ("caution-Conflicting-Traffic", SignalPhase.YELLOW),  # 황색 점멸
        ("dark", SignalPhase.UNKNOWN),
        ("unavailable", SignalPhase.UNKNOWN),
        ("", SignalPhase.UNKNOWN),
        (None, SignalPhase.UNKNOWN),
        ("듣도보도못한값", SignalPhase.UNKNOWN),
    ])
    def test_maps_state(self, raw, expect):
        assert to_phase(raw) is expect


# ==========================================================================
class TestRealResponse:
    """실제로 받은 응답이 그대로 파싱되는지."""

    def test_parses_real_response(self):
        s = sig(fetcher=lambda url: body(REAL_ROW_1057, REAL_ROW_1062))
        n = s.poll_once(now=100.0)
        assert n > 0
        ids = s.live_signal_ids()
        assert "1057:wt" in ids
        assert "1062:se" in ids

    def test_empty_directions_are_skipped(self):
        """8방향 중 값이 있는 방향만 담는다. 대부분은 비어 있다."""
        s = sig(fetcher=lambda url: body(REAL_ROW_1057))
        s.poll_once(now=100.0)
        assert s.live_signal_ids() == ["1057:ne", "1057:wt"]

    def test_straight_green(self):
        s = sig(fetcher=lambda url: body(REAL_ROW_1057))
        s.poll_once(now=100.0)
        assert s.movement_at("1057:wt", 100.0, Movement.STRAIGHT) is SignalPhase.GREEN

    def test_pedestrian_red(self):
        s = sig(fetcher=lambda url: body(REAL_ROW_1057))
        s.poll_once(now=100.0)
        assert s.ped_phase_at("1057:wt", 100.0) is PedPhase.RED

    def test_permissive_pedestrian_is_green(self):
        s = sig(fetcher=lambda url: body(REAL_ROW_1062))
        s.poll_once(now=100.0)
        assert s.ped_phase_at("1062:se", 100.0) is PedPhase.GREEN

    def test_remaining_time_is_deciseconds(self):
        """RmndCs 808 → 80.8초. 초로 보면 13분이라 말이 안 된다."""
        s = sig(fetcher=lambda url: body(REAL_ROW_1062))
        s.poll_once(now=100.0)
        assert s.remain_sec("1062:st", 100.0, Movement.LEFT) == pytest.approx(80.8)
        assert s.remain_sec("1062:st", 100.0, Movement.PED) == pytest.approx(46.8)

    def test_all_red_direction(self):
        s = sig(fetcher=lambda url: body(REAL_ROW_1062))
        s.poll_once(now=100.0)
        assert s.phase_at("1062:st", 100.0) is SignalPhase.RED
        assert s.ped_phase_at("1062:st", 100.0) is PedPhase.RED


# ==========================================================================
class TestComposedVehiclePhase:
    """직진과 좌회전을 합쳐 하나의 차량 신호로 만든다."""

    def _phase(self, straight, left):
        s = sig(fetcher=lambda url: body(row("1", "wt", Stsg=straight, Ltsg=left)))
        s.poll_once(now=100.0)
        return s.phase_at("1:wt", 100.0)

    def test_straight_and_left_green_is_green_left(self):
        assert self._phase("protected-Movement-Allowed",
                           "protected-Movement-Allowed") is SignalPhase.GREEN_LEFT

    def test_left_only_is_left_arrow(self):
        assert self._phase("stop-And-Remain",
                           "protected-Movement-Allowed") is SignalPhase.LEFT_ARROW

    def test_straight_only_is_green(self):
        assert self._phase("protected-Movement-Allowed",
                           "stop-And-Remain") is SignalPhase.GREEN

    def test_both_red(self):
        assert self._phase("stop-And-Remain", "stop-And-Remain") is SignalPhase.RED

    def test_yellow(self):
        assert self._phase("protected-Clearance", "stop-And-Remain") is SignalPhase.YELLOW


# ==========================================================================
class TestUTurnSignalIsUsedDirectly:
    """이 API의 핵심 이점 — 유턴 신호를 추론하지 않고 직접 본다."""

    def _judge(self, uturn_state, straight="stop-And-Remain", ped=None):
        from app.violation.detectors import UTurnDetector
        from app.violation.roi import VirtualLine

        kw = {"Utsg": uturn_state, "Stsg": straight}
        if ped:
            kw["Pdsg"] = ped
        s = sig(fetcher=lambda url: body(row("1", "wt", **kw)))
        s.poll_once(now=100.0)

        det = UTurnDetector(s)
        line = VirtualLine(line_id="c1", p1=(0, 0), p2=(10, 10),
                           line_type="center", uturn_allowed=True,
                           signal_id="1:wt")
        return det._judge(None, line, -90.0, 90.0, 180.0, 100.0, 10, 100.5, 20)

    def test_uturn_green_is_legal(self):
        assert self._judge("protected-Movement-Allowed") is None

    def test_uturn_red_is_violation(self):
        v = self._judge("stop-And-Remain")
        assert v is not None and v.subtype == "red_light"
        assert "유턴 신호" in v.detail

    def test_uturn_yellow_is_violation(self):
        v = self._judge("protected-Clearance")
        assert v is not None and v.subtype == "wrong_signal"

    def test_uturn_green_overrides_straight_green(self):
        """직진이 녹색이어도 유턴 신호가 녹색이면 합법이다."""
        assert self._judge("protected-Movement-Allowed",
                           straight="protected-Movement-Allowed") is None

    def test_falls_back_when_no_uturn_signal(self):
        """유턴 신호가 안 오면 종전대로 좌회전·보행 신호로 추론한다."""
        v = self._judge("", straight="protected-Movement-Allowed")
        assert v is not None and v.subtype == "wrong_signal"

    def test_ped_green_still_works_as_fallback(self):
        assert self._judge("", straight="protected-Movement-Allowed",
                           ped="protected-Movement-Allowed") is None


# ==========================================================================
class TestHistoryAndFailure:
    def test_answers_past_timestamps(self):
        seq = ["protected-Movement-Allowed", "protected-Movement-Allowed",
               "stop-And-Remain"]
        box = {"i": 0}

        def fetch(url):
            v = seq[min(box["i"], len(seq) - 1)]
            box["i"] += 1
            return body(row("1", "wt", Stsg=v))

        s = sig(fetcher=fetch)
        for t in (100.0, 101.0, 102.0):
            s.poll_once(now=t)

        assert s.phase_at("1:wt", 100.5) is SignalPhase.GREEN
        assert s.phase_at("1:wt", 102.0) is SignalPhase.RED

    def test_remaining_time_pins_transition(self):
        seq = [("protected-Movement-Allowed", 4), ("stop-And-Remain", 300)]
        box = {"i": 0}

        def fetch(url):
            st, rm = seq[min(box["i"], len(seq) - 1)]
            box["i"] += 1
            return body(row("1", "wt", Stsg=(st, rm)))

        s = sig(fetcher=fetch)
        s.poll_once(now=100.0)          # 녹색, 잔여 0.4초 (4 → 0.4s)
        s.poll_once(now=101.0)
        # 중간값 100.5 가 아니라 100.4 여야 한다
        assert s.last_change("1:wt", 101.0) == pytest.approx(100.4)

    def test_stale_becomes_unknown(self):
        s = sig(max_age_sec=5.0, fetcher=lambda url: body(REAL_ROW_1057))
        s.poll_once(now=100.0)
        assert s.phase_at("1057:wt", 103.0) is SignalPhase.GREEN
        assert s.phase_at("1057:wt", 200.0) is SignalPhase.UNKNOWN

    def test_network_failure_is_held(self):
        state = {"fail": False}

        def fetch(url):
            if state["fail"]:
                raise OSError("연결 끊김")
            return body(REAL_ROW_1057)

        s = sig(fetcher=fetch)
        s.poll_once(now=100.0)
        state["fail"] = True
        s.poll_once(now=101.0)
        assert s.stats["failed"] == 1
        assert s.phase_at("1057:wt", 101.0) is SignalPhase.GREEN
        assert s.phase_at("1057:wt", 500.0) is SignalPhase.UNKNOWN

    def test_api_error_code_is_detected(self):
        err = json.dumps({"header": {"resultCode": "30",
                                     "resultMsg": "SERVICE_KEY_IS_NOT_REGISTERED_ERROR"}})
        s = sig(fetcher=lambda url: err)
        assert s.poll_once(now=100.0) == 0
        assert "SERVICE_KEY" in s.last_error

    def test_garbage_does_not_crash(self):
        s = sig(fetcher=lambda url: "<<깨진 응답")
        assert s.poll_once(now=100.0) == 0
        assert s.phase_at("1057:wt", 100.0) is SignalPhase.UNKNOWN

    def test_unknown_intersection(self):
        s = sig(fetcher=lambda url: body(REAL_ROW_1057))
        s.poll_once(now=100.0)
        assert s.phase_at("9999:nt", 100.0) is SignalPhase.UNKNOWN


class TestUrlBuilding:
    def test_key_is_not_double_encoded(self):
        key = "abc%2Bdef%3D%3D"
        s = sig(api_key=key)
        assert f"serviceKey={key}" in s.build_url()
        assert "%252B" not in s.build_url()

    def test_default_base_url(self):
        assert "apis.data.go.kr/B551982/rti" in sig().build_url()

    def test_accepts_full_url_with_path(self):
        """사용자가 .env 에 /tl_drct_info 까지 넣어도 경로가 겹치지 않는다."""
        s = sig(base_url="https://apis.data.go.kr/B551982/rti/tl_drct_info")
        assert s.build_url().count("/tl_drct_info") == 1
