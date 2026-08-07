"""한국형 번호판 포맷 검증 및 OCR 오인식 보정.

EasyOCR 원문은 공백/기호가 섞이고 숫자-영문이 혼동되어 나온다.
여기서 정규화 → 문자 혼동 보정 → 포맷 검증까지 처리해
DB 대조 단계로 깨끗한 문자열만 넘긴다.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Optional

# --------------------------------------------------------------------------
# 번호판에 실제로 쓰이는 한글 (자가용 + 영업용 + 렌터카 + 택배)
# --------------------------------------------------------------------------
PRIVATE_HANGUL = list("가나다라마거너더러머버서어저고노도로모보소오조구누두루무부수우주")
COMMERCIAL_HANGUL = list("아바사자")       # 택시·버스·화물 등 영업용
RENT_HANGUL = list("하허호")               # 렌터카
DELIVERY_HANGUL = ["배"]                   # 택배
PLATE_HANGUL = set(PRIVATE_HANGUL + COMMERCIAL_HANGUL + RENT_HANGUL + DELIVERY_HANGUL)

REGIONS = [
    "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
    "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주",
]

# --------------------------------------------------------------------------
# 포맷 정의
#   NEW2    : 12가3456       (2006~, 두 자리)
#   NEW3    : 123가4567      (2019~, 세 자리)
#   OLD_REG : 서울12가3456   (구형 지역 표기)
#   DIPLO   : 외교123-456    (외교용, 참고용)
# --------------------------------------------------------------------------
HANGUL_CLASS = "".join(sorted(PLATE_HANGUL))
REGION_CLASS = "|".join(REGIONS)

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("NEW3", re.compile(rf"^(\d{{3}})([{HANGUL_CLASS}])(\d{{4}})$")),
    ("NEW2", re.compile(rf"^(\d{{2}})([{HANGUL_CLASS}])(\d{{4}})$")),
    ("OLD_REG", re.compile(rf"^({REGION_CLASS})(\d{{2}})([{HANGUL_CLASS}])(\d{{4}})$")),
]

# 숫자 자리에서 잘못 읽히는 영문/기호 → 숫자
DIGIT_FIX = {
    "O": "0", "o": "0", "D": "0", "Q": "0", "()": "0",
    "I": "1", "i": "1", "l": "1", "|": "1", "!": "1", "L": "1",
    "Z": "2", "z": "2",
    "E": "3", "ㅋ": "3",
    "A": "4", "һ": "4",
    "S": "5", "s": "5", "$": "5",
    "G": "6", "b": "6",
    "T": "7", "?": "7",
    "B": "8", "&": "8",
    "g": "9", "q": "9",
}

# 한글 한 자리에서 흔히 튀는 오인식 (모양 유사)
HANGUL_FIX = {
    "기": "가", "카": "가", "각": "가", "가1": "가",
    "니": "나", "나1": "나",
    "다1": "다", "타": "다",
    "리": "러", "라1": "라",
    "머1": "머", "며": "머",
    "보1": "보", "부1": "부",
    "오1": "오", "우1": "우",
    "저1": "저", "조1": "조",
    "허1": "허", "히": "허",
    "호1": "호", "흐": "호",
}

_NOISE = re.compile(r"[^0-9A-Za-z가-힣]")


@dataclass
class NormalizedPlate:
    text: str
    valid: bool
    plate_type: str          # NEW2 | NEW3 | OLD_REG | invalid
    changed: bool = False    # 보정으로 문자가 바뀌었는지
    region: str = ""


def strip_noise(raw: str) -> str:
    """공백·하이픈·특수문자 제거 및 유니코드 정규화."""
    s = unicodedata.normalize("NFC", raw or "")
    return _NOISE.sub("", s)


def _fix_digits(chunk: str) -> str:
    return "".join(DIGIT_FIX.get(ch, ch) for ch in chunk)


def _fix_hangul(ch: str) -> str:
    if ch in PLATE_HANGUL:
        return ch
    return HANGUL_FIX.get(ch, ch)


def _split_by_hangul(s: str) -> Optional[tuple[str, str, str]]:
    """문자열을 (앞부분, 한글1자, 뒷부분)으로 분리.

    한글이 여러 개면 지역명(앞 2자)을 제외한 마지막 한글을 분류 문자로 본다.
    """
    idxs = [i for i, ch in enumerate(s) if "가" <= ch <= "힣"]
    if not idxs:
        return None
    # 지역 표기(맨 앞 2글자 한글)는 건너뛴다
    body_idxs = [i for i in idxs if i >= 2] or idxs
    i = body_idxs[-1]
    return s[:i], s[i], s[i + 1:]


def correct(raw: str) -> NormalizedPlate:
    """OCR 원문 → 정규화 + 보정 + 포맷 판정."""
    s = strip_noise(raw)
    if not s:
        return NormalizedPlate("", False, "invalid")

    original = s

    # 1차: 있는 그대로 포맷 매칭
    hit = _match(s)
    if hit:
        return NormalizedPlate(s, True, hit[0], False, hit[1])

    # 2차: 자리별 보정 (숫자 자리엔 숫자만, 한글 자리엔 한글만)
    parts = _split_by_hangul(s)
    if parts:
        head, mid, tail = parts
        region = ""
        if len(head) >= 2 and head[:2] in REGIONS:
            region, head = head[:2], head[2:]
        head = _fix_digits(head)
        tail = _fix_digits(tail)
        mid = _fix_hangul(mid)
        s = f"{region}{head}{mid}{tail}"
    else:
        # 한글이 아예 안 읽힌 경우 → 숫자만이라도 살려둔다 (fuzzy 매칭용)
        s = _fix_digits(s)

    hit = _match(s)
    if hit:
        return NormalizedPlate(s, True, hit[0], s != original, hit[1])
    return NormalizedPlate(s, False, "invalid", s != original)


def _match(s: str) -> Optional[tuple[str, str]]:
    for name, pat in PATTERNS:
        m = pat.match(s)
        if m:
            region = m.group(1) if name == "OLD_REG" else ""
            return name, region
    return None


def is_valid(plate_no: str) -> bool:
    return _match(strip_noise(plate_no)) is not None


def canonical(plate_no: str) -> str:
    """DB 조회 키. 지역명을 떼고 숫자-한글-숫자만 남긴다.

    '서울12가3456' 과 '12가3456' 이 같은 차량을 가리키므로 조회 시 통일한다.
    """
    s = strip_noise(plate_no)
    if len(s) >= 2 and s[:2] in REGIONS:
        s = s[2:]
    return s


def plate_class(plate_no: str) -> str:
    """번호판 용도 분류. 통계 화면에서 영업용/렌터카 구분에 쓴다."""
    parts = _split_by_hangul(canonical(plate_no))
    if not parts:
        return "unknown"
    ch = parts[1]
    if ch in COMMERCIAL_HANGUL:
        return "commercial"
    if ch in RENT_HANGUL:
        return "rental"
    if ch in DELIVERY_HANGUL:
        return "delivery"
    if ch in PRIVATE_HANGUL:
        return "private"
    return "unknown"


def similarity(a: str, b: str) -> int:
    """같은 길이 문자열의 서로 다른 자리 수 (Hamming). 길이 다르면 큰 값."""
    a, b = canonical(a), canonical(b)
    if len(a) != len(b):
        return 99
    return sum(1 for x, y in zip(a, b) if x != y)
