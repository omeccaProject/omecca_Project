"""EasyOCR 연동 계약(contract) 테스트.

EasyOCR 자체는 torch 의존성이 커 CI 환경에 두지 않는다. 대신 실제
`easyocr.Reader.readtext()` 의 반환 형식을 그대로 흉내낸 대역을 주입해
recognizer 의 호출·파싱·보정 경로를 검증한다.

EasyOCR 반환 규격 (detail=1):
    [ ([[x1,y1],[x2,y1],[x2,y2],[x1,y2]], "텍스트", 신뢰도), ... ]
"""

from __future__ import annotations

import pytest

from app.core.schemas import BBox
from app.lpr import recognizer as rec_mod
from app.lpr.recognizer import (
    ALLOWLIST, DIGIT_ALLOWLIST, HANGUL_ALLOWLIST, PlateRecognizer,
)


class FakeReader:
    """easyocr.Reader 대역.

    운영 코드는 `recognize()`(검출 없이 이미지 전체를 한 줄로 읽기)를 주로
    쓰고, 그게 안 되면 `readtext()`(내부 글자 검출 포함)로 물러난다.
    대역도 둘 다 갖춰야 실제 호출 경로를 흉내 낼 수 있다.
    """

    def __init__(self, results, raise_exc: bool = False):
        self.results = results
        self.raise_exc = raise_exc
        self.calls: list[dict] = []

    def readtext(self, image, **kwargs):
        self.calls.append(kwargs)
        if self.raise_exc:
            raise RuntimeError("OCR 엔진 오류")
        return list(self.results)

    def recognize(self, image, **kwargs):
        self.calls.append(kwargs)
        if self.raise_exc:
            raise RuntimeError("OCR 엔진 오류")
        return list(self.results)


def box(x: int) -> list[list[int]]:
    return [[x, 0], [x + 30, 0], [x + 30, 20], [x, 20]]


@pytest.fixture
def patch_reader(monkeypatch):
    def _apply(reader):
        monkeypatch.setattr(rec_mod, "get_reader", lambda *a, **k: reader)
        return reader
    return _apply


IMG = object()   # 전처리 결과 이미지 자리표시자 (대역은 내용을 보지 않는다)


class TestReadtextParsing:
    def test_single_fragment(self, patch_reader):
        patch_reader(FakeReader([(box(0), "12가3456", 0.93)]))
        r = PlateRecognizer(mock=False).read(IMG, bbox=BBox(0, 0, 100, 30))
        assert r is not None
        assert r.plate_no == "12가3456"
        assert r.valid_format
        assert r.confidence == pytest.approx(0.93, abs=0.01)
        # 2패스가 아닌 경로로 읽었음을 나타내면 된다. 구체적인 이름
        # (whole-greedy / whole-beamsearch / detect)은 어느 방식이 채택됐는지에
        # 따라 달라지므로 고정하지 않는다.
        assert r.engine.startswith("easyocr") and "2pass" not in r.engine

    def test_fragments_joined_in_x_order(self, patch_reader):
        """조각이 뒤섞여 와도 x 좌표 순으로 이어붙여야 한다."""
        patch_reader(FakeReader([
            (box(60), "3456", 0.90),
            (box(0), "12", 0.95),
            (box(30), "가", 0.85),
        ]))
        r = PlateRecognizer(mock=False).read(IMG)
        assert r.plate_no == "12가3456"

    def test_confidence_is_averaged(self, patch_reader):
        patch_reader(FakeReader([
            (box(0), "12", 0.90),
            (box(30), "가", 0.70),
            (box(60), "3456", 0.80),
        ]))
        r = PlateRecognizer(mock=False).read(IMG)
        assert r.confidence == pytest.approx(0.80, abs=0.01)

    def test_allowlist_is_passed(self, patch_reader):
        reader = patch_reader(FakeReader([(box(0), "12가3456", 0.9)]))
        PlateRecognizer(mock=False).read(IMG)
        assert reader.calls[0]["allowlist"] == ALLOWLIST
        assert reader.calls[0]["detail"] == 1
        # 문단 병합은 켜지 않는다. 번호판은 한 줄이라 켜면 엉뚱하게 묶인다.
        assert reader.calls[0].get("paragraph", False) is False

    def test_allowlist_contains_plate_charset(self):
        for ch in "0123456789가나허바자서울경기":
            assert ch in ALLOWLIST
        # 번호판에 쓰이지 않는 문자는 제외돼야 오인식이 줄어든다
        # ('수'는 실제 번호판 한글이므로 반례로 쓰면 안 된다)
        for ch in "ABCxyz김철":
            assert ch not in ALLOWLIST


