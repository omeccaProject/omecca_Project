# b_report — 증거 리포트 생성기

오메카3 탐지 이벤트 발생 시점의 전/후 프레임을 캡쳐하고,
번호판·발생시각·위치·위반유형을 담은 PDF를 자동 생성한 뒤
`b_gateway`의 `report` 테이블에 경로를 등록한다.

## 역할

| 단계 | 내용 |
|------|------|
| 1 | 이벤트 `frameRefBefore` / `frameRefAfter` 또는 영상 소스에서 프레임 확보 (OpenCV) |
| 2 | ReportLab으로 PDF 생성 |
| 3 | `POST /api/reports`로 `{ eventId, pdfPath, status }` 를 게이트웨이에 기록 |

## 예상 구조

```
b_report/
  README.md
  requirements.txt
  src/
    capture.py          # 전/후 프레임 캡쳐
    generate_pdf.py     # PDF 생성
    register_report.py  # b_gateway API 연동
    main.py             # CLI 진입점
  output/               # 생성된 PDF·캡쳐 이미지 (로컬)
```

## 설치

```bash
cd b_report
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 사용 예시

```bash
# 샘플 이미지로 PDF 생성 후 게이트웨이에 등록
python -m src.main \
  --event-id 1 \
  --title "신호위반 증거 리포트" \
  --event-type SIGNAL_VIOLATION \
  --occurred-at "2026-08-06T10:00:00" \
  --location "교차로 북측" \
  --plate "12가3456" \
  --before ./samples/before.jpg \
  --after ./samples/after.jpg \
  --gateway-url http://localhost:8080
```

게이트웨이(`b_gateway`)가 떠 있어야 `POST /api/reports` 등록이 성공한다.
PDF만 만들려면 `--skip-register` 옵션을 사용한다.
