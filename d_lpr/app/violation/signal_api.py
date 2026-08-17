"""실시간 신호정보 API 연동 (공공데이터포털).

`TimelineSignal` 이 "사람이 적어 둔 신호"를 재생한다면, 이쪽은 **실제 신호제어기
값을 API로 받아 온다.** 판정 로직(`RedLightDetector`, `UTurnDetector`)은
`SignalProvider` 인터페이스만 보므로 이 클래스로 갈아 끼우면 그대로 동작한다.

---
설계에서 가장 중요한 점 — **과거를 물어본다**

판정은 "차가 정지선을 넘던 **그 순간**의 신호"를 묻는다.

    phase_at(signal_id, ts)      # ts 는 과거 시각

그런데 API는 "지금"밖에 모른다. 그래서 이 클래스는 백그라운드로 계속 폴링하며
**관측 이력을 로컬에 쌓아 두고**, 조회가 오면 그 이력에서 해당 시각을 찾는다.
`TimelineSignal` 과 같은 조회 방식이고, 타임라인을 사람이 아니라 API가 채운다.

**전환 시각 보정**

폴링 간격이 1초면 신호가 언제 바뀌었는지 최대 1초 오차가 난다. 적색 판정
유예(`redlight_grace_sec`)가 0.3초라 이 오차는 그냥 넘길 수 없다.
그래서 API가 **잔여시간**을 주면 그것으로 전환 시각을 역산한다.

    직전 관측이 (t=10.0, 녹색, 잔여 2.4초) 였다면
    → 실제 전환 시각은 12.4초. 폴링이 13.0초에 적색을 봤더라도 12.4초로 기록한다.

잔여시간이 없으면 두 관측의 중간값으로 둔다 (오차 ±폴링간격/2).

---
장애 대응 — **판정 보류**

API가 죽거나 응답이 `max_age_sec` 보다 오래됐으면 `UNKNOWN` 을 돌려준다.
판정 쪽은 `UNKNOWN` 이면 위반으로 단정하지 않는다. 신호를 모르는 채로 사람에게
과태료를 물릴 수는 없다. 놓치는 건 있어도 억울한 오탐은 없다.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from ..core.config import BASE_DIR, mask, secret
from .signal_state import PedPhase, SignalPhase, SignalProvider

log = logging.getLogger("omeca.violation.signal_api")

MAP_PATH = BASE_DIR / "signal_api.json"


# ==========================================================================
@dataclass
class ApiMapping:
    """API 응답을 우리 규격으로 옮기는 방법.

    기관마다 필드 이름이 달라 코드에 박지 않고 `signal_api.json` 으로 뺐다.
    `signal_probe.py` 로 실제 응답을 찍어 보고 채우면 된다.
    """

    url: str = ""
    key_param: str = "serviceKey"
    params: dict[str, str] = field(default_factory=dict)
    # 응답에서 교차로 목록이 들어 있는 경로 (점 표기). 비우면 자동 탐색
    items_path: str = ""
    # 항목 안의 필드 이름 (후보를 여러 개 적으면 먼저 발견되는 것을 쓴다)
    id_fields: list[str] = field(default_factory=lambda: ["itstId", "crossId", "nodeId"])
    phase_fields: list[str] = field(default_factory=lambda: ["signalState", "phase"])
    remain_fields: list[str] = field(default_factory=lambda: ["remainTime", "remndSec"])
    ped_fields: list[str] = field(default_factory=lambda: ["pedSignalState", "pedPhase"])
    # 응답 값 → SignalPhase. 소문자로 비교한다.
    phase_map: dict[str, str] = field(default_factory=dict)
    ped_map: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path = MAP_PATH) -> "ApiMapping":
        m = cls()
        if not path.exists():
            log.warning("신호 API 매핑 파일 없음(%s) → 기본 후보로 시도", path)
            return m
        raw = json.loads(path.read_text(encoding="utf-8"))
        for k, v in raw.items():
            if k.startswith("_"):          # 주석 키
                continue
            if hasattr(m, k):
                setattr(m, k, v)
        return m


# 기관에서 흔히 쓰는 표기들. 매핑 파일에 없으면 이걸로 넘어온다.
DEFAULT_PHASE_WORDS = {
    SignalPhase.RED: ["red", "r", "적색", "정지", "1"],
    SignalPhase.YELLOW: ["yellow", "amber", "y", "황색", "주의"],
    SignalPhase.GREEN: ["green", "g", "녹색", "직진", "진행"],
    SignalPhase.LEFT_ARROW: ["left", "left_arrow", "leftarrow", "좌회전", "좌회전화살표"],
    SignalPhase.GREEN_LEFT: ["green_left", "greenleft", "직진좌회전", "직좌"],
}
DEFAULT_PED_WORDS = {
    PedPhase.RED: ["red", "r", "적색", "정지"],
    PedPhase.GREEN: ["green", "g", "녹색", "보행"],
}


def _to_phase(value: Any, table: dict[str, str]) -> SignalPhase:
    if value is None:
        return SignalPhase.UNKNOWN
    s = str(value).strip().lower()
    if not s:
        return SignalPhase.UNKNOWN
    hit = table.get(s)
    if hit:
        try:
            return SignalPhase(hit)
        except ValueError:
            return SignalPhase.UNKNOWN
    for ph, words in DEFAULT_PHASE_WORDS.items():
        if s in words:
            return ph
    return SignalPhase.UNKNOWN


def _to_ped(value: Any, table: dict[str, str]) -> PedPhase:
    if value is None:
        return PedPhase.UNKNOWN
    s = str(value).strip().lower()
    if not s:
        return PedPhase.UNKNOWN
    hit = table.get(s)
    if hit:
        try:
            return PedPhase(hit)
        except ValueError:
            return PedPhase.UNKNOWN
    for ph, words in DEFAULT_PED_WORDS.items():
        if s in words:
            return ph
    return PedPhase.UNKNOWN


# ==========================================================================
def parse_response(body: str) -> Any:
    """JSON 이든 XML 이든 dict/list 로 만든다.

    공공데이터포털은 기본이 XML 이고 파라미터에 따라 JSON 도 준다.
    어느 쪽이 올지 모르니 둘 다 받는다.
    """
    text = body.strip()
    if not text:
        return {}
    if text[0] in "{[":
        return json.loads(text)
    root = ET.fromstring(text)
    return _xml_to_obj(root)


def _xml_to_obj(el) -> Any:
    children = list(el)
    if not children:
        return (el.text or "").strip()
    out: dict[str, Any] = {}
    for c in children:
        v = _xml_to_obj(c)
        tag = c.tag.split("}")[-1]          # 네임스페이스 제거
        if tag in out:                      # 같은 태그가 반복되면 리스트
            if not isinstance(out[tag], list):
                out[tag] = [out[tag]]
            out[tag].append(v)
        else:
            out[tag] = v
    return out


def find_items(obj: Any, path: str = "") -> list[dict]:
    """응답에서 교차로 항목 리스트를 찾아낸다.

    `path` 를 주면 그대로 따라가고, 없으면 'dict 들이 담긴 가장 큰 리스트' 를
    찾는다. 기관마다 response.body.items.item 구조가 조금씩 달라서
    자동 탐색을 기본으로 두었다.
    """
    if path:
        cur = obj
        for part in path.split("."):
            if isinstance(cur, dict):
                cur = cur.get(part)
            elif isinstance(cur, list):
                cur = cur[int(part)] if part.isdigit() else None
            if cur is None:
                return []
        if isinstance(cur, dict):
            return [cur]
        return [x for x in cur if isinstance(x, dict)] if isinstance(cur, list) else []

    # 1순위: dict 들이 담긴 가장 큰 리스트
    best: list[dict] = []
    # 2순위: item/row 키 아래의 단일 dict (결과가 1건이면 리스트가 아니라 dict 로 온다)
    single: list[dict] = []

    def walk(node: Any) -> None:
        nonlocal best, single
        if isinstance(node, list):
            dicts = [x for x in node if isinstance(x, dict)]
            if len(dicts) > len(best):
                best = dicts
            for x in node:
                walk(x)
        elif isinstance(node, dict):
            for k, v in node.items():
                if (k.lower() in ("item", "row") and isinstance(v, dict)
                        and _is_leaf_record(v) and not single):
                    single = [v]
                walk(v)

    walk(obj)
    return best or single


def _is_leaf_record(d: dict) -> bool:
    """값이 전부 스칼라인 dict = 한 건의 레코드. 중간 래퍼와 구분하기 위함."""
    return bool(d) and all(not isinstance(v, (dict, list)) for v in d.values())


def _pick(item: dict, names: list[str]) -> Any:
    """후보 이름 중 먼저 발견되는 값. 대소문자 무시."""
    lower = {k.lower(): v for k, v in item.items()}
    for n in names:
        v = lower.get(n.lower())
        if v not in (None, ""):
            return v
    return None


# ==========================================================================
@dataclass
class Observation:
    ts: float
    phase: SignalPhase
    ped: PedPhase
    remain: Optional[float] = None


class ApiSignal(SignalProvider):
    """공공데이터포털 실시간 신호 API 기반 SignalProvider."""

    def __init__(
        self,
        mapping: Optional[ApiMapping] = None,
        api_key: str = "",
        poll_sec: float = 1.0,
        max_age_sec: float = 5.0,
        history_sec: float = 600.0,
        timeout: float = 3.0,
        fetcher: Optional[Callable[[str], str]] = None,
    ) -> None:
        self.map = mapping or ApiMapping.load()
        self.url = self.map.url or secret("SIGNAL_API_URL")
        self.key = api_key or secret("SIGNAL_API_KEY")
        self.poll_sec = poll_sec
        self.max_age_sec = max_age_sec
        self.history_sec = history_sec
        self.timeout = timeout
        self._fetch = fetcher or self._http_get

        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        # signal_id -> 전환 이력 [(전환시각, Observation)]
        self._hist: dict[str, list[Observation]] = {}
        # signal_id -> 마지막 관측 (신선도 판단용)
        self._last: dict[str, Observation] = {}
        self.stats = {"polls": 0, "ok": 0, "failed": 0, "items": 0, "changes": 0}
        self.last_error = ""

    # ------------------------------------------------------------------
    def ready(self) -> tuple[bool, str]:
        """설정이 갖춰졌는지. (가능 여부, 사람이 읽을 이유)"""
        if not self.url:
            return False, ("신호 API 주소가 없습니다. .env 의 SIGNAL_API_URL 또는 "
                           "signal_api.json 의 url 을 채우세요.")
        if not self.key:
            return False, ".env 에 SIGNAL_API_KEY 가 없습니다."
        return True, f"신호 API 준비됨 (키 {mask(self.key)})"

    # ------------------------------------------------------------------
    def build_url(self) -> str:
        params = dict(self.map.params)
        qs = urllib.parse.urlencode(params) if params else ""
        sep = "&" if "?" in self.url else "?"
        # 서비스키는 포털이 준 Encoding 값을 그대로 붙인다.
        # urlencode 에 넣으면 %2B 가 %252B 로 이중 인코딩돼 401 이 난다.
        url = f"{self.url}{sep}{self.map.key_param}={self.key}"
        return f"{url}&{qs}" if qs else url

    def _http_get(self, url: str) -> str:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return r.read().decode("utf-8", "replace")

    # ------------------------------------------------------------------
    def poll_once(self, now: Optional[float] = None) -> int:
        """한 번 조회해 이력에 반영한다. 반영한 교차로 수를 반환."""
        now = time.time() if now is None else now
        self.stats["polls"] += 1
        try:
            body = self._fetch(self.build_url())
            obj = parse_response(body)
        except urllib.error.HTTPError as e:
            self.last_error = f"HTTP {e.code}"
            self.stats["failed"] += 1
            log.warning("신호 API %s", self.last_error)
            return 0
        except Exception as e:
            self.last_error = f"{type(e).__name__}: {e}"
            self.stats["failed"] += 1
            log.warning("신호 API 조회 실패: %s", self.last_error)
            return 0

        items = find_items(obj, self.map.items_path)
        if not items:
            self.last_error = "응답에서 교차로 항목을 찾지 못함"
            self.stats["failed"] += 1
            return 0

        self.stats["ok"] += 1
        self.last_error = ""
        n = 0
        for it in items:
            sid = _pick(it, self.map.id_fields)
            if sid is None:
                continue
            phase = _to_phase(_pick(it, self.map.phase_fields), self.map.phase_map)
            ped = _to_ped(_pick(it, self.map.ped_fields), self.map.ped_map)
            remain = _pick(it, self.map.remain_fields)
            try:
                remain_f = float(remain) if remain is not None else None
            except (TypeError, ValueError):
                remain_f = None
            self._record(str(sid), Observation(now, phase, ped, remain_f))
            n += 1
        self.stats["items"] += n
        return n

    # ------------------------------------------------------------------
    def _record(self, sid: str, obs: Observation) -> None:
        with self._lock:
            prev = self._last.get(sid)
            self._last[sid] = obs
            hist = self._hist.setdefault(sid, [])

            if prev is not None and prev.phase is obs.phase and prev.ped is obs.ped:
                return                       # 변화 없음 → 이력에 안 쌓는다

            # 전환 시각 추정. 잔여시간이 있으면 그것으로 역산한다.
            if prev is None:
                change_ts = obs.ts
            elif prev.remain is not None:
                est = prev.ts + prev.remain
                # 추정치가 두 관측 사이를 벗어나면 신뢰하지 않는다
                change_ts = est if prev.ts <= est <= obs.ts else (prev.ts + obs.ts) / 2.0
            else:
                change_ts = (prev.ts + obs.ts) / 2.0

            hist.append(Observation(change_ts, obs.phase, obs.ped, obs.remain))
            self.stats["changes"] += 1

            cutoff = obs.ts - self.history_sec
            while len(hist) > 2 and hist[0].ts < cutoff:
                hist.pop(0)

    # ------------------------------------------------------------------
    def _lookup(self, sid: str, ts: float) -> Optional[Observation]:
        with self._lock:
            last = self._last.get(sid)
            hist = list(self._hist.get(sid, []))
        if last is None:
            return None
        # 마지막 관측이 너무 오래됐으면 판정 보류
        if last.ts < ts - self.max_age_sec:
            return None
        found = None
        for o in hist:
            if o.ts <= ts:
                found = o
            else:
                break
        # 이력의 첫 전환보다 이른 시각을 물으면 근거가 없다 → 보류
        return found

    # --- SignalProvider 인터페이스 ------------------------------------
    def phase_at(self, signal_id: str, ts: float) -> SignalPhase:
        o = self._lookup(signal_id, ts)
        return o.phase if o else SignalPhase.UNKNOWN

    def ped_phase_at(self, signal_id: str, ts: float) -> PedPhase:
        o = self._lookup(signal_id, ts)
        return o.ped if o else PedPhase.UNKNOWN

    def last_change(self, signal_id: str, ts: float) -> float:
        o = self._lookup(signal_id, ts)
        return o.ts if o else 0.0

    # ------------------------------------------------------------------
    def signal_ids(self) -> list[str]:
        with self._lock:
            return sorted(self._last)

    def start(self) -> "ApiSignal":
        """백그라운드 폴링 시작."""
        ok, why = self.ready()
        if not ok:
            log.warning("신호 API 비활성: %s", why)
            return self
        if self._thread is not None:
            return self
        self._thread = threading.Thread(target=self._worker, daemon=True,
                                        name="signal-api-poller")
        self._thread.start()
        log.info("신호 API 폴링 시작 (%.1f초 간격)", self.poll_sec)
        return self

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _worker(self) -> None:
        while not self._stop.is_set():
            self.poll_once()
            self._stop.wait(self.poll_sec)
