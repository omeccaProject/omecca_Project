"""C파트(수배자 얼굴인식·흉기판정) 전용 증거 리포트 PDF 생성.

기존 generate_pdf.py(불법유턴/낙하물용)는 건드리지 않고, 별도 파일로 분리.
공통 폰트/이미지 그리기 유틸리티는 generate_pdf.py에서 그대로 재사용.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from reportlab.lib.colors import HexColor, black
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

# 기존 파일의 폰트/유틸 함수 그대로 재사용 (수정 없이 import만)
from .generate_pdf import FONT_TITLE, FONT_BODY, MUTED, FAINT, _load_image, _draw_image_fit

ARMED_RED = HexColor("#DC2626")


def generate_person_risk_evidence_pdf(
    out_path: str | Path,
    *,
    title: str,
    event_type: str,  # "WANTED_PERSON" 또는 "WEAPON"
    occurred_at: str,
    location: str,
    before_image: str | Path | None,
    after_image: str | Path | None,
    event_id: int | None = None,
    cam_id: str | None = None,
    track_id: str | None = None,
    confidence: float | None = None,
    bbox: list[int] | tuple[int, int, int, int] | None = None,
    matched_db_id: str | None = None,
    face_match_score: float | None = None,
    is_armed: bool = False,
    weapon_type: str | None = None,
) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    c = canvas.Canvas(str(out_path), pagesize=A4)
    width, height = A4
    margin = 18 * mm

    # 헤더
    c.setFont(FONT_TITLE, 9)
    c.setFillColor(MUTED)
    c.drawString(margin, height - 14 * mm, "OMECCA-3 PERSON RISK EVIDENCE REPORT")
    if event_id is not None:
        c.drawRightString(width - margin, height - 14 * mm, f"REF. EVT-{event_id:06d}")
    c.setFillColor(black)
    c.setFont(FONT_TITLE, 19)
    c.drawString(margin, height - 22 * mm, title)

    # 무장 여부 강조 배지 (제일 눈에 띄게, 헤더 우측)
    if is_armed:
        c.setFillColor(ARMED_RED)
        c.setFont(FONT_TITLE, 12)
        c.drawRightString(width - margin, height - 22 * mm, "⚠ 흉기 소지 확인")
        c.setFillColor(black)

    c.setLineWidth(0.8)
    c.line(margin, height - 26 * mm, width - margin, height - 26 * mm)

    y = height - 33 * mm

    # 1. 사건 개요
    c.setFont(FONT_TITLE, 11)
    c.drawString(margin, y, "1. 사건 개요")
    y -= 7 * mm
    c.setFont(FONT_BODY, 10)

    cam_loc = f"{cam_id} / {location}" if cam_id else location
    overview = [
        ("이벤트 유형", event_type),
        ("발생 시각", occurred_at),
        ("카메라 / 위치", cam_loc),
        ("추적 ID", track_id or "-"),
        ("탐지 신뢰도", f"{confidence * 100:.1f}%" if confidence is not None else "-"),
        ("매칭 대상(수배자 ID)", matched_db_id or "-"),
        ("얼굴 매칭 점수", f"{face_match_score:.2f}" if face_match_score is not None else "-"),
        ("무장 여부", "예 (흉기 소지)" if is_armed else "아니오"),
        ("흉기 종류", weapon_type or "-"),
    ]
    for label, value in overview:
        c.setFillColor(MUTED)
        c.drawString(margin, y, label)
        c.setFillColor(black)
        c.drawString(margin + 38 * mm, y, str(value))
        y -= 6 * mm

    y -= 6 * mm
    c.setFont(FONT_TITLE, 11)
    c.drawString(margin, y, "2. 증거 이미지" + (" (탐지 영역 표시)" if bbox else ""))
    y -= 6 * mm

    img_w = (width - 2 * margin - 8 * mm) / 2
    img_h = 65 * mm
    for i, (label, path) in enumerate([("사건 발생 전", before_image), ("사건 발생 후", after_image)]):
        if not path or not Path(path).exists():
            continue
        bx = margin + i * (img_w + 8 * mm)
        c.setFont(FONT_BODY, 9)
        c.drawString(bx, y, label)
        reader = _load_image(path, bbox)
        _draw_image_fit(c, reader, bx, y - 4 * mm, img_w, img_h)
    y -= img_h + 12 * mm

    if bbox:
        c.setFont(FONT_BODY, 7.5)
        c.setFillColor(FAINT)
        c.drawString(margin, y, "* 붉은 사각형은 탐지 모듈이 보고한 bounding box(bbox) 좌표를 표시한 영역입니다.")
        c.setFillColor(black)
        y -= 10 * mm

    # 3. 처리 정보 (서명란)
    c.setFont(FONT_TITLE, 11)
    c.drawString(margin, y, "3. 처리 정보")
    y -= 8 * mm
    c.setFont(FONT_BODY, 9)
    box_w = (width - 2 * margin - 8 * mm) / 2
    box_h = 20 * mm
    c.setLineWidth(0.4)
    c.rect(margin, y - box_h, box_w, box_h, stroke=1, fill=0)
    c.drawString(margin + 3 * mm, y - 6 * mm, "확인 관제요원")
    c.rect(margin + box_w + 8 * mm, y - box_h, box_w, box_h, stroke=1, fill=0)
    c.drawString(margin + box_w + 8 * mm + 3 * mm, y - 6 * mm, "처리 상태 / 인계 기관")

    # 푸터
    c.setFont(FONT_BODY, 7.5)
    c.setFillColor(FAINT)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.drawString(
        margin, 14 * mm,
        f"생성일시: {generated_at} / 오메카3 관제시스템 자동 생성 / 본 문서는 수사/행정 목적으로만 사용됩니다.",
    )

    c.showPage()
    c.save()
    return out_path