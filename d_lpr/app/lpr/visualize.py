"""인식 결과 시각화.

OpenCV 의 putText 는 한글을 그리지 못하므로(??? 로 깨짐) PIL 로 그린다.
관제 화면 오버레이와 발표 자료용 캡처에 함께 쓴다.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional, Sequence

log = logging.getLogger("omeca.lpr.visualize")

try:  # pragma: no cover - 환경 의존
    import cv2
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont
    HAS_DRAW = True
except ImportError:  # pragma: no cover
    cv2 = None  # type: ignore
    np = None  # type: ignore
    HAS_DRAW = False


# --------------------------------------------------------------------------
# 한글 경로 안전 입출력
#
# 번호판 사진은 파일명이 '12가3456.jpg' 처럼 한글이고, 데이터 폴더명에도
# 한글이 섞인다. cv2.imread/imwrite 는 Windows 에서 경로를 ANSI 코드페이지로
# 넘기기 때문에 이런 경로에서 조용히 실패한다(None 반환 / 저장 안 됨).
# 파이썬 파일 API 로 바이트를 직접 주고받아 우회한다.
# --------------------------------------------------------------------------
def imread_unicode(path) -> Any:
    """한글 경로에서도 안전하게 이미지를 읽는다. 실패 시 None."""
    if not HAS_DRAW:
        return None
    p = Path(path)
    try:
        data = p.read_bytes()
    except OSError:
        return None
    if not data:
        return None
    return cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)


def imwrite_unicode(path, img, jpeg_quality: int = 0) -> bool:
    """한글 경로에서도 안전하게 이미지를 저장한다.

    `cv2.imwrite` 는 경로에 한글이 있으면 **아무것도 쓰지 않고 False 만**
    돌려준다 (예외도 안 난다). 그래서 인코딩만 OpenCV 로 하고 파일 쓰기는
    파이썬으로 한다.

    jpeg_quality 를 주면 .jpg 저장 시 품질을 지정한다 (1~100).
    """
    if not HAS_DRAW or img is None:
        return False
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    ext = p.suffix or ".jpg"
    params = []
    if jpeg_quality and ext.lower() in (".jpg", ".jpeg"):
        params = [cv2.IMWRITE_JPEG_QUALITY, int(jpeg_quality)]
    ok, buf = cv2.imencode(ext, img, params)
    if not ok:
        return False
    p.write_bytes(buf.tobytes())
    return True

# 한글 글리프가 있는 폰트 후보 (Windows / Linux)
FONT_CANDIDATES: list[tuple[str, int]] = [
    ("C:/Windows/Fonts/malgunbd.ttf", 0),
    ("C:/Windows/Fonts/malgun.ttf", 0),
    ("C:/Windows/Fonts/NanumGothicBold.ttf", 0),
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 1),
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 1),
    ("/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf", 0),
    ("/System/Library/Fonts/AppleSDGothicNeo.ttc", 0),
]

# 위험도별 색상 (BGR)
COLOR = {
    "high": (73, 81, 248),        # 빨강
    "caution": (65, 179, 227),    # 노랑
    "normal": (80, 185, 63),      # 초록
    "unknown": (158, 158, 158),   # 회색
}


@lru_cache(maxsize=8)
def _font(size: int):
    for path, index in FONT_CANDIDATES:
        if not Path(path).exists():
            continue
        try:
            f = ImageFont.truetype(path, size, index=index)
            if f.getbbox("가")[2] > 0:
                return f
        except Exception:
            continue
    log.warning("한글 폰트를 찾지 못해 기본 폰트로 그립니다 (한글이 깨질 수 있음)")
    return ImageFont.load_default()


def draw_label(
    img: Any,
    xy: tuple[int, int],
    text: str,
    color: tuple[int, int, int] = (255, 255, 255),
    font_size: int = 20,
    bg: bool = True,
) -> Any:
    """한글 라벨을 그린다. 이미지를 새로 만들어 반환한다."""
    if not HAS_DRAW or img is None:
        return img
    pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    d = ImageDraw.Draw(pil)
    font = _font(font_size)
    x, y = xy

    lines = text.split("\n")
    heights, widths = [], []
    for line in lines:
        bb = d.textbbox((0, 0), line, font=font)
        widths.append(bb[2] - bb[0])
        heights.append(bb[3] - bb[1] + 6)

    if bg:
        pad = 6
        w = max(widths) + pad * 2
        h = sum(heights) + pad
        y0 = max(0, y - h)
        d.rectangle([x, y0, x + w, y0 + h], fill=(20, 22, 28))
        d.rectangle([x, y0, x + 4, y0 + h], fill=tuple(reversed(color)))
        cy = y0 + pad // 2
        for line, lh in zip(lines, heights):
            d.text((x + pad + 4, cy), line, font=font, fill=(240, 245, 250))
            cy += lh
    else:
        d.text((x, y), text, font=font, fill=tuple(reversed(color)))

    return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)


def draw_box(
    img: Any,
    box: Sequence[float],
    color: tuple[int, int, int] = (80, 185, 63),
    thickness: int = 2,
) -> Any:
    if not HAS_DRAW or img is None:
        return img
    x1, y1, x2, y2 = (int(v) for v in box)
    cv2.rectangle(img, (x1, y1), (x2, y2), color, thickness)
    # 모서리 강조
    L = max(8, int(min(x2 - x1, y2 - y1) * 0.2))
    for (px, py, dx, dy) in ((x1, y1, 1, 1), (x2, y1, -1, 1), (x1, y2, 1, -1), (x2, y2, -1, -1)):
        cv2.line(img, (px, py), (px + dx * L, py), color, thickness + 2)
        cv2.line(img, (px, py), (px, py + dy * L), color, thickness + 2)
    return img


def annotate_detection(
    img: Any,
    box: Sequence[float],
    plate_no: str = "",
    confidence: float = 0.0,
    risk_level: str = "unknown",
    extra: str = "",
    font_size: int = 20,
    low_confidence: bool = False,
) -> Any:
    """번호판 박스 + 인식 결과 라벨을 함께 그린다.

    low_confidence=True 면 글자는 읽었지만 신뢰도가 낮아 사람이 다시 봐야
    한다는 경고를 붙인다 (박스 색은 DB 위험도 표시이므로 그대로 둔다).
    """
    if not HAS_DRAW or img is None:
        return img
    color = COLOR.get(risk_level, COLOR["unknown"])
    out = draw_box(img, box, color)

    lines = [plate_no if plate_no else "인식 실패"]
    if confidence:
        lines[0] += f"  {confidence * 100:.0f}%"
    if low_confidence:
        lines.append("※ 신뢰도 낮음 · 재확인 필요")
    if extra:
        lines.append(extra)

    x1, y1 = int(box[0]), int(box[1])
    return draw_label(out, (x1, y1 - 4), "\n".join(lines), color, font_size)


def draw_banner(img: Any, text: str, font_size: int = 22) -> Any:
    """좌측 상단 상태 표시."""
    if not HAS_DRAW or img is None:
        return img
    return draw_label(img, (12, 12 + font_size * (text.count("\n") + 1) + 14),
                      text, (200, 200, 200), font_size)


def stack_stages(images: Sequence[tuple[str, Any]], width: int = 420) -> Any:
    """전처리 단계별 이미지를 세로로 이어 붙여 한 장으로 만든다."""
    if not HAS_DRAW or not images:
        return None
    tiles = []
    for name, im in images:
        if im is None:
            continue
        if len(im.shape) == 2:
            im = cv2.cvtColor(im, cv2.COLOR_GRAY2BGR)
        h, w = im.shape[:2]
        scale = width / w
        im = cv2.resize(im, (width, max(1, int(h * scale))), interpolation=cv2.INTER_NEAREST)
        im = cv2.copyMakeBorder(im, 34, 8, 8, 8, cv2.BORDER_CONSTANT, value=(20, 22, 28))
        im = draw_label(im, (10, 6), name, (255, 255, 255), 18, bg=False)
        tiles.append(im)
    return np.vstack(tiles) if tiles else None
