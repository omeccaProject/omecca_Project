"""EasyOCR 기반 번호판 문자 인식.

EasyOCR Reader는 초기화 비용이 크므로 프로세스당 1회만 생성해 재사용한다.
allowlist로 번호판에 쓰이는 문자만 남기면 오인식이 눈에 띄게 줄어든다.
"""

from __future__ import annotations

import logging
import random
import threading
from typing import Any, Optional

from ..core.config import settings
from ..core.schemas import BBox, PlateResult
from . import plate_format as pf
from . import segment as seg

log = logging.getLogger("omeca.lpr.recognizer")

# 번호판에 등장 가능한 문자만 허용 → 엉뚱한 글자 후보를 원천 차단
ALLOWLIST = "0123456789" + "".join(sorted(pf.PLATE_HANGUL)) + "".join(pf.REGIONS)

# 자리별 인식용 allowlist.
# 숫자와 한글을 한 목록에 같이 두면 OCR 이 한글 자리에서 숫자를 골라
# '나'→'4', '아'→'0', '가'→'7' 같은 오인식이 대량 발생한다(실측 오류의 93%).
# 자리마다 후보를 나눠 주면 그 선택지 자체가 사라진다.
DIGIT_ALLOWLIST = "0123456789"
HANGUL_ALLOWLIST = "".join(sorted(pf.PLATE_HANGUL))

_reader = None
_reader_lock = threading.Lock()


def get_reader(langs: Optional[list[str]] = None, gpu: bool = False):  # pragma: no cover
    """EasyOCR Reader 싱글턴."""
    global _reader
    if _reader is not None:
        return _reader
    with _reader_lock:
        if _reader is not None:
            return _reader
        try:
            import easyocr  # type: ignore
        except ImportError:
            log.warning("easyocr 미설치 → Mock 인식기로 동작")
            return None
        try:
            _reader = easyocr.Reader(langs or settings.lpr.ocr_lang, gpu=gpu)
        except Exception:
            log.exception("EasyOCR 초기화 실패")
            return None
    return _reader


