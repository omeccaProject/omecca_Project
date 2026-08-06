"""ReportLab으로 증거 리포트 PDF 생성 — '상세 증거형' 레이아웃.

사건 개요 / 증거 이미지(bbox 탐지영역 오버레이) / 처리 정보(서명란) 3개 섹션으로 구성된
정식 문서 형태. 팀 회의에서 3가지 시안(공문서형/색상카드형/상세증거형) 중 상세증거형으로
확정됨 (2026-08-06).
"""

from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw
from reportlab.lib.colors import HexColor, black
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas

# 한글 CID 폰트 등록 (별도 폰트 파일 없이 reportlab 기본 제공 - Adobe-Korea1 표준 폰트).
# PDF 뷰어(미리보기/Chrome 등)가 시스템에 설치된 한글 폰트로 대체 렌더링해줌.
pdfmetrics.registerFont(UnicodeCIDFont("HYGothic-Medium"))   # 제목/라벨용 (고딕)
pdfmetrics.registerFont(UnicodeCIDFont("HYSMyeongJo-Medium"))  # 본문용 (명조)
FONT_TITLE = "HYGothic-Medium"
FONT_BODY = "HYSMyeongJo-Medium"

MUTED = HexColor("#6B7280")
FAINT = HexColor("#9CA3AF")
BBOX_COLOR = (230, 40, 40)


def generate_evidence_pdf(
    out_path: str | Path,
    *,
    title: str,
    event_type: str,
    occurred_at: str,
    location: str,
    plate: str | None,
    before_image: str | Path | None,
    after_image: str | Path | None,
    event_id: int | None = None,
    cam_id: str | None = None,
    track_id: str | None = None,
    confidence: float | None = None,
    bbox: list[int] | tuple[int, int, int, int] | None = None,
) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    c = canvas.Canvas(str(out_path), pagesize=A4)
    width, height = A4
    margin = 18 * mm

    # 헤더
    c.setFont(FONT_TITLE, 9)
    c.setFillColor(MUTED)
    c.drawString(margin, height - 14 * mm, "OMECCA-3 EVIDENCE REPORT")
    if event_id is not None:
        c.drawRightString(width - margin, height - 14 * mm, f"REF. EVT-{event_id:06d}")
    c.setFillColor(black)
    c.setFont(FONT_TITLE, 19)
    c.drawString(margin, height - 22 * mm, title)
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
        ("차량 번호판", plate or "-"),
        ("탐지 신뢰도", f"{confidence * 100:.1f}%" if confidence is not None else "-"),
    ]
    for label, value in overview:
        c.setFillColor(MUTED)
        c.drawString(margin, y, label)
        c.setFillColor(black)
        c.drawString(margin + 32 * mm, y, str(value))
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


def _load_image(path: str | Path, bbox) -> ImageReader:
    """bbox가 있으면 탐지 영역을 빨간 사각형으로 표시한 뒤 ImageReader로 반환, 없으면 원본 그대로."""
    if not bbox:
        return ImageReader(str(path))
    img = Image.open(path).convert("RGB")
    x, y, w, h = bbox
    ImageDraw.Draw(img).rectangle([x, y, x + w, y + h], outline=BBOX_COLOR, width=4)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)
    return ImageReader(buf)


def _draw_image_fit(c: canvas.Canvas, img: ImageReader, x: float, y_top: float, max_w: float, max_h: float) -> float:
    iw, ih = img.getSize()
    scale = min(max_w / iw, max_h / ih)
    w, h = iw * scale, ih * scale
    y = y_top - h
    c.drawImage(img, x, y, width=w, height=h, preserveAspectRatio=True, mask="auto")
    return y