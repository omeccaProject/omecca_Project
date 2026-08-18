"""EasyOCR 기반 번호판 문자 인식.

EasyOCR Reader는 초기화 비용이 크므로 프로세스당 1회만 생성해 재사용한다.
allowlist로 번호판에 쓰이는 문자만 남기면 오인식이 눈에 띄게 줄어든다.
"""

from __future__ import annotations

import logging
import random
import threading
from pathlib import Path
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


# 번호판 전용으로 파인튜닝한 모델의 이름.
#   ~/.EasyOCR/model/plate.pth
#   ~/.EasyOCR/user_network/plate.py
#   ~/.EasyOCR/user_network/plate.yaml
# 세 파일이 다 있으면 자동으로 이 모델을 쓴다. 하나라도 없으면 기본 한국어
# 모델(korean_g2)로 돌아간다. **되돌리려면 plate.pth 만 지우면 된다.**
CUSTOM_NETWORK = "plate"


def custom_model_ready() -> tuple[bool, str]:
    """번호판 전용 모델이 설치돼 있는가."""
    home = Path.home() / ".EasyOCR"
    need = [home / "model" / f"{CUSTOM_NETWORK}.pth",
            home / "user_network" / f"{CUSTOM_NETWORK}.py",
            home / "user_network" / f"{CUSTOM_NETWORK}.yaml"]
    missing = [p.name for p in need if not p.exists()]
    if missing:
        return False, f"없는 파일: {', '.join(missing)}"
    return True, str(home)


def custom_lang_list() -> list[str]:
    """전용 모델 yaml 이 선언한 언어 목록.

    EasyOCR 은 `Reader(lang_list=...)` 가 yaml 의 `lang_list` 에 **포함되는지**
    검사하고, 하나라도 벗어나면 통째로 거부한다.

        우리 기본값     ['ko', 'en']
        plate.yaml     ['ko']
        → {'en'} 이 남아 "Plate is only compatible with English" 로 실패

    그래서 전용 모델을 쓸 때는 yaml 이 말하는 목록을 그대로 따라야 한다.
    """
    y = Path.home() / ".EasyOCR" / "user_network" / f"{CUSTOM_NETWORK}.yaml"
    try:
        import yaml  # type: ignore
        cfg = yaml.safe_load(y.read_text(encoding="utf-8")) or {}
        langs = cfg.get("lang_list") or []
        return [str(x) for x in langs] or ["ko"]
    except Exception:
        log.debug("plate.yaml 의 lang_list 를 읽지 못했습니다", exc_info=True)
        return ["ko"]