class PlateRecognizer:
    def __init__(
        self,
        mock: Optional[bool] = None,
        gpu: Optional[bool] = None,
        structured: Optional[bool] = None,
    ) -> None:
        cfg = settings.lpr
        self.mock = cfg.mock if mock is None else mock
        self.gpu = cfg.gpu if gpu is None else gpu
        self.min_conf = cfg.min_plate_conf
        self.structured = cfg.structured_ocr if structured is None else structured
        self._mock_plates: list[str] = []
        self.stats = {"structured_ok": 0, "structured_fallback": 0, "single_pass": 0}

    # ------------------------------------------------------------------
    def set_mock_plates(self, plates: list[str]) -> None:
        """Mock 모드에서 돌려줄 번호판 풀 (DB 시드와 맞춰 시연에 사용)."""
        self._mock_plates = list(plates)

    # ------------------------------------------------------------------
    def read(
        self,
        image: Any,
        bbox: Optional[BBox] = None,
        cam_id: str = "",
        track_id: int = -1,
        hint: Optional[str] = None,
    ) -> Optional[PlateResult]:
        """전처리된 이미지에서 번호판 문자열을 읽는다."""
        if self.mock or image is None:
            return self._read_mock(bbox, cam_id, track_id, hint)

        reader = get_reader(settings.lpr.ocr_lang, self.gpu)
        if reader is None:
            return self._read_mock(bbox, cam_id, track_id, hint)

        # 자리별 인식 우선 시도. 배치를 못 읽으면 단일 패스로 되돌아간다.
        if self.structured:
            r = self._read_structured(reader, image, bbox, cam_id, track_id)
            if r is not None:
                self.stats["structured_ok"] += 1
                return r
            self.stats["structured_fallback"] += 1

        self.stats["single_pass"] += 1
        results = self._readtext(reader, image, ALLOWLIST)
        if not results:
            return None

        raw, conf = self._join(results)
        return self._finalize(raw, conf, bbox, cam_id, track_id, engine="easyocr")

    # ------------------------------------------------------------------
    @staticmethod
    def _readtext(reader, image, allowlist: str) -> list:
        try:  # pragma: no cover - OCR 엔진 의존
            return reader.readtext(
                image, allowlist=allowlist, detail=1, paragraph=False
            ) or []
        except Exception:
            log.exception("OCR 실패")
            return []

    @staticmethod
    def _join(results) -> tuple[str, float]:
        """조각으로 끊겨 나온 결과를 x좌표 순으로 이어붙인다 (번호판은 한 줄)."""
        ordered = sorted(results, key=lambda r: r[0][0][0])
        text = "".join(r[1] for r in ordered)
        conf = sum(float(r[2]) for r in ordered) / len(ordered)
        return text, conf

    # ------------------------------------------------------------------
    def _read_structured(
        self, reader, image: Any, bbox, cam_id: str, track_id: int
    ) -> Optional[PlateResult]:
        """자리별 allowlist 를 쓰는 2패스 인식.

          1) 한글 자리를 배경색으로 덮고 → 숫자 전용 allowlist 로 전체 인식
          2) 한글 자리만 잘라 확대 → 한글 전용 allowlist 로 인식
          3) 두 결과를 자리에 맞춰 합성

        한글이 숫자로 읽히거나 그 반대인 경우가 구조적으로 불가능해진다.
        분할이 형식에 안 맞으면 None 을 돌려 단일 패스로 넘긴다.
        """
        if not seg.HAS_CV or image is None:
            return None

        boxes = seg.segment(image)
        layout = seg.split_layout(boxes)
        if layout is None:
            return None
        head, hangul_box, tail = layout
        expected_digits = len(head) + len(tail)

        # --- 1패스: 숫자 ---------------------------------------------
        masked = seg.mask_region(image, hangul_box)
        digit_res = self._readtext(reader, masked, DIGIT_ALLOWLIST)
        if not digit_res:
            return None
        digits, digit_conf = self._join(digit_res)
        digits = "".join(ch for ch in digits if ch.isdigit())
        if len(digits) != expected_digits:
            log.debug("자리별 인식 숫자 개수 불일치: %d != %d", len(digits), expected_digits)
            return None

        # --- 2패스: 한글 ---------------------------------------------
        crop = seg.crop(image, hangul_box, pad_x=6, pad_y=6)
        if crop is None:
            return None
        crop = _upscale_for_ocr(crop)
        hangul_res = self._readtext(reader, crop, HANGUL_ALLOWLIST)
        if not hangul_res:
            return None
        htext, hconf = self._join(hangul_res)
        hchar = next((ch for ch in htext if ch in pf.PLATE_HANGUL), "")
        if not hchar:
            log.debug("한글 자리 인식 실패: %r", htext)
            return None

        plate = digits[:len(head)] + hchar + digits[len(head):]

        # 신뢰도는 글자 수 비중으로 가중 평균한다
        total = expected_digits + 1
        conf = (digit_conf * expected_digits + hconf) / total

        result = self._finalize(plate, conf, bbox, cam_id, track_id, engine="easyocr:2pass")
        if result is not None and not result.valid_format:
            # 자리별로 뽑았는데도 형식이 안 맞으면 분할이 틀린 것이다
            return None
        return result

    # ------------------------------------------------------------------
    def _finalize(
        self,
        raw: str,
        conf: float,
        bbox: Optional[BBox],
        cam_id: str,
        track_id: int,
        engine: str,
    ) -> Optional[PlateResult]:
        norm = pf.correct(raw)
        if not norm.text:
            return None
        # 보정이 개입했으면 신뢰도를 살짝 깎아 하류 판정에서 보수적으로 다루게 한다
        if norm.changed:
            conf *= 0.92
        if not norm.valid:
            conf *= 0.75
        return PlateResult(
            plate_no=norm.text,
            confidence=round(min(conf, 1.0), 4),
            bbox=bbox,
            raw_text=raw,
            valid_format=norm.valid,
            plate_type=norm.plate_type,
            cam_id=cam_id,
            track_id=track_id,
            engine=engine,
        )

    # ------------------------------------------------------------------
    def _read_mock(
        self,
        bbox: Optional[BBox],
        cam_id: str,
        track_id: int,
        hint: Optional[str],
    ) -> Optional[PlateResult]:
        """가중치/영상 없이 파이프라인을 시연하기 위한 더미 인식.

        hint가 주어지면 그 번호판을 그대로 쓰되, 실제 OCR처럼 낮은 확률로
        한 글자를 흔들어 fuzzy 매칭 로직까지 검증되도록 한다.
        """
        plate = hint or (random.choice(self._mock_plates) if self._mock_plates else None)
        if plate is None:
            plate = f"{random.randint(10, 99)}{random.choice(pf.PRIVATE_HANGUL)}{random.randint(1000, 9999)}"

        conf = round(random.uniform(0.72, 0.98), 4)
        raw = plate
        if random.random() < 0.15:  # 15% 확률로 오인식 재현
            raw = _perturb(plate)
            conf = round(random.uniform(0.45, 0.7), 4)
        return self._finalize(raw, conf, bbox, cam_id, track_id, engine="mock")


def _upscale_for_ocr(img: Any, target_h: int = 96) -> Any:
    """한 글자 크롭은 너무 작아 그대로 넣으면 인식되지 않는다."""
    if not seg.HAS_CV or img is None:
        return img
    h, w = img.shape[:2]
    if h <= 0 or h >= target_h:
        return img
    scale = target_h / h
    return seg.cv2.resize(
        img, (max(1, int(w * scale)), target_h), interpolation=seg.cv2.INTER_CUBIC
    )


_REVERSE_FIX = {"0": "O", "1": "I", "5": "S", "8": "B", "6": "G", "2": "Z", "7": "T"}


def _perturb(plate: str) -> str:
    """Mock용: 숫자 한 자리를 헷갈리기 쉬운 영문으로 바꾼다."""
    idxs = [i for i, ch in enumerate(plate) if ch in _REVERSE_FIX]
    if not idxs:
        return plate
    i = random.choice(idxs)
    return plate[:i] + _REVERSE_FIX[plate[i]] + plate[i + 1:]
