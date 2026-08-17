"""행정안전부 한국지역정보개발원 — 교통안전 신호등 실시간 정보 연동.

공공데이터포털 15157604
Base URL: https://apis.data.go.kr/B551982/rti

    /crsrd_map_info   교차로 맵 정보      (교차로 ID·이름·위경도, 전국 4,239곳)
    /tl_drct_info     신호제어기 잔여시간 (실시간 점등상태·잔여시간, 1,399곳)

---
데이터 구조 — 교차로 하나에 신호가 48개다

    교차로(crsrdId) × 진입방향 8개 × 이동류 6개

  진입방향  nt 북 · et 동 · st 남 · wt 서 · ne 북동 · se 남동 · sw 남서 · nw 북서
  이동류    Stsg 직진 · Ltsg 좌회전 · Utsg 유턴 · Pdsg 보행 · Bssg 버스 · Bcsg 자전거

  필드명은 `<방향><이동류><접미사>` 로 조합된다.

      wtStsgSttsNm = 서쪽 진입 직진신호 점등상태명
      wtUtsgRmndCs = 서쪽 진입 유턴신호 잔여시간
      sePdsgSttsNm = 남동 진입 보행신호 점등상태명

  그래서 우리 `signal_id` 는 **"교차로ID:방향"** 형식이다.  예) "1057:wt"
  `config_zones.json` 의 라인마다 이 값을 넣어 주면 된다.

---
실제로 뭐가 채워져 오는가 (2026-08-13 전수 조사)

  규격에 필드가 있는 것과 값이 실제로 오는 것은 다르다. 1,399행을 훑어 세었다.

    교차로 목록          4,239곳
    실시간 신호 수신     1,342곳  (32%)
    유턴 신호(Utsg) 값   **1곳**  (동대문역 서쪽 진입)

  **유턴 신호는 사실상 안 온다.** 아래 `movement_at(..., UTURN)` 경로는
  값이 올 때 정확히 동작하지만, 현실에서는 대부분 UNKNOWN 이 되어
  좌회전·보행 신호로 추론하는 기존 경로로 넘어간다.

  보행 신호(Pdsg)는 꽤 온다. 이쪽은 "연계 가정"이 아니라 실제 값이다.

---
점등상태 값은 SAE J2735 MovementPhaseState 를 그대로 쓴다

  stop-And-Remain               적색 (정지 유지)
  protected-Movement-Allowed    녹색 (보호 이동 — 화살표 등 상충 없음)
  permissive-Movement-Allowed   녹색 (비보호 이동 — 상충 가능, 예: 비보호 좌회전)
  protected-Clearance           황색
  permissive-Clearance          황색
  caution-Conflicting-Traffic   황색 점멸
  stop-Then-Proceed             적색 점멸
  pre-Movement                  적+황 (곧 녹색이지만 아직 정지)
  dark / unavailable            신호 정보 없음

빈 문자열("")도 흔하다. 그 방향에 그 이동류가 없거나 자료가 안 올라온 것이다.
이 경우 UNKNOWN 이 되고, 판정은 보류된다.
"""

from __future__ import annotations

import logging
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable, Optional

from ..core.config import mask, secret
from .signal_api import find_items, parse_response
from .signal_state import Movement, PedPhase, SignalPhase, SignalProvider

log = logging.getLogger("omeca.violation.signal_klid")

BASE_URL = "https://apis.data.go.kr/B551982/rti"
PATH_SIGNAL = "/tl_drct_info"
PATH_MAP = "/crsrd_map_info"

# 진입 방향 접두사
DIRECTIONS = {
    "nt": "북", "et": "동", "st": "남", "wt": "서",
    "ne": "북동", "se": "남동", "sw": "남서", "nw": "북서",
}

# 이동류 → 필드 중간 토큰
MOVEMENT_TOKEN = {
    Movement.STRAIGHT: "Stsg",
    Movement.LEFT: "Ltsg",
    Movement.UTURN: "Utsg",
    Movement.PED: "Pdsg",
    Movement.BUS: "Bssg",
    Movement.BIKE: "Bcsg",
}

# SAE J2735 MovementPhaseState → 우리 상태 (소문자로 비교)
J2735_PHASE = {
    "stop-and-remain": SignalPhase.RED,
    "stop-then-proceed": SignalPhase.RED,          # 적색 점멸 — 일단 정지
    "pre-movement": SignalPhase.RED,               # 적+황, 아직 진행 불가
    "protected-movement-allowed": SignalPhase.GREEN,
    "permissive-movement-allowed": SignalPhase.GREEN,
    "protected-clearance": SignalPhase.YELLOW,
    "permissive-clearance": SignalPhase.YELLOW,
    "caution-conflicting-traffic": SignalPhase.YELLOW,   # 황색 점멸
    "dark": SignalPhase.UNKNOWN,
    "unavailable": SignalPhase.UNKNOWN,
}

