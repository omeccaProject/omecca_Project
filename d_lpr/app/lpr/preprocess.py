"""한국형 번호판 전처리.

CCTV 번호판은 작고, 기울어지고, 야간엔 조명 반사로 뭉개진다.
OCR에 그대로 넣으면 인식률이 크게 떨어지므로 아래 순서로 정리한다.

    크롭 → 그레이스케일 → CLAHE 대비 보정 → 노이즈 제거
         → 기울기 보정(deskew) → 확대(upscale) → 이진화

OpenCV / NumPy가 없으면 전처리를 건너뛰고 원본을 그대로 돌려준다(Mock 모드).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

log = logging.getLogger("omeca.lpr.preprocess")

try:  # pragma: no cover - 환경 의존
    import cv2
    import numpy as np
    HAS_CV = True
except ImportError:  # pragma: no cover
    cv2 = None  # type: ignore
    np = None  # type: ignore
    HAS_CV = False


@dataclass
class PreprocessResult:
    image: Any                 # OCR 입력 이미지 (ndarray | None)
    binary: Any = None         # 이진화 결과 (디버그/폴백용)
    angle: float = 0.0         # 적용된 회전 각도
    applied: list[str] = None  # 적용된 단계 목록

    def __post_init__(self) -> None:
        if self.applied is None:
            self.applied = []


def crop(frame: Any, bbox_xyxy: tuple[int, int, int, int], pad: int = 4) -> Any:
    """bbox 크롭. 좌우 약간의 여백을 둬야 끝자리가 잘리지 않는다."""
    if not HAS_CV or frame is None:
        return frame
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = (int(v) for v in bbox_xyxy)

    # 패딩을 주기 전에 bbox 자체의 유효성을 확인한다.
    # (뒤집힌 좌표가 들어오면 패딩 때문에 유효한 것처럼 보여 엉뚱한 영역이 잘린다)
    if x2 <= x1 or y2 <= y1:
        return None
    if x2 <= 0 or y2 <= 0 or x1 >= w or y1 >= h:
        return None

    x1 = max(0, x1 - pad)
    y1 = max(0, y1 - pad)
    x2 = min(w, x2 + pad)
    y2 = min(h, y2 + pad)
    if x2 <= x1 or y2 <= y1:
        return None
    return frame[y1:y2, x1:x2]


def to_gray(img: Any) -> Any:
    if not HAS_CV or img is None:
        return img
    if len(img.shape) == 2:
        return img
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def enhance_contrast(gray: Any, clip: float = 2.5, grid: int = 8) -> Any:
    """CLAHE. 역광·야간 번호판의 국소 대비를 살린다."""
    if not HAS_CV or gray is None:
        return gray
    clahe = cv2.createCLAHE(clipLimit=clip, tileGridSize=(grid, grid))
    return clahe.apply(gray)


def denoise(gray: Any) -> Any:
    """양방향 필터. 문자 경계는 살리고 잡티만 뭉갠다.

    커널 크기를 이미지 높이에 맞춰 조절한다. 작은 번호판에 고정 크기(9)를 쓰면
    필터 반경이 문자 획 두께를 넘어서 글자 자체가 지워진다.
    """
    if not HAS_CV or gray is None or gray.size == 0:
        return gray
    h = gray.shape[0]
    d = 9 if h >= 64 else (5 if h >= 32 else 3)
    sigma = 75 if h >= 64 else 40
    return cv2.bilateralFilter(gray, d, sigma, sigma)


def _binarize_text(gray: Any) -> Any:
    """문자를 전경(255)으로 만드는 이진화.

    번호판은 밝은 바탕에 어두운 글자지만, 크롭에 어두운 차체 배경이 섞이면
    OTSU 결과의 극성이 뒤집힌다. 전경 비율을 보고 극성을 바로잡는다.
    """
    thr = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]
    if float((thr > 0).mean()) > 0.5:
        thr = cv2.bitwise_not(thr)
    return thr


def _plate_rect_angle(gray: Any, limit: float) -> Optional[float]:
    """번호판 판(밝은 사각형) 자체의 기울기.

    문자 수가 적어도 판 테두리는 항상 보이므로, 문자 중심선 추정을 검증하는
    독립적인 근거가 된다.
    """
    try:
        thr = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
        k = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        thr = cv2.morphologyEx(thr, cv2.MORPH_CLOSE, k)
        n, labels, stats, _ = cv2.connectedComponentsWithStats(thr, 8)
        if n <= 1:
            return None
        i = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        pts = cv2.findNonZero((labels == i).astype(np.uint8))
        if pts is None or len(pts) < 20:
            return None
        (_, _), (rw, rh), a = cv2.minAreaRect(pts)
        if rw < rh:                      # 항상 '가로가 긴' 기준으로 정규화
            a += 90.0
        while a > 45:
            a -= 90
        while a < -45:
            a += 90
        return float(a) if abs(a) <= limit else None
    except Exception:
        return None


def estimate_skew(gray: Any, limit: float = 20.0, cross_check_deg: float = 6.0) -> float:
    """번호판 기울기 추정.

    문자 블롭들의 중심점이 이루는 직선의 기울기를 각도로 삼는다.

    minAreaRect 방식은 크롭에 배경이 섞이면 전경이 화면을 가득 채워
    외접 사각형이 이미지 전체로 붕괴하므로 쓰지 않는다. 문자 후보를
    크기·비율로 걸러낸 뒤 중심선을 피팅하면 배경에 훨씬 강인하다.
    문자 후보가 부족할 때만 허프 직선으로 대체한다.
    """
    if not HAS_CV or gray is None or gray.size == 0:
        return 0.0
    try:
        h, w = gray.shape[:2]
        if h < 8 or w < 16:
            return 0.0

        thr = _binarize_text(gray)
        n, _, stats, centroids = cv2.connectedComponentsWithStats(thr, connectivity=8)

        pts = []
        for i in range(1, n):
            cw = stats[i, cv2.CC_STAT_WIDTH]
            ch = stats[i, cv2.CC_STAT_HEIGHT]
            area = stats[i, cv2.CC_STAT_AREA]
            if ch < h * 0.18 or ch > h * 0.95:      # 너무 작은 잡티 / 배경 덩어리 제외
                continue
            if cw < 2 or cw > w * 0.4:
                continue
            ar = cw / float(ch)
            if not (0.08 <= ar <= 1.8):             # 문자 형태 비율
                continue
            if area < ch * cw * 0.12:               # 속이 빈 윤곽 제외
                continue
            pts.append(centroids[i])

        angle = None
        if len(pts) >= 3:
            arr = np.array(pts, dtype=np.float32)
            # 좌우로 퍼져 있어야 문자열로 인정 (세로 정렬은 번호판이 아님)
            if arr[:, 0].ptp() > w * 0.25:
                vx, vy = cv2.fitLine(arr, cv2.DIST_L2, 0, 0.01, 0.01)[:2]
                angle = float(np.degrees(np.arctan2(float(vy), float(vx))))

        # 글자가 몇 개 안 보이면(가려짐·저해상도) 중심선 피팅이 크게 흔들린다.
        # 판 테두리에서 얻은 독립 추정과 교차 검증해, 어긋나면 보정하지 않는다.
        # (실측: 검증 없이 쓰면 거의 수평인 실제 번호판을 11~16도씩 잘못 돌렸다)
        plate_angle = _plate_rect_angle(gray, limit)
        if angle is not None:
            if plate_angle is None:
                # 판 테두리조차 못 찾으면 근거가 하나뿐이다. 큰 각도는 믿지 않는다.
                if abs(angle) > cross_check_deg * 2:
                    angle = None
            elif abs(angle - plate_angle) > cross_check_deg:
                log.debug("기울기 추정 불일치 (문자 %.1f / 판 %.1f) → 보정 생략",
                          angle, plate_angle)
                angle = None

        if angle is None:
            angle = plate_angle
        if angle is None:
            angle = _hough_skew(thr, limit)

        if angle is None:
            return 0.0
        # -45 ~ +45 범위로 정규화
        while angle > 45:
            angle -= 90
        while angle < -45:
            angle += 90
        if abs(angle) > limit:
            return 0.0
        return float(angle)
    except Exception:
        log.debug("skew estimation failed", exc_info=True)
        return 0.0


def _hough_skew(binary: Any, limit: float) -> Optional[float]:
    """문자 후보가 부족할 때 쓰는 대체 추정: 지배적인 수평 직선의 기울기."""
    edges = cv2.Canny(binary, 50, 150)
    lines = cv2.HoughLinesP(
        edges, 1, np.pi / 360, threshold=40,
        minLineLength=max(20, binary.shape[1] // 4), maxLineGap=8,
    )
    if lines is None:
        return None
    angles = []
    for x1, y1, x2, y2 in lines[:, 0]:
        a = np.degrees(np.arctan2(float(y2 - y1), float(x2 - x1)))
        if a > 90:
            a -= 180
        elif a < -90:
            a += 180
        if abs(a) <= limit:          # 수평에 가까운 직선만
            angles.append(a)
    if not angles:
        return None
    return float(np.median(angles))


def rotate(img: Any, angle: float) -> Any:
    if not HAS_CV or img is None or abs(angle) < 0.3:
        return img
    h, w = img.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(
        img, m, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
    )


def trim_to_plate(gray: Any, margin: float = 0.06) -> Any:
    """번호판 판 영역만 남기고 주변 여백을 잘라낸다.

    bbox 크롭은 축 정렬이라 기울어진 번호판일수록 모서리에 배경이 크게 남고,
    기울기 보정 후에도 그대로 남아 이진화·OCR을 방해한다. 밝은 판 영역을
    찾아 그 부분만 남기면 문자 대비가 뚜렷해진다.
    """
    if not HAS_CV or gray is None or gray.size == 0:
        return gray
    h, w = gray.shape[:2]
    if h < 12 or w < 24:
        return gray
    try:
        thr = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
        k = cv2.getStructuringElement(cv2.MORPH_RECT, (max(3, w // 40), max(3, h // 20)))
        thr = cv2.morphologyEx(thr, cv2.MORPH_CLOSE, k)
        n, _, stats, _ = cv2.connectedComponentsWithStats(thr, 8)
        if n <= 1:
            return gray

        i = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        x = int(stats[i, cv2.CC_STAT_LEFT]); y = int(stats[i, cv2.CC_STAT_TOP])
        cw = int(stats[i, cv2.CC_STAT_WIDTH]); ch = int(stats[i, cv2.CC_STAT_HEIGHT])
        if cw < 24 or ch < 12:
            return gray

        # 판정 기준은 '이미지 대비 비율'이 아니라 '번호판다운 생김새'여야 한다.
        # 비율로 재면 여백이 큰 이미지(정작 정리가 가장 필요한 경우)에서 거부된다.
        ar = cw / float(ch)
        if not (1.5 <= ar <= 8.0):
            return gray

        # 판 안에 글자(어두운 화소)가 있어야 번호판이다.
        # 균일한 밝은 면(차체·하늘)을 번호판으로 오인하는 것을 막는다.
        inner = gray[y:y + ch, x:x + cw]
        dark_ratio = float((inner < inner.mean()).mean())
        if not (0.08 <= dark_ratio <= 0.65):
            return gray

        mx, my = int(cw * margin), int(ch * margin)
        x1, y1 = max(0, x - mx), max(0, y - my)
        x2, y2 = min(w, x + cw + mx), min(h, y + ch + my)
        if x2 - x1 < 24 or y2 - y1 < 12:
            return gray
        return gray[y1:y2, x1:x2]
    except Exception:
        log.debug("여백 정리 실패", exc_info=True)
        return gray


def upscale(img: Any, target_h: int = 96) -> Any:
    """OCR 입력 높이 정규화. 너무 작은 번호판은 확대해야 인식된다."""
    if not HAS_CV or img is None:
        return img
    h, w = img.shape[:2]
    if h <= 0 or h >= target_h:
        return img
    scale = target_h / h
    return cv2.resize(img, (int(w * scale), target_h), interpolation=cv2.INTER_CUBIC)


def binarize(gray: Any) -> Any:
    """적응형 이진화. 조명이 균일하지 않은 CCTV 영상에 유리하다."""
    if not HAS_CV or gray is None:
        return gray
    return cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 25, 12
    )


def run(
    frame: Any,
    bbox_xyxy: Optional[tuple[int, int, int, int]] = None,
    target_h: int = 96,
    deskew_limit: float = 30.0,
    denoise_min_height: int = 28,
) -> PreprocessResult:
    """전처리 파이프라인 전체 실행.

    단계 순서와 임계값은 합성 데이터 실측으로 정했다 (bench_lpr.py 참고).
        확대 → 대비 보정 → (조건부) 잡음 제거 → 기울기 보정 → 여백 정리 → 이진화
    """
    if not HAS_CV or frame is None:
        return PreprocessResult(image=frame, applied=["skipped:no-opencv"])

    steps: list[str] = []
    img = crop(frame, bbox_xyxy) if bbox_xyxy else frame
    if img is None or getattr(img, "size", 0) == 0:
        return PreprocessResult(image=None, applied=["empty-crop"])
    steps.append("crop")

    gray = to_gray(img); steps.append("gray")
    src_h = gray.shape[0]

    # 확대를 먼저 한다. 저해상도 번호판에 필터를 먼저 걸면 커널 반경이
    # 문자 획보다 커져 글자가 지워진다(실측: 16px 번호판 정확도 0.70 → 0.23).
    gray = upscale(gray, target_h); steps.append("upscale")

    gray = enhance_contrast(gray); steps.append("clahe")

    # 원본이 아주 작았다면 확대된 화소는 보간으로 만들어진 값이라 이미 매끄럽다.
    # 여기에 잡음 제거를 더하면 문자만 더 뭉갠다(실측 16px: 0.95 → 0.62).
    if src_h >= denoise_min_height:
        gray = denoise(gray); steps.append("denoise")
    else:
        steps.append("denoise:skipped")

    angle = estimate_skew(gray, deskew_limit)
    if abs(angle) >= 0.3:
        gray = rotate(gray, angle)
        steps.append(f"deskew({angle:.1f})")

    # bbox 크롭은 검출기가 잡아준 사각형 그대로라 테두리·볼트·차체가 섞여
    # 들어온다. 회전 여부와 무관하게 항상 판 영역만 추려야
    # 자리별 분할(segment.py)이 테두리를 글자로 오인하지 않는다.
    # (이전엔 회전이 실제로 일어났을 때만 trim 했다 — 이미 수평인 번호판이
    #  오히려 테두리를 안 걷어내고 그대로 넘어가는 역설이 있었다)
    gray = trim_to_plate(gray); steps.append("trim")
    gray = upscale(gray, target_h)

    binary = binarize(gray); steps.append("binarize")

    return PreprocessResult(image=gray, binary=binary, angle=angle, applied=steps)
