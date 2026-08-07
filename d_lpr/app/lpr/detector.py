"""번호판 영역 검출.

세 가지 백엔드를 순서대로 시도한다.
  1) YOLO  : 번호판 클래스로 학습된 YOLOv11 가중치 (가장 정확)
  2) CV    : 형태학 연산 + 윤곽선 기반 후보 추출 (가중치 없을 때 폴백)
  3) MOCK  : 차량 bbox 하단 중앙을 번호판으로 가정 (영상/모델 없이 시연)

김관용 담당 detector/ 모듈이 차량 bbox를 주면 그 안에서만 탐색하므로
전체 프레임을 훑는 것보다 훨씬 빠르고 오탐도 적다.
"""

from __future__ import annotations

import logging
from typing import Any, Optional, Sequence

from ..core.config import settings
from ..core.schemas import BBox

log = logging.getLogger("omeca.lpr.detector")

try:  # pragma: no cover
    import cv2
    import numpy as np
    HAS_CV = True
except ImportError:  # pragma: no cover
    cv2 = None  # type: ignore
    np = None  # type: ignore
    HAS_CV = False


class PlateDetector:
    """번호판 후보 영역을 반환한다."""

    def __init__(
        self,
        weights: Optional[str] = None,
        mock: Optional[bool] = None,
        min_area: Optional[int] = None,
        ar_range: Optional[tuple[float, float]] = None,
    ) -> None:
        cfg = settings.lpr
        self.mock = cfg.mock if mock is None else mock
        self.min_area = min_area if min_area is not None else cfg.min_plate_area
        self.ar_range = tuple(ar_range or cfg.plate_ar_range)
        self.model = None
        self.backend = "mock" if self.mock else "cv"

        if not self.mock and weights:
            self.model = self._load_yolo(weights)
            if self.model is not None:
                self.backend = "yolo"

    # ------------------------------------------------------------------
    @staticmethod
    def _load_yolo(weights: str):  # pragma: no cover - 가중치 의존
        try:
            from ultralytics import YOLO  # type: ignore
        except ImportError:
            log.warning("ultralytics 미설치 → CV 폴백으로 동작")
            return None
        try:
            return YOLO(weights)
        except Exception:
            log.exception("YOLO 가중치 로드 실패: %s", weights)
            return None

    # ------------------------------------------------------------------
    def detect(
        self,
        frame: Any,
        vehicle_bbox: Optional[BBox] = None,
        max_candidates: Optional[int] = None,
    ) -> list[BBox]:
        """번호판 후보 목록.

        vehicle_bbox 가 없으면 '전체 프레임 모드'로 동작한다. 이 경우 화면에
        번호판보다 큰 구조물(건물·차체·노면표시)이 잔뜩 있으므로, 프레임 크기
        대비 번호판이 가질 수 있는 크기 범위로 후보를 먼저 걸러야 한다.
        (실측: 이 필터 없이 면적순 정렬만 하면 4K 화면에서 검출률 0%)
        """
        if self.backend == "mock" or frame is None or not HAS_CV:
            return self._mock(vehicle_bbox)
        if self.backend == "yolo":
            boxes = self._detect_yolo(frame, vehicle_bbox)
            if boxes:
                return boxes
        return self._detect_cv(frame, vehicle_bbox, max_candidates)

    # ------------------------------------------------------------------
    def _mock(self, vehicle_bbox: Optional[BBox]) -> list[BBox]:
        """차량 bbox 하단 중앙 = 번호판 위치로 가정."""
        if vehicle_bbox is None:
            return []
        w, h = vehicle_bbox.width, vehicle_bbox.height
        pw, ph = w * 0.34, h * 0.12
        cx = (vehicle_bbox.x1 + vehicle_bbox.x2) / 2
        y2 = vehicle_bbox.y2 - h * 0.10
        return [BBox(cx - pw / 2, y2 - ph, cx + pw / 2, y2)]

    def _detect_yolo(self, frame: Any, vehicle_bbox: Optional[BBox]) -> list[BBox]:  # pragma: no cover
        roi, ox, oy = self._roi(frame, vehicle_bbox)
        if roi is None:
            return []
        try:
            res = self.model.predict(roi, verbose=False)[0]
        except Exception:
            log.exception("YOLO 추론 실패")
            return []
        out: list[BBox] = []
        for b in getattr(res, "boxes", []):
            x1, y1, x2, y2 = [float(v) for v in b.xyxy[0].tolist()]
            out.append(BBox(x1 + ox, y1 + oy, x2 + ox, y2 + oy))
        return out

    def _detect_cv(
        self, frame: Any, vehicle_bbox: Optional[BBox],
        max_candidates: Optional[int] = None,
    ) -> list[BBox]:
        """모폴로지 기반 후보 추출.

        번호판은 '가로로 긴 사각형 + 문자 밀집으로 인한 강한 수평 엣지' 특성이
        뚜렷하므로, blackhat → 수직 소벨 → 닫힘 연산으로 후보를 뽑는다.
        """
        roi, ox, oy = self._roi(frame, vehicle_bbox)
        if roi is None or roi.size == 0:
            return []

        full_frame = vehicle_bbox is None
        H, W = frame.shape[:2]
        if full_frame:
            cfg = settings.lpr
            h_lo = max(8.0, H * cfg.frame_plate_h_range[0])
            h_hi = H * cfg.frame_plate_h_range[1]
            w_hi = W * cfg.frame_plate_w_max
            limit = max_candidates or 20
        else:
            h_lo, h_hi, w_hi = 0.0, float("inf"), float("inf")
            limit = max_candidates or 5

        gray = roi if len(roi.shape) == 2 else cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        rect_k = cv2.getStructuringElement(cv2.MORPH_RECT, (17, 5))
        blackhat = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, rect_k)

        grad = cv2.Sobel(blackhat, cv2.CV_32F, 1, 0, ksize=3)
        grad = np.absolute(grad)
        gmin, gmax = float(grad.min()), float(grad.max())
        if gmax - gmin < 1e-6:
            return []
        grad = (255 * (grad - gmin) / (gmax - gmin)).astype("uint8")

        grad = cv2.GaussianBlur(grad, (5, 5), 0)
        grad = cv2.morphologyEx(grad, cv2.MORPH_CLOSE, rect_k)
        thr = cv2.threshold(grad, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
        thr = cv2.erode(thr, None, iterations=1)
        thr = cv2.dilate(thr, None, iterations=2)

        contours, _ = cv2.findContours(thr, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        candidates: list[tuple[float, BBox]] = []
        for c in contours:
            x, y, w, h = cv2.boundingRect(c)
            if h <= 0 or w * h < self.min_area:
                continue
            if not (h_lo <= h <= h_hi and w <= w_hi):
                continue
            ar = w / float(h)
            if not (self.ar_range[0] <= ar <= self.ar_range[1]):
                continue
            # 위 연산은 '문자 밀집 영역'을 잡으므로 번호판 판 전체로 넓혀 준다.
            # 그대로 두면 크롭 시 앞뒤 글자가 잘려 OCR 인식률이 떨어진다.
            x, y, w, h = self._expand_to_plate(gray, (x, y, w, h))
            if full_frame and not (h_lo <= h <= h_hi and w <= w_hi):
                continue
            candidates.append((
                self._plate_score(w, h, full_frame),
                BBox(x + ox, y + oy, x + w + ox, y + h + oy),
            ))

        candidates.sort(key=lambda t: t[0], reverse=True)
        return [b for _, b in candidates[:limit]]

    # ------------------------------------------------------------------
    @staticmethod
    def _plate_score(w: int, h: int, full_frame: bool) -> float:
        """번호판다움 점수.

        전체 프레임에서는 면적순으로 뽑으면 건물·차체가 상위를 차지한다.
        한국 번호판 규격(335형 2.1, 520형 4.7)에 가까운 비율을 우선한다.
        """
        if not full_frame:
            return float(w * h)
        ar = w / float(h) if h else 0.0
        shape = max(1.0 / (1.0 + abs(ar - 2.1)), 1.0 / (1.0 + abs(ar - 4.7)))
        return shape * (w * h) ** 0.35

    # ------------------------------------------------------------------
    def _expand_to_plate(
        self, gray: Any, rect: tuple[int, int, int, int], grow: float = 2.2
    ) -> tuple[int, int, int, int]:
        """문자 영역 후보를 번호판 판 전체로 확장한다.

        후보 주변을 넓게 잘라 밝기 이진화한 뒤, 후보를 감싸는 밝은 연결 성분
        (= 번호판 판)의 외접 사각형을 취한다. 실패하면 고정 비율로 확대한다.
        """
        x, y, w, h = rect
        H, W = gray.shape[:2]
        cx, cy = x + w / 2.0, y + h / 2.0
        sw, sh = w * grow, h * grow * 1.6
        sx1, sy1 = max(0, int(cx - sw / 2)), max(0, int(cy - sh / 2))
        sx2, sy2 = min(W, int(cx + sw / 2)), min(H, int(cy + sh / 2))

        fallback = self._fixed_expand(rect, W, H)
        win = gray[sy1:sy2, sx1:sx2]
        if win.size == 0 or win.shape[0] < 4 or win.shape[1] < 8:
            return fallback

        # 조건마다 유리한 이진화가 다르다. 주간·고대비에서는 원본 OTSU가,
        # 야간·저대비에서는 대비 보정본이 판을 잘 분리한다. 순서대로 시도해
        # 검증을 통과하는 첫 결과를 쓴다.
        for prep in (self._win_plain, self._win_clahe, self._win_norm):
            try:
                found = self._plate_rect(prep(win), rect, (sx1, sy1), (cx, cy), grow)
            except Exception:
                log.debug("번호판 영역 확장 실패", exc_info=True)
                found = None
            if found is not None:
                return found
        return fallback

    # -- 창 전처리 전략 -------------------------------------------------
    @staticmethod
    def _win_plain(win: Any) -> Any:
        return win

    @staticmethod
    def _win_clahe(win: Any) -> Any:
        return cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8)).apply(win)

    @staticmethod
    def _win_norm(win: Any) -> Any:
        return cv2.normalize(win, None, 0, 255, cv2.NORM_MINMAX)

    # ------------------------------------------------------------------
    def _plate_rect(
        self, win: Any, rect: tuple[int, int, int, int],
        origin: tuple[int, int], center: tuple[float, float], grow: float,
    ) -> Optional[tuple[int, int, int, int]]:
        """밝은 연결 성분에서 번호판 사각형을 찾고 타당성을 검증한다."""
        x, y, w, h = rect
        sx1, sy1 = origin
        cx, cy = center

        thr = cv2.threshold(win, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
        # 글자로 뚫린 구멍을 메워 판 전체가 하나의 성분이 되게 한다
        k = cv2.getStructuringElement(cv2.MORPH_RECT, (max(3, w // 6), max(3, h // 2)))
        thr = cv2.morphologyEx(thr, cv2.MORPH_CLOSE, k)
        n, labels, stats, _ = cv2.connectedComponentsWithStats(thr, 8)
        if n <= 1:
            return None

        px, py = int(cx - sx1), int(cy - sy1)
        lbl = 0
        if 0 <= py < labels.shape[0] and 0 <= px < labels.shape[1]:
            lbl = int(labels[py, px])
        if lbl == 0:  # 중심이 글자(어두운 화소) 위면 가장 큰 밝은 성분을 쓴다
            lbl = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))

        rx = int(stats[lbl, cv2.CC_STAT_LEFT]) + sx1
        ry = int(stats[lbl, cv2.CC_STAT_TOP]) + sy1
        rw = int(stats[lbl, cv2.CC_STAT_WIDTH])
        rh = int(stats[lbl, cv2.CC_STAT_HEIGHT])

        # 원 후보를 감싸고, 번호판 비율을 유지하며, 과도하게 번지지 않을 때만 채택
        if not (rx <= x and ry <= y and rx + rw >= x + w and ry + rh >= y + h):
            return None
        if rh <= 0 or not (self.ar_range[0] <= rw / float(rh) <= self.ar_range[1] + 1.5):
            return None
        if rw > w * grow * 1.3 or rh > h * grow * 2.0:
            return None
        return rx, ry, rw, rh

    @staticmethod
    def _fixed_expand(
        rect: tuple[int, int, int, int], W: int, H: int,
        fx: float = 1.35, fy: float = 1.55,
    ) -> tuple[int, int, int, int]:
        """밝기 기반 확장이 실패했을 때의 고정 비율 확대."""
        x, y, w, h = rect
        cx, cy = x + w / 2.0, y + h / 2.0
        nw, nh = w * fx, h * fy
        nx1, ny1 = max(0, int(cx - nw / 2)), max(0, int(cy - nh / 2))
        nx2, ny2 = min(W, int(cx + nw / 2)), min(H, int(cy + nh / 2))
        return nx1, ny1, nx2 - nx1, ny2 - ny1

    # ------------------------------------------------------------------
    @staticmethod
    def _roi(frame: Any, vehicle_bbox: Optional[BBox]):
        """차량 bbox가 있으면 그 영역만 잘라 (roi, offset_x, offset_y) 반환."""
        if vehicle_bbox is None:
            return frame, 0.0, 0.0
        h, w = frame.shape[:2]
        x1 = max(0, int(vehicle_bbox.x1)); y1 = max(0, int(vehicle_bbox.y1))
        x2 = min(w, int(vehicle_bbox.x2)); y2 = min(h, int(vehicle_bbox.y2))
        if x2 <= x1 or y2 <= y1:
            return None, 0.0, 0.0
        return frame[y1:y2, x1:x2], float(x1), float(y1)


    # ------------------------------------------------------------------
    def detect_by_text(self, frame: Any, reader: Any, max_candidates: int = 5) -> list[BBox]:
        """OCR 엔진의 텍스트 검출을 이용해 번호판 후보를 찾는다.

        YOLO 번호판 가중치가 없을 때 실사진에서 쓰기 좋은 경로다.
        EasyOCR 은 자체 검출망(CRAFT)으로 글자 영역을 먼저 찾으므로, 그 결과 중
        번호판다운 것(가로로 길고 숫자가 여럿)만 남기면 된다.
        """
        if frame is None or reader is None:
            return []
        try:
            results = reader.readtext(frame, detail=1, paragraph=False) or []
        except Exception:
            log.exception("텍스트 검출 실패")
            return []

        raw: list[tuple[BBox, str, float]] = []
        for pts, text, conf in results:
            xs = [float(p[0]) for p in pts]
            ys = [float(p[1]) for p in pts]
            b = BBox(min(xs), min(ys), max(xs), max(ys))
            if b.height <= 1 or b.width <= 1:
                continue
            raw.append((b, str(text), float(conf)))

        merged = _merge_text_boxes(raw)

        scored: list[tuple[float, BBox]] = []
        for b, text, conf in merged:
            ar = b.width / b.height
            if not (1.2 <= ar <= 9.0):
                continue
            digits = sum(ch.isdigit() for ch in text)
            if digits < 2:
                continue
            has_hangul = any("가" <= ch <= "힣" for ch in text)
            score = conf * (1.0 + 0.2 * digits) * (1.5 if has_hangul else 1.0)
            scored.append((score, b))

        scored.sort(key=lambda t: t[0], reverse=True)
        return [b for _, b in scored[:max_candidates]]


def _merge_text_boxes(
    items: list[tuple[BBox, str, float]], gap_ratio: float = 1.2
) -> list[tuple[BBox, str, float]]:
    """같은 줄에서 끊어진 텍스트 조각을 하나로 잇는다.

    번호판이 '12가' + '3456' 처럼 두 조각으로 검출되는 경우가 흔하다.
    """
    if not items:
        return []
    items = sorted(items, key=lambda t: t[0].x1)
    out: list[tuple[BBox, str, float]] = [items[0]]

    for b, text, conf in items[1:]:
        pb, ptext, pconf = out[-1]
        v_overlap = min(pb.y2, b.y2) - max(pb.y1, b.y1)
        min_h = min(pb.height, b.height)
        gap = b.x1 - pb.x2
        same_line = min_h > 0 and v_overlap / min_h > 0.5
        close = gap < min_h * gap_ratio

        if same_line and close:
            out[-1] = (
                BBox(min(pb.x1, b.x1), min(pb.y1, b.y1), max(pb.x2, b.x2), max(pb.y2, b.y2)),
                ptext + text,
                (pconf + conf) / 2,
            )
        else:
            out.append((b, text, conf))
    return out


def filter_by_shape(
    boxes: Sequence[BBox], ar_range: tuple[float, float] = (1.8, 6.0), min_area: int = 400
) -> list[BBox]:
    out = []
    for b in boxes:
        if b.height <= 0 or b.area < min_area:
            continue
        ar = b.width / b.height
        if ar_range[0] <= ar <= ar_range[1]:
            out.append(b)
    return out