# 잔여시간 단위.
#   관측값이 808 / 468 / 327 / 257 / 138 / 78 로, 초로 보면 808초(13분)라 말이 안 된다.
#   0.1초로 보면 80.8 / 46.8 / 32.7 / 25.7 / 13.8 / 7.8초 — 실제 신호 주기와 맞다.
#   원본이 SAE J2735(1/10초 단위)라 그대로 실어 보내는 것으로 보인다.
#   **스톱워치로 한 번 검증할 것.** signal_probe.py --watch 로 확인할 수 있다.
REMAIN_UNIT_SEC = 0.1


def to_phase(value: object) -> SignalPhase:
    if value is None:
        return SignalPhase.UNKNOWN
    s = str(value).strip().lower()
    return J2735_PHASE.get(s, SignalPhase.UNKNOWN) if s else SignalPhase.UNKNOWN


def field_name(direction: str, movement: Movement, suffix: str) -> str:
    """('wt', UTURN, 'SttsNm') → 'wtUtsgSttsNm'"""
    return f"{direction}{MOVEMENT_TOKEN[movement]}{suffix}"


def split_signal_id(signal_id: str) -> tuple[str, str]:
    """'1057:wt' → ('1057', 'wt'). 방향이 없으면 빈 문자열."""
    cid, _, direction = signal_id.partition(":")
    return cid.strip(), direction.strip().lower()


# ==========================================================================
@dataclass
class Snapshot:
    """어느 시점의 한 (교차로, 방향) 상태."""

    ts: float
    phases: dict[Movement, SignalPhase]
    remains: dict[Movement, Optional[float]]

    def phase(self, m: Movement) -> SignalPhase:
        return self.phases.get(m, SignalPhase.UNKNOWN)

    def remain(self, m: Movement) -> Optional[float]:
        return self.remains.get(m)


