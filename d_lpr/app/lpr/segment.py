"""번호판 문자 분할.

번호판을 글자 단위 영역으로 나눈다. 자리별 allowlist 인식(recognizer 의
2패스 방식)이 '몇 번째 글자가 한글 자리인지'를 알아야 하므로 필요하다.

한글은 자모가 떨어진 성분으로 잡히므로(가 = ㄱ + ㅏ) 병합 규칙이 핵심이다.
글자 간격만으로는 자모 경계와 글자 경계를 구분할 수 없어(실측상 둘 다 문자
높이의 0.06~0.13) 모음의 형태 특성을 쓴다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

log = logging.getLogger("omeca.lpr.segment")

try:  # pragma: no cover - 환경 의존
    import cv2
    import numpy as np
    HAS_CV = True
except ImportError:  # pragma: no cover
    cv2 = None  # type: ignore
    np = None  # type: ignore
    HAS_CV = False


@dataclass
class CharBox:
    """글자 하나의 영역."""

    x1: int
    y1: int
    x2: int
    y2: int

    @property
    def width(self) -> int:
        return self.x2 - self.x1

    @property
    def height(self) -> int:
        return self.y2 - self.y1

    @property
    def cx(self) -> float:
        return (self.x1 + self.x2) / 2.0

    def to_tuple(self) -> tuple[int, int, int, int]:
        return self.x1, self.y1, self.x2, self.y2

    def expand(self, mx: int, my: int, w: int, h: int) -> "CharBox":
        return CharBox(
            max(0, self.x1 - mx), max(0, self.y1 - my),
            min(w, self.x2 + mx), min(h, self.y2 + my),
        )


# 세로 모음 판정 기준.
#
#   실사진 47장으로 0.34/0.08 까지 조여 보았다. 글자 수를 정확히 맞추는 비율은
#   36%→77% 로 크게 올랐지만, **최종 인식 정확도는 78%→76% 로 오히려 떨어졌다.**
#   분할이 잘 되는 사진은 원래도 잘 읽혔고, 새로 2패스에 들어온 어려운 사진들이
#   2패스 정확도를 100%→85% 로 끌어내렸기 때문이다.
#   중간 지표(분할 정확도)가 좋아진다고 최종 지표가 좋아지지는 않는다.
#   그래서 실측이 더 나았던 원래 값으로 되돌렸다.
VOWEL_RATIO = 0.50
GAP_RATIO = 0.22


def binarize_text(gray: Any) -> Any:
    """문자를 전경(255)으로 만드는 이진화.

    번호판은 밝은 바탕에 어두운 글자지만 크롭에 어두운 배경이 섞이면 극성이
    뒤집히므로, 전경 비율을 보고 바로잡는다.
    """
    thr = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]
    if float((thr > 0).mean()) > 0.5:
        thr = cv2.bitwise_not(thr)
    return thr


def segment(gray: Any, vowel_ratio: float = VOWEL_RATIO,
            gap_ratio: float = GAP_RATIO) -> list[CharBox]:
    """번호판 이미지를 글자 영역 목록(좌→우)으로 나눈다."""
    if not HAS_CV or gray is None or getattr(gray, "size", 0) == 0:
        return []
    g = gray if len(gray.shape) == 2 else cv2.cvtColor(gray, cv2.COLOR_BGR2GRAY)
    h, w = g.shape[:2]
    if h < 12 or w < 24:
        return []

    try:
        thr = binarize_text(g)
        n, _, stats, _ = cv2.connectedComponentsWithStats(thr, 8)
    except Exception:
        log.debug("문자 분할 실패", exc_info=True)
        return []

    boxes: list[list[int]] = []
    for i in range(1, n):
        x = int(stats[i, cv2.CC_STAT_LEFT]); y = int(stats[i, cv2.CC_STAT_TOP])
        cw = int(stats[i, cv2.CC_STAT_WIDTH]); ch = int(stats[i, cv2.CC_STAT_HEIGHT])
        if ch < h * 0.18 or ch > h * 0.95:      # 잡티 / 테두리 제외
            continue
        # 폭 제한은 '이미지 폭 대비'가 아니라 '자기 높이 대비'로 건다.
        # 이미지 폭 기준으로 두면 한 글자만 잘라낸 크롭에서 정상 글자가 걸러진다.
        if cw < 2 or not (0.05 <= cw / float(ch) <= 2.0):
            continue
        boxes.append([x, y, x + cw, y + ch])

    merged = merge_syllables(boxes, vowel_ratio, gap_ratio)
    return [
        CharBox(*b) for b in merged
        if (b[3] - b[1]) >= h * 0.3 and (b[2] - b[0]) >= 2
    ]


def merge_syllables(boxes: list[list[int]], vowel_ratio: float = VOWEL_RATIO,
                    gap_ratio: float = GAP_RATIO) -> list[list[int]]:
    """한글 자모로 쪼개진 성분을 하나의 음절로 합친다.

      - 세로 모음(ㅏㅓㅣ 등): 좁고 길다 → 폭/높이 비가 작으면 앞 글자에 붙인다
      - 가로 모음(ㅗㅜ 등): 자음 아래에 놓인다 → x 구간이 크게 겹치면 붙인다

    임계값은 이미지 높이가 아니라 실제 문자 높이를 기준으로 잡는다.
    (이미지 높이로 잡으면 숫자끼리도 합쳐져 전부 뭉개진다)
    """
    if not boxes:
        return []
    boxes = sorted((b[:] for b in boxes), key=lambda b: b[0])
    heights = sorted(b[3] - b[1] for b in boxes)
    char_h = float(heights[len(heights) // 2])
    if char_h <= 0:
        return boxes
    # 한글 음절은 숫자보다 넓다. 1.15 로 두면 '사'(ㅅ+ㅏ, 폭 60 vs 한계 58.6)처럼
    # 아슬아슬하게 병합에 실패한다. 1.35 로 두어도 숫자 두 개(폭 74)는 걸러진다.
    max_w = char_h * 1.35
    gap_thr = char_h * gap_ratio

    merged = [boxes[0][:]]
    for b in boxes[1:]:
        cur = merged[-1]
        bw, bh = b[2] - b[0], b[3] - b[1]
        gap = b[0] - cur[2]
        would_w = max(cur[2], b[2]) - min(cur[0], b[0])
        overlap = min(cur[2], b[2]) - max(cur[0], b[0])
        overlap_ratio = overlap / float(min(cur[2] - cur[0], bw) or 1)

        vertical_vowel = bh > 0 and (bw / float(bh)) < vowel_ratio and gap < gap_thr
        horizontal_vowel = overlap_ratio > 0.5

        # '도·보' 처럼 모음이 자음 아래에 놓이면 각 부품의 높이가 음절 높이보다
        # 훨씬 작다. 부품 높이 기준으로만 재면 실제 글자를 못 합친다.
        would_h = max(cur[3], b[3]) - min(cur[1], b[1])
        width_limit = max(max_w, would_h * 1.2)

        if (vertical_vowel or horizontal_vowel) and would_w <= width_limit:
            cur[0] = min(cur[0], b[0]); cur[1] = min(cur[1], b[1])
            cur[2] = max(cur[2], b[2]); cur[3] = max(cur[3], b[3])
        else:
            merged.append(b[:])
    return merged


# --------------------------------------------------------------------------
# 번호판 배치 해석
# --------------------------------------------------------------------------
#   7글자 : 숫자 2 + 한글 1 + 숫자 4   (12가3456)
#   8글자 : 숫자 3 + 한글 1 + 숫자 4   (123가4567)
HANGUL_INDEX = {7: 2, 8: 3}


def hangul_index(char_count: int) -> Optional[int]:
    """글자 수로부터 한글이 놓이는 자리를 알아낸다."""
    return HANGUL_INDEX.get(char_count)


def split_layout(boxes: list[CharBox]) -> Optional[tuple[list[CharBox], CharBox, list[CharBox]]]:
    """(앞 숫자들, 한글, 뒤 숫자들) 로 분리. 형식에 안 맞으면 None.

    글자 수만 보고 자리를 정하면, 한글이 자모로 쪼개져 8개로 잡힌 7글자 판을
    8글자 배치로 오인해 **엉뚱한 자리를 한글로 지목**하게 된다. 한글 음절은
    숫자보다 넓다는 성질로 한 번 더 확인한다.
    """
    idx = hangul_index(len(boxes))
    if idx is None:
        return None

    head, hangul, tail = boxes[:idx], boxes[idx], boxes[idx + 1:]
    digits = head + tail
    if digits:
        widths = sorted(b.width for b in digits)
        median_w = widths[len(widths) // 2]
        if median_w > 0 and hangul.width < median_w * 1.05:
            log.debug("한글 자리 검증 실패: 폭 %d < 숫자 중앙값 %d", hangul.width, median_w)
            return None
    return head, hangul, tail


def mask_region(gray: Any, box: CharBox, pad: int = 2) -> Any:
    """지정 영역을 배경색으로 덮은 복사본을 만든다.

    한글 자리를 지운 뒤 숫자 전용 allowlist 로 인식하면, 한글이 숫자로
    잘못 읽혀 끼어드는 문제를 원천 차단할 수 있다.
    """
    if not HAS_CV or gray is None:
        return gray
    out = gray.copy()
    h, w = out.shape[:2]
    b = box.expand(pad, pad, w, h)
    # 번호판 바탕색 = 밝은 쪽. 상위 백분위수를 배경값으로 쓴다.
    bg = int(np.percentile(out, 85))
    out[b.y1:b.y2, b.x1:b.x2] = bg
    return out


def crop(gray: Any, box: CharBox, pad_x: int = 4, pad_y: int = 4) -> Any:
    if not HAS_CV or gray is None:
        return None
    h, w = gray.shape[:2]
    b = box.expand(pad_x, pad_y, w, h)
    if b.width < 2 or b.height < 2:
        return None
    return gray[b.y1:b.y2, b.x1:b.x2]