class TestCorrectionInRealPath:
    def test_ocr_confusion_corrected(self, patch_reader):
        patch_reader(FakeReader([(box(0), "12가34S6", 0.88)]))
        r = PlateRecognizer(mock=False).read(IMG)
        assert r.plate_no == "12가3456"
        assert r.raw_text == "12가34S6"
        assert r.valid_format

    def test_confidence_penalised_when_corrected(self, patch_reader):
        patch_reader(FakeReader([(box(0), "12가34S6", 0.88)]))
        corrected = PlateRecognizer(mock=False).read(IMG).confidence
        patch_reader(FakeReader([(box(0), "12가3456", 0.88)]))
        clean = PlateRecognizer(mock=False).read(IMG).confidence
        assert corrected < clean          # 보정이 개입하면 신뢰도를 깎는다

    def test_invalid_format_penalised(self, patch_reader):
        patch_reader(FakeReader([(box(0), "12345", 0.9)]))
        r = PlateRecognizer(mock=False).read(IMG)
        assert not r.valid_format
        assert r.confidence < 0.9

    def test_noise_characters_stripped(self, patch_reader):
        patch_reader(FakeReader([(box(0), " 12 가 3456 ", 0.9)]))
        assert PlateRecognizer(mock=False).read(IMG).plate_no == "12가3456"


class TestFailureHandling:
    def test_empty_result_returns_none(self, patch_reader):
        patch_reader(FakeReader([]))
        assert PlateRecognizer(mock=False).read(IMG) is None

    def test_engine_exception_returns_none(self, patch_reader):
        patch_reader(FakeReader([], raise_exc=True))
        assert PlateRecognizer(mock=False).read(IMG) is None

    def test_unreadable_text_returns_none(self, patch_reader):
        patch_reader(FakeReader([(box(0), "!!!", 0.5)]))
        assert PlateRecognizer(mock=False).read(IMG) is None

    def test_falls_back_to_mock_when_reader_missing(self, monkeypatch):
        """EasyOCR 미설치 환경에서도 파이프라인이 멈추지 않아야 한다."""
        monkeypatch.setattr(rec_mod, "get_reader", lambda *a, **k: None)
        r = PlateRecognizer(mock=False)
        r.set_mock_plates(["12가3456"])
        out = r.read(IMG)
        assert out is not None and out.engine == "mock"

    def test_none_image_uses_mock(self):
        r = PlateRecognizer(mock=False)
        r.set_mock_plates(["34나5678"])
        assert r.read(None).engine == "mock"