# ==========================================================================
class KlidSignal(SignalProvider):
    """KLID 실시간 신호 API 기반 SignalProvider.

    API는 '지금'만 알지만 판정은 '차가 선을 넘던 그때'를 묻는다. 그래서
    폴링하며 **변화 이력을 쌓아 두고** 과거 시각을 조회할 수 있게 한다.

    응답이 `max_age_sec` 보다 오래되면 UNKNOWN 을 돌려준다 → 판정 보류.
    신호를 모르는 채로 위반 딱지를 붙이지 않는다.
    """

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "",
        poll_sec: float = 1.0,
        max_age_sec: float = 5.0,
        history_sec: float = 600.0,
        num_rows: int = 1000,
        timeout: float = 5.0,
        remain_unit_sec: float = REMAIN_UNIT_SEC,
        fetcher: Optional[Callable[[str], str]] = None,
    ) -> None:
        self.key = api_key or secret("SIGNAL_API_KEY")
        self.base = (base_url or secret("SIGNAL_API_URL") or BASE_URL).rstrip("/")
        if self.base.endswith(PATH_SIGNAL):
            self.base = self.base[: -len(PATH_SIGNAL)]
        self.poll_sec = poll_sec
        self.max_age_sec = max_age_sec
        self.history_sec = history_sec
        self.num_rows = num_rows
        self.timeout = timeout
        self.remain_unit_sec = remain_unit_sec
        self._fetch = fetcher or self._http_get

        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        # "교차로:방향" -> 변화 이력
        self._hist: dict[str, list[Snapshot]] = {}
        self._last: dict[str, Snapshot] = {}
        self.names: dict[str, str] = {}                    # crsrdId -> 교차로명
        self.coords: dict[str, tuple[float, float]] = {}   # crsrdId -> (위도, 경도)
        self.stats = {"polls": 0, "ok": 0, "failed": 0, "rows": 0,
                      "live_dirs": 0, "changes": 0}
        self.last_error = ""

    # ------------------------------------------------------------------
    def ready(self) -> tuple[bool, str]:
        if not self.key:
            return False, ".env 에 SIGNAL_API_KEY 가 없습니다."
        return True, f"KLID 신호 API 준비됨 (키 {mask(self.key)})"

    def build_url(self, path: str = PATH_SIGNAL, page: int = 1,
                  rows: Optional[int] = None) -> str:
        # 서비스키는 포털이 준 Encoding 값 그대로. 다시 인코딩하면 401 이 난다.
        return (f"{self.base}{path}?serviceKey={self.key}"
                f"&numOfRows={rows or self.num_rows}&pageNo={page}&type=json")

    def _http_get(self, url: str) -> str:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return r.read().decode("utf-8", "replace")

    # ------------------------------------------------------------------
    def parse_row(self, row: dict, now: float) -> dict[str, Snapshot]:
        """응답 1행(교차로 1곳) → {"교차로:방향": Snapshot}.

        8방향 × 6이동류를 훑되, **하나라도 값이 있는 방향만** 담는다.
        대부분의 방향은 비어 있다 (그 방향에 그 이동류가 없는 교차로).
        """
        cid = str(row.get("crsrdId", "")).strip()
        if not cid:
            return {}

        out: dict[str, Snapshot] = {}
        for d in DIRECTIONS:
            phases: dict[Movement, SignalPhase] = {}
            remains: dict[Movement, Optional[float]] = {}
            any_value = False
            for m in MOVEMENT_TOKEN:
                raw_state = row.get(field_name(d, m, "SttsNm"))
                raw_remain = row.get(field_name(d, m, "RmndCs"))
                ph = to_phase(raw_state)
                phases[m] = ph
                rm = None
                if raw_remain not in (None, ""):
                    try:
                        rm = float(raw_remain) * self.remain_unit_sec
                    except (TypeError, ValueError):
                        rm = None
                remains[m] = rm
                if ph is not SignalPhase.UNKNOWN or rm is not None:
                    any_value = True
            if any_value:
                out[f"{cid}:{d}"] = Snapshot(now, phases, remains)
        return out

    # ------------------------------------------------------------------
    def poll_once(self, now: Optional[float] = None) -> int:
        """한 번 조회해 이력에 반영. 값이 살아 있는 (교차로,방향) 수를 반환."""
        now = time.time() if now is None else now
        self.stats["polls"] += 1
        try:
            body = self._fetch(self.build_url())
            obj = parse_response(body)
        except urllib.error.HTTPError as e:
            self.last_error = f"HTTP {e.code}"
            self.stats["failed"] += 1
            log.warning("KLID 신호 API %s", self.last_error)
            return 0
        except Exception as e:
            self.last_error = f"{type(e).__name__}: {e}"
            self.stats["failed"] += 1
            log.warning("KLID 신호 API 조회 실패: %s", self.last_error)
            return 0

        header = obj.get("header", {}) if isinstance(obj, dict) else {}
        code = str(header.get("resultCode", ""))
        if code and code not in ("K0", "00"):
            self.last_error = f"{code} {header.get('resultMsg', '')}"
            self.stats["failed"] += 1
            log.warning("KLID 신호 API 오류: %s", self.last_error)
            return 0

        rows = find_items(obj, "body.items.item")
        if not rows:
            self.last_error = "응답에 항목이 없음"
            self.stats["failed"] += 1
            return 0

        self.stats["ok"] += 1
        self.last_error = ""
        self.stats["rows"] += len(rows)

        n = 0
        for row in rows:
            for sid, snap in self.parse_row(row, now).items():
                self._record(sid, snap)
                n += 1
        self.stats["live_dirs"] = n
        return n

    # ------------------------------------------------------------------
    def _record(self, sid: str, snap: Snapshot) -> None:
        with self._lock:
            prev = self._last.get(sid)
            self._last[sid] = snap
            hist = self._hist.setdefault(sid, [])

            if prev is not None and prev.phases == snap.phases:
                return                        # 점등 변화 없음

            # 전환 시각 추정. 직전 관측의 잔여시간으로 역산하면 폴링 간격보다
            # 정밀하다. (1초 폴링 → 유예 판정 0.3초를 가릴 만큼 큰 오차가 남)
            if prev is None:
                change_ts = snap.ts
            else:
                est = self._estimate_change(prev, snap)
                change_ts = est if est is not None else (prev.ts + snap.ts) / 2.0

            hist.append(Snapshot(change_ts, snap.phases, snap.remains))
            self.stats["changes"] += 1

            cutoff = snap.ts - self.history_sec
            while len(hist) > 2 and hist[0].ts < cutoff:
                hist.pop(0)

    def _estimate_change(self, prev: Snapshot, cur: Snapshot) -> Optional[float]:
        """바뀐 이동류의 직전 잔여시간으로 전환 시각을 역산한다."""
        best: Optional[float] = None
        for m, ph in cur.phases.items():
            if prev.phases.get(m) is ph:
                continue                      # 안 바뀐 이동류는 근거가 안 된다
            r = prev.remain(m)
            if r is None:
                continue
            est = prev.ts + r
            if prev.ts <= est <= cur.ts:      # 두 관측 사이여야 신뢰
                best = est if best is None else min(best, est)
        return best

    # ------------------------------------------------------------------
    def _lookup(self, signal_id: str, ts: float) -> Optional[Snapshot]:
        with self._lock:
            last = self._last.get(signal_id)
            hist = list(self._hist.get(signal_id, []))
        if last is None or last.ts < ts - self.max_age_sec:
            return None                       # 자료 없음 / 오래됨 → 판정 보류
        found = None
        for s in hist:
            if s.ts <= ts:
                found = s
            else:
                break
        return found

    # --- SignalProvider 인터페이스 ------------------------------------
    def movement_at(self, signal_id: str, ts: float, movement: Movement) -> SignalPhase:
        s = self._lookup(signal_id, ts)
        return s.phase(movement) if s else SignalPhase.UNKNOWN

    def phase_at(self, signal_id: str, ts: float) -> SignalPhase:
        """차량 신호. 직진과 좌회전을 합쳐 하나의 상태로 만든다."""
        s = self._lookup(signal_id, ts)
        if s is None:
            return SignalPhase.UNKNOWN
        straight = s.phase(Movement.STRAIGHT)
        left = s.phase(Movement.LEFT)

        if straight is SignalPhase.GREEN and left is SignalPhase.GREEN:
            return SignalPhase.GREEN_LEFT
        if left is SignalPhase.GREEN and straight is not SignalPhase.GREEN:
            return SignalPhase.LEFT_ARROW
        if straight is not SignalPhase.UNKNOWN:
            return straight
        return left

    def ped_phase_at(self, signal_id: str, ts: float) -> PedPhase:
        ph = self.movement_at(signal_id, ts, Movement.PED)
        if ph is SignalPhase.GREEN:
            return PedPhase.GREEN
        if ph in (SignalPhase.RED, SignalPhase.YELLOW):
            return PedPhase.RED
        return PedPhase.UNKNOWN

    def last_change(self, signal_id: str, ts: float) -> float:
        s = self._lookup(signal_id, ts)
        return s.ts if s else 0.0

    def remain_sec(self, signal_id: str, ts: float, movement: Movement) -> Optional[float]:
        s = self._lookup(signal_id, ts)
        return s.remain(movement) if s else None

    # ------------------------------------------------------------------
    def live_signal_ids(self) -> list[str]:
        with self._lock:
            return sorted(self._last)

    def load_map(self, pages: int = 5) -> int:
        """교차로 이름·좌표를 받아 둔다.

        내 CCTV가 찍는 교차로의 `crsrdId` 를 찾으려면 이게 필요하다.
        전국 4,239곳이라 한 번만 받아 두면 된다.
        """
        got = 0
        for page in range(1, pages + 1):
            try:
                obj = parse_response(self._fetch(self.build_url(PATH_MAP, page=page)))
            except Exception as e:
                log.warning("교차로 목록 조회 실패: %s", e)
                break
            rows = find_items(obj, "body.items.item")
            if not rows:
                break
            for r in rows:
                cid = str(r.get("crsrdId", "")).strip()
                if not cid:
                    continue
                self.names[cid] = str(r.get("crsrdNm", "")).strip()
                try:
                    self.coords[cid] = (float(r.get("mapCtptIntLat")),
                                        float(r.get("mapCtptIntLot")))
                except (TypeError, ValueError):
                    pass
                got += 1
        return got

    def nearest(self, lat: float, lng: float, limit: int = 5) -> list[tuple[float, str, str]]:
        """위경도에서 가까운 교차로. [(거리 m, 교차로ID, 이름)]

        `load_map()` 을 먼저 불러야 한다. 촬영 지점 좌표를 넣으면
        어느 `crsrdId` 를 써야 하는지 알 수 있다.
        """
        import math

        out = []
        for cid, (clat, clng) in self.coords.items():
            dy = (clat - lat) * 111_320
            dx = (clng - lng) * 111_320 * math.cos(math.radians(lat))
            out.append((math.hypot(dx, dy), cid, self.names.get(cid, "")))
        return sorted(out)[:limit]

    # ------------------------------------------------------------------
    def start(self) -> "KlidSignal":
        ok, why = self.ready()
        if not ok:
            log.warning("KLID 신호 API 비활성: %s", why)
            return self
        if self._thread is not None:
            return self
        self._thread = threading.Thread(target=self._worker, daemon=True,
                                        name="klid-signal-poller")
        self._thread.start()
        log.info("KLID 신호 폴링 시작 (%.1f초 간격)", self.poll_sec)
        return self

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3.0)
            self._thread = None

    def _worker(self) -> None:
        while not self._stop.is_set():
            self.poll_once()
            self._stop.wait(self.poll_sec)
