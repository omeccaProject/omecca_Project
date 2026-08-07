"""번호판 포맷 검증 · OCR 오인식 보정 테스트."""

import pytest

from app.lpr import plate_format as pf


class TestValidation:
    @pytest.mark.parametrize("plate", [
        "12가3456",      # 신형 2자리
        "123가4567",     # 신형 3자리
        "서울12가3456",  # 구형 지역 표기
        "34나5678",
        "67바8901",      # 영업용
        "123허4567",     # 렌터카
    ])
    def test_valid(self, plate):
        assert pf.is_valid(plate)

    @pytest.mark.parametrize("plate", [
        "1가3456",       # 앞자리 부족
        "12가345",       # 뒷자리 부족
        "12A3456",       # 한글 자리에 영문
        "가나다라",
        "",
        "1234567",       # 한글 없음
    ])
    def test_invalid(self, plate):
        assert not pf.is_valid(plate)


class TestCorrection:
    def test_strips_noise(self):
        assert pf.correct(" 12 가 3456 ").text == "12가3456"
        assert pf.correct("12-가-3456").text == "12가3456"

    @pytest.mark.parametrize("raw,expected", [
        ("12가34S6", "12가3456"),   # S → 5
        ("I2가3456", "12가3456"),   # I → 1
        ("12가3O56", "12가3056"),   # O → 0
        ("l2가3456", "12가3456"),   # l → 1
        ("12가B456", "12가8456"),   # B → 8
    ])
    def test_digit_confusion(self, raw, expected):
        r = pf.correct(raw)
        assert r.text == expected
        assert r.valid
        assert r.changed

    def test_hangul_confusion(self):
        r = pf.correct("12기3456")   # 기 → 가
        assert r.text == "12가3456"
        assert r.valid

    def test_no_change_when_already_clean(self):
        r = pf.correct("12가3456")
        assert r.valid and not r.changed

    def test_unrecoverable_marked_invalid(self):
        r = pf.correct("@@@")
        assert not r.valid


class TestCanonical:
    def test_region_stripped(self):
        assert pf.canonical("서울12가3456") == "12가3456"
        assert pf.canonical("경기34나5678") == "34나5678"

    def test_same_vehicle_matches(self):
        assert pf.canonical("서울12가3456") == pf.canonical("12가3456")


class TestPlateClass:
    @pytest.mark.parametrize("plate,cls", [
        ("12가3456", "private"),
        ("67바8901", "commercial"),
        ("123허4567", "rental"),
        ("12배3456", "delivery"),
    ])
    def test_classification(self, plate, cls):
        assert pf.plate_class(plate) == cls


class TestSimilarity:
    def test_one_char_diff(self):
        assert pf.similarity("12가3456", "12가3457") == 1

    def test_identical(self):
        assert pf.similarity("12가3456", "서울12가3456") == 0

    def test_length_mismatch(self):
        assert pf.similarity("12가3456", "123가4567") == 99