class TestStructuredTwoPass:
    """자리별 allowlist 2패스 인식.

    실측에서 오인식의 93%가 '한글이 숫자로 읽히는' 문제였다(나→4, 아→0, 가→7).
    숫자 자리와 한글 자리를 분리해 인식하면 그 선택지 자체가 사라진다.
    """

    cv2 = pytest.importorskip("cv2", reason="OpenCV 미설치 - 분할 기반 경로 생략")

    @pytest.fixture
    def plate_image(self):
        from .test_segment import CONDITIONS, prepared

        return prepared("12가3456", CONDITIONS[0])

    @staticmethod
    def _reader_by_allowlist(digits: str, hangul: str, conf: float = 0.9):
        """allowlist 에 따라 다르게 응답하는 대역 (실제 2패스 동작을 흉내)."""

        class ByAllowlist:
            def __init__(self):
                self.calls: list[str] = []

            def _answer(self, allowlist):
                self.calls.append(allowlist or "")
                if allowlist == DIGIT_ALLOWLIST:
                    return [(box(i * 10), ch, conf) for i, ch in enumerate(digits)]
                if allowlist == HANGUL_ALLOWLIST:
                    return [(box(0), hangul, conf)]
                return [(box(0), digits[:2] + hangul + digits[2:], conf)]

            # 운영 코드는 recognize() 를 먼저 쓴다 (검출 없이 전체 읽기).
            def recognize(self, image, allowlist=None, **kw):
                return self._answer(allowlist)

            def readtext(self, image, allowlist=None, **kw):
                return self._answer(allowlist)

        return ByAllowlist()

    def test_composes_digits_and_hangul(self, patch_reader, plate_image):
        reader = patch_reader(self._reader_by_allowlist("123456", "가"))
        r = PlateRecognizer(mock=False, structured=True).read(plate_image)
        assert r is not None
        assert r.plate_no == "12가3456"
        assert r.engine == "easyocr:2pass"

    def test_uses_separate_allowlists(self, patch_reader, plate_image):
        reader = patch_reader(self._reader_by_allowlist("123456", "가"))
        PlateRecognizer(mock=False, structured=True).read(plate_image)
        assert DIGIT_ALLOWLIST in reader.calls
        assert HANGUL_ALLOWLIST in reader.calls

    def test_digit_allowlist_has_no_hangul(self):
        assert not any("가" <= c <= "힣" for c in DIGIT_ALLOWLIST)

    def test_hangul_allowlist_has_no_digits(self):
        assert not any(c.isdigit() for c in HANGUL_ALLOWLIST)
        assert "가" in HANGUL_ALLOWLIST and "허" in HANGUL_ALLOWLIST

    def test_falls_back_when_digit_count_wrong(self, patch_reader, plate_image):
        """숫자 개수가 배치와 안 맞으면 단일 패스로 되돌아가야 한다."""
        reader = patch_reader(self._reader_by_allowlist("12345", "가"))
        rec = PlateRecognizer(mock=False, structured=True)
        rec.read(plate_image)
        assert rec.stats["structured_fallback"] == 1
        assert rec.stats["single_pass"] == 1

    def test_falls_back_when_hangul_unreadable(self, patch_reader, plate_image):
        reader = patch_reader(self._reader_by_allowlist("123456", "X"))
        rec = PlateRecognizer(mock=False, structured=True)
        rec.read(plate_image)
        assert rec.stats["structured_fallback"] == 1

    def test_disabled_uses_single_pass(self, patch_reader, plate_image):
        reader = patch_reader(self._reader_by_allowlist("123456", "가"))
        rec = PlateRecognizer(mock=False, structured=False)
        r = rec.read(plate_image)
        assert rec.stats["single_pass"] == 1
        assert rec.stats["structured_ok"] == 0
        assert "2pass" not in r.engine

    def test_structured_skipped_without_image(self, patch_reader):
        reader = patch_reader(self._reader_by_allowlist("123456", "가"))
        rec = PlateRecognizer(mock=False, structured=True)
        rec.read(object())          # 배열이 아니면 분할할 수 없다
        assert rec.stats["structured_fallback"] == 1

    def test_hangul_to_digit_confusion_is_impossible(self, patch_reader, plate_image):
        """숫자 패스가 한글을 내놓을 수 없으므로 '나→4' 유형이 사라진다."""
        reader = patch_reader(self._reader_by_allowlist("345678", "나"))
        r = PlateRecognizer(mock=False, structured=True).read(plate_image)
        assert r.plate_no == "34나5678"
        assert r.valid_format


class TestReaderSingleton:
    def test_get_reader_returns_none_without_easyocr(self, monkeypatch):
        """easyocr 미설치 시 예외가 아니라 None 을 돌려줘야 한다."""
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "easyocr":
                raise ImportError("no easyocr")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(rec_mod, "_reader", None)
        monkeypatch.setattr(builtins, "__import__", fake_import)
        assert rec_mod.get_reader(["ko"], False) is None
