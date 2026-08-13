# 오메카3 (OMECCA³)

AI 기반 지능형 CCTV 통합 관제 시스템 — 수배자·흉기·위험 차량·도로 낙하물을 실시간 자동 탐지하고, 관심 대상을 다중 CCTV로 추적하며, 사건 증거를 자동으로 문서화한다.

지자체 통합관제센터, 경찰청 등 공공기관(B2G)을 대상으로 하며, 기존 지능형 CCTV가 "탐지 후 알림"에 그치는 것과 달리 **탐지 → GIS 추적 → PDF 증거화**까지 이어지는 대응 흐름 전체를 자동화하는 것이 핵심 차별점이다.

## 왜 만드는가

전국 지자체 CCTV는 2021년 47만 대에서 2024년 65만 대로 늘었지만, 같은 기간 관제 인력은 4,277명에서 4,093명으로 오히려 줄었다. 관제요원 1인당 담당 대수는 행안부 권고 기준(50대)의 10배에 달한다. 사람의 집중력만으로는 실시간 이상 상황을 놓치지 않기 어렵고, 사건 발생 후 증거를 수동으로 정리하는 데도 상당한 시간이 든다.

## 핵심 기능

| # | 기능 | 담당 |
|---|------|------|
| ① | 수배자 얼굴 인식 / 흉기 소지 탐지 | 이시헌 |
| ② | 사건 전후 자동 증거 PDF 리포트 생성 | 장성혁 |
| ③ | 관심 대상 다중 CCTV 연계 추적 및 GIS 경로 시각화 | 김준호 |
| ④ | 미등록 차량(대포차·수배차) 실시간 감지 | 박지원 |
| ⑤ | 도로 낙하물·방치물(공유 킥보드 등) 자동 감지 | 김관용 |
| ⑥ | 음주운전 의심 주행 패턴 감지 | 김준호 |
| ⑦ | 불법 유턴·신호 위반 차량 감지 | 박지원 |

## 시스템 구조
CCTV 영상 입력
↓
FastAPI (AI 추론) — YOLOv11 / ByteTrack / EasyOCR / 얼굴 임베딩 매칭
↓
Spring Boot (API 게이트웨이) — 이벤트 수신·검증·저장, WebSocket 실시간 알림 허브
↓
웹 대시보드 (React) — 영상 뷰어, 이벤트 리스트, Leaflet GIS 지도, PDF 증거 리포트

웹 기반 서비스로 제공하며, 별도 설치형 데스크톱 클라이언트는 두지 않는다.

## 팀 구성

| 이름 | 역할 | 담당 모듈 |
|------|------|-----------|
| 김관용 (팀장) | 영상 인식 코어, 낙하물 감지 | `a_core/`, `a_detector/` |
| 박지원 (부팀장) | 번호판 인식(LPR), 차량 위반 감지 | `d_lpr/` |
| 장성혁 | 백엔드 게이트웨이, 대시보드, 증거 리포트 | `b_gateway/`, `b_dashboard/`, `b_report/` |
| 이시헌 | 얼굴 인식, 흉기 판정 | `c_person_risk/` |
| 김준호 | 다중 CCTV 추적, GIS, 주행 패턴 분석 | `e_tracking/` |

## 기술 스택

- **AI/영상처리**: Python, YOLOv11(Ultralytics), ByteTrack, OpenCV, EasyOCR
- **백엔드**: FastAPI(AI 추론 서버), Spring Boot(API 게이트웨이), WebSocket
- **DB/GIS**: MySQL, PostGIS, Leaflet.js
- **프론트엔드**: React
- **문서 생성**: ReportLab (PDF 증거 리포트)
- **데이터셋 관리**: Roboflow, AI Hub

## 프로젝트 구조
omecca_Project/
├── a_core/ # 영상 입력·추론 실행 (김관용)
├── a_detector/ # 낙하물 모델·클래스 정의 (김관용)
├── b_gateway/ # Spring Boot API 게이트웨이 (장성혁)
├── b_dashboard/ # 관제 대시보드 (장성혁)
├── b_report/ # PDF 증거 리포트 (장성혁)
├── c_person_risk/ # 얼굴 인식·흉기 판정 (이시헌)
├── d_lpr/ # 번호판 인식·위반 감지 (박지원)
├── e_tracking/ # 다중 CCTV 추적·GIS (김준호)
├── docs/ # 설계 문서, 모델 성능 자료, ERD
└── data/ # 테스트 영상 등 (Git 미포함)

## 공통 이벤트 스키마

전 모듈은 탐지 결과를 아래 규격으로 통일해 `POST /api/events`로 전송한다. 상세 필드 정의는 [`docs/오메카3_통합ERD_규격서_v1.0.docx`](docs/오메카3_통합ERD_규격서_v1.0.docx) 참고.

```json
{
  "camId": "CCTV-014",
  "trackId": null,
  "eventType": "DEBRIS",
  "objectClass": "OBJECT",
  "detectedClass": "electric_scooter",
  "bbox": [x, y, w, h],
  "confidence": 0.912,
  "occurredAt": "2026-08-13T10:20:00.123Z",
  "lat": null,
  "lng": null,
  "roiId": "roi_sidewalk_01",
  "meta": { "stationaryDurationSec": 12.4 }
}
```

이벤트 스키마와 WebSocket 채널은 장성혁(모듈 B)이 소유하며, 다른 모듈은 이를 소비만 하고 임의로 변경하지 않는다.

## 시작하기

```powershell
# 1. 가상환경 및 의존성 설치
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

# 2. 각 모듈 실행 (예: 낙하물 감지)
python a_core/yolo_infer.py
```

각 모듈별 세부 실행 방법은 담당자 폴더 내 README를 참고.

## 데이터셋

- [Roboflow: kick_board](https://universe.roboflow.com/han-a5nvo/kick_board) — Format: YOLOv11
- 다운로드 후 `data/` 폴더에 `train/valid/test/data.yaml` 그대로 압축 해제
- (추후 팀원별 사용 데이터셋 링크 추가)

## 개발 일정

4주 스프린트: 1주차 환경 세팅·기본 탐지 → 2주차 추적·DB 연동 → 3주차 증거 리포트·GIS → 4주차 통합 테스트·발표 준비