def get_reader(langs: Optional[list[str]] = None, gpu: bool = False):  # pragma: no cover
    """EasyOCR Reader 싱글턴.

    번호판 전용 모델이 설치돼 있으면 그것을, 없으면 기본 한국어 모델을 쓴다.
    전용 모델 로딩에 실패해도 기본 모델로 넘어가 파이프라인이 멈추지 않는다.
    """
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

        lang = langs or settings.lpr.ocr_lang
        ok, info = custom_model_ready()
        if ok:
            # 전용 모델은 yaml 이 선언한 언어만 받는다. 우리 기본값(ko+en)을
            # 그대로 넘기면 'en 은 지원 안 함' 으로 거부당한다.
            plate_lang = custom_lang_list()
            try:
                _reader = easyocr.Reader(plate_lang, gpu=gpu,
                                         recog_network=CUSTOM_NETWORK)
                log.info("번호판 전용 모델 사용 (%s, lang=%s)",
                         CUSTOM_NETWORK, plate_lang)
                print(f"[LPR] 번호판 전용 모델 '{CUSTOM_NETWORK}' 사용 "
                      f"(lang={plate_lang})")
                return _reader
            except Exception as e:
                log.exception("전용 모델 로딩 실패 → 기본 모델로 넘어갑니다")
                print(f"[LPR] 전용 모델 로딩 실패 → 기본 korean_g2 로 진행")
                print(f"      원인: {type(e).__name__}: {e}")
        else:
            log.info("번호판 전용 모델 없음 (%s) → 기본 모델 사용", info)
            print(f"[LPR] 전용 모델 없음 ({info}) → 기본 korean_g2 사용")

        try:
            _reader = easyocr.Reader(lang, gpu=gpu)
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

        # 자리별 2패스는 **범용 모델**이 한글을 숫자로 읽는 걸 막으려고 만든 장치다.
        # 번호판 전용 모델은 글자 67자만 알고 자리 구조까지 배웠으므로 그 실수를
        # 애초에 못 한다. 그 상태에서 2패스를 켜면 이득 없이 분할 실패 위험만 얹는다.
        #
        #   실측 (실제 번호판 사진 50장, 전용 모델)
        #       2패스 켬    단일 40건 92.5% / 2패스 10건 70.0%  → 전체 88.0%
        #       2패스 끔    단일 50건 94.0%                      → 전체 94.0%
        #
        # 그래서 전용 모델이 있으면 기본으로 끈다. 명시로 넘기면 그 값을 따른다.
        if structured is not None:
            self.structured = structured
        elif custom_model_ready()[0]:
            self.structured = False
        else:
            self.structured = cfg.structured_ocr
        self._mock_plates: list[str] = []
        self.stats = {"structured_ok": 0, "structured_fallback": 0, "single_pass": 0}
        # 2패스가 '어느 단계에서' 포기했는지. 실측상 2패스는 걸리기만 하면
        # 정확도가 압도적이라, 포기 지점을 알아야 어디를 손볼지 정해진다.
        # (bench_lpr.py 가 이 값을 읽어 분포를 출력한다)
        self.bail: dict[str, int] = {}

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
        raw2 = self._recover_hangul(reader, image, raw)
        if raw2 != raw:
            self.stats["hangul_recovered"] = self.stats.get("hangul_recovered", 0) + 1
            return self._finalize(raw2, conf, bbox, cam_id, track_id,
                                  engine="easyocr:hangul-fix")
        return self._finalize(raw, conf, bbox, cam_id, track_id, engine="easyocr")

    # ------------------------------------------------------------------
    def _recover_hangul(self, reader, image: Any, raw: str) -> str:
        """숫자만 읽힌 결과에서 한글 자리를 되찾는다.

        왜 필요한가
            분할(segment)이 실패해 2패스를 못 쓰면 단일 패스로 넘어가는데,
            거기서 한글이 숫자로 읽히는 일이 잦다. 사진 50장 실측에서
            오답 19건 중 **7건**이 이 유형이었고, 전부 아래 모양이었다.

                10조1385 → 1031385      29버3443 → 2903443
                33누0315 → 3350315      45구1353 → 4571353

        왜 안전한가
            **한국 번호판에 한글 없는 것은 없다.** 숫자만 7~8자리인 결과는
            이미 100% 오답이므로, 여기서 무엇을 하든 더 나빠질 수 없다.
            형식이 맞는 기존 결과에는 손대지 않는다.

        어떻게
            글자 수가 정해지면 한글 자리도 정해진다(7자→3번째, 8자→4번째).
            번호판은 글자 간격이 고르므로 그 자리를 가로 비율로 잘라내
            **한글 전용 allowlist** 로 다시 읽는다. 못 읽으면 원문을 그대로 둔다.
        """
        s = pf.strip_noise(raw)
        if not s.isdigit() or len(s) not in seg.HANGUL_INDEX:
            return raw                      # 한글이 이미 있거나 길이가 안 맞음
        if image is None or not seg.HAS_CV:
            return raw

        idx = seg.HANGUL_INDEX[len(s)]
        h, w = image.shape[:2]
        if h < 12 or w < 24:
            return raw

        # 해당 자리의 가로 구간. 간격 추정이 조금 어긋나도 잡히도록 넉넉히 준다.
        unit = w / float(len(s))
        pad = unit * 0.35
        x1 = max(0, int(idx * unit - pad))
        x2 = min(w, int((idx + 1) * unit + pad))
        if x2 - x1 < 6:
            return raw

        crop = _upscale_for_ocr(image[:, x1:x2])
        res = self._readtext(reader, crop, HANGUL_ALLOWLIST)
        if not res:
            return raw
        htext, _ = self._join(res)
        hchar = next((ch for ch in htext if ch in pf.PLATE_HANGUL), "")
        if not hchar:
            return raw
        # **삽입이 아니라 교체다.** 그 자리의 숫자는 한글을 잘못 읽은 것이므로
        # 빼내야 한다. 삽입하면 '1031385' 가 '10조31385'(8자)가 되어 버린다.
        return s[:idx] + hchar + s[idx + 1:]

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
        """조각으로 끊겨 나온 결과를 **읽는 순서대로** 이어붙인다.

        번호판이 항상 한 줄인 것은 아니다. 지역명이 붙은 판은 두 줄이다.

            경기 70        ← 윗줄
            바  1332       ← 아랫줄     →  "경기70바1332"

        x 좌표로만 정렬하면 두 줄이 뒤섞인다. 실측에서 이렇게 나왔다.

            정답 경기70바1332  →  '천8바1332경가70'
            정답 경기76자3500  →  '8자3500경가76'

        그래서 y 로 줄을 먼저 나누고, 줄은 위→아래, 줄 안에서는 왼→오로
        정렬한다. 한 줄짜리 판에서는 결과가 예전과 같다.
        """
        if not results:
            return "", 0.0

        items = []
        for r in results:
            ys = [float(p[1]) for p in r[0]]
            xs = [float(p[0]) for p in r[0]]
            items.append({
                "y1": min(ys), "y2": max(ys),
                "h": max(1.0, max(ys) - min(ys)),
                "x": min(xs), "text": r[1], "conf": float(r[2]),
            })

        # 같은 줄인지는 **세로로 겹치는가**로 본다. 중심 거리로 재면 안 된다.
        #   2줄 번호판의 윗줄은 '인천 70' 처럼 지역명이 숫자보다 작고 위로
        #   치우쳐 있다. 중심끼리는 멀지만 세로 구간은 크게 겹친다.
        #   중심 거리로 재면 '인천' 과 '70' 이 다른 줄로 갈려서
        #   '70인천8바1670' 같은 결과가 나온다 (실측).
        items.sort(key=lambda d: d["y1"])
        lines: list[list[dict]] = [[items[0]]]
        for it in items[1:]:
            cur = lines[-1]
            top = min(d["y1"] for d in cur)
            bot = max(d["y2"] for d in cur)
            overlap = min(bot, it["y2"]) - max(top, it["y1"])
            if overlap > min(bot - top, it["h"]) * 0.35:
                cur.append(it)
            else:
                lines.append([it])

        parts = []
        for line in lines:                       # 줄은 이미 위→아래 순
            line.sort(key=lambda d: d["x"])      # 줄 안에서는 왼→오
            parts += line
        text = "".join(d["text"] for d in parts)
        conf = sum(d["conf"] for d in parts) / len(parts)
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
        def bail(reason: str) -> None:
            self.bail[reason] = self.bail.get(reason, 0) + 1

        if not seg.HAS_CV or image is None:
            bail("cv없음/이미지없음")
            return None

        boxes = seg.segment(image)
        layout = seg.split_layout(boxes)
        if layout is None:
            # 글자를 7개나 8개로 못 나눴거나, 한글 자리 폭 검증에 걸렸다.
            bail(f"분할실패(글자 {len(boxes)}개)")
            return None
        head, hangul_box, tail = layout
        expected_digits = len(head) + len(tail)

        # --- 1패스: 숫자 ---------------------------------------------
        masked = seg.mask_region(image, hangul_box)
        digit_res = self._readtext(reader, masked, DIGIT_ALLOWLIST)
        if not digit_res:
            bail("숫자 인식 0건")
            return None
        digits, digit_conf = self._join(digit_res)
        digits = "".join(ch for ch in digits if ch.isdigit())
        if len(digits) != expected_digits:
            log.debug("자리별 인식 숫자 개수 불일치: %d != %d", len(digits), expected_digits)
            bail(f"숫자 개수 불일치({len(digits)}≠{expected_digits})")
            return None

        # --- 2패스: 한글 ---------------------------------------------
        crop = seg.crop(image, hangul_box, pad_x=6, pad_y=6)
        if crop is None:
            bail("한글 크롭 실패")
            return None
        crop = _upscale_for_ocr(crop)
        hangul_res = self._readtext(reader, crop, HANGUL_ALLOWLIST)
        if not hangul_res:
            bail("한글 인식 0건")
            return None
        htext, hconf = self._join(hangul_res)
        hchar = next((ch for ch in htext if ch in pf.PLATE_HANGUL), "")
        if not hchar:
            log.debug("한글 자리 인식 실패: %r", htext)
            bail("한글 글자 못 고름")
            return None

        plate = digits[:len(head)] + hchar + digits[len(head):]

        # 신뢰도는 글자 수 비중으로 가중 평균한다
        total = expected_digits + 1
        conf = (digit_conf * expected_digits + hconf) / total

        result = self._finalize(plate, conf, bbox, cam_id, track_id, engine="easyocr:2pass")
        if result is None:
            bail("finalize 실패")
            return None
        if not result.valid_format:
            # 자리별로 뽑았는데도 형식이 안 맞으면 분할이 틀린 것이다
            bail("합성 결과 형식 위반")
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
