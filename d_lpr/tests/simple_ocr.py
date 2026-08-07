"""템플릿 매칭 기반 경량 OCR (검증 전용).

EasyOCR 은 torch 의존성이 커 테스트 환경에 두기 어렵다. 전처리 단계가
실제로 문자 판독성을 얼마나 개선하는지 **정량 측정**하기 위한 대체 인식기다.

전처리 유무를 같은 인식기로 비교하는 것이 목적이므로 절대 정확도보다
두 조건의 상대 차이가 의미를 갖는다. 운영 코드에는 쓰지 않는다.
"""

from __future__ import annotations

from functools import lru_cache

import cv2
import numpy as np

from app.lpr import plate_format as pf
from app.lpr import segment as plate_segment

from .plate_synth import _load_font

CHARSET = list("0123456789") + sorted(pf.PLATE_HANGUL)
TPL_SIZE = 32


@lru_cache(maxsize=1)
def _templates() -> dict[str, np.ndarray]:
    """문자별 정규화 템플릿 생성."""
    from PIL import Image, ImageDraw

    out: dict[str, np.ndarray] = {}
    font = _load_font(64)
    for ch in CHARSET:
        img = Image.new("L", (96, 96), 255)
        d = ImageDraw.Draw(img)
        bbox = d.textbbox((0, 0), ch, font=font)
        d.text((48 - (bbox[0] + bbox[2]) / 2, 48 - (bbox[1] + bbox[3]) / 2),
               ch, font=font, fill=0)
        arr = np.array(img)
        inv = 255 - arr
        ys, xs = np.nonzero(inv > 40)
        if len(xs) == 0:
            continue
        crop = inv[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
        out[ch] = _norm(crop)
    return out


def _norm(patch: np.ndarray) -> np.ndarray:
    """문자 패치를 비율 유지하며 정사각 템플릿 크기로 정규화."""
    h, w = patch.shape[:2]
    if h == 0 or w == 0:
        return np.zeros((TPL_SIZE, TPL_SIZE), np.float32)
    scale = (TPL_SIZE - 6) / max(h, w)
    nh, nw = max(1, int(round(h * scale))), max(1, int(round(w * scale)))
    r = cv2.resize(patch, (nw, nh), interpolation=cv2.INTER_AREA)
    canvas = np.zeros((TPL_SIZE, TPL_SIZE), np.uint8)
    oy, ox = (TPL_SIZE - nh) // 2, (TPL_SIZE - nw) // 2
    canvas[oy:oy + nh, ox:ox + nw] = r
    f = canvas.astype(np.float32)
    f -= f.mean()
    n = np.linalg.norm(f)
    return f / n if n > 1e-6 else f


def _segment(gray: np.ndarray) -> list[tuple[int, np.ndarray]]:
    """문자 후보를 좌→우 순으로 잘라낸다.

    분할 규칙은 운영 코드(app/lpr/segment.py)와 동일해야 측정이 의미가 있으므로
    그대로 가져다 쓴다.
    """
    if gray is None or gray.size == 0:
        return []
    g = gray if len(gray.shape) == 2 else cv2.cvtColor(gray, cv2.COLOR_BGR2GRAY)
    thr = plate_segment.binarize_text(g)
    chars = []
    for box in plate_segment.segment(g):
        patch = (thr[box.y1:box.y2, box.x1:box.x2] > 0).astype(np.uint8) * 255
        if patch.size == 0:
            continue
        chars.append((box.x1, patch))
    return chars


def read_plate(gray: np.ndarray) -> tuple[str, float]:
    """번호판 문자열과 평균 매칭 점수를 반환한다."""
    tpls = _templates()
    out, scores = [], []
    for _, patch in _segment(gray):
        v = _norm(patch)
        best_ch, best_s = "", -1.0
        for ch, t in tpls.items():
            s = float((v * t).sum())
            if s > best_s:
                best_s, best_ch = s, ch
        if best_ch:
            out.append(best_ch)
            scores.append(best_s)
    return "".join(out), (sum(scores) / len(scores) if scores else 0.0)


def char_accuracy(truth: str, pred: str) -> float:
    """자리별 정확도. 길이가 다르면 편집거리 기반으로 계산한다."""
    t, p = pf.canonical(truth), pf.canonical(pred)
    if not t:
        return 0.0
    if len(t) == len(p):
        return sum(1 for a, b in zip(t, p) if a == b) / len(t)
    # Levenshtein
    prev = list(range(len(p) + 1))
    for i, ct in enumerate(t, 1):
        cur = [i]
        for j, cp in enumerate(p, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ct != cp)))
        prev = cur
    return max(0.0, 1.0 - prev[-1] / len(t))
