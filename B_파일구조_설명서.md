# 오메카3 B담당 — 파일 구조 설명서

작성: 장성혁 · 2026-08-06 (2.2 항목 수정: DTO 필드 설명 정정)
수정: 장성혁 · 2026-08-06 (1.2~1.7 항목에 target/roi 등록 API 추가 반영)
수정: 장성혁 · 2026-08-07 (대시보드를 정적 HTML에서 b_dashboard(React+Vite)로 이전, 3항목 추가)

한 줄 요약: **b_gateway = 이벤트 받아서 DB 저장·조회·알림**, **b_dashboard = 관제 화면(React)**,
**b_report = 증거 PDF 만들고 경로 등록**.

---

## 1. b_gateway (백엔드 API)

### 1.1 설정 / 실행

| 파일 | 역할 |
|------|------|
| `pom.xml` | Spring Boot 프로젝트 설정 (의존성: Web, JPA, WebSocket, MySQL 등) |
| `src/main/resources/application.yml` | 서버 포트·**omecca** DB 접속 정보 |
| `src/main/resources/schema.sql` | MySQL 테이블 생성 DDL (target / roi / event / report) |
| `OmeccaBackendApplication.java` | 앱 시작 진입점 (`main`) |
| `README.md` | 실행·API 사용법 |

### 1.2 DB 테이블 ↔ 자바 (Entity)

| 파일 | 역할 |
|------|------|
| `entity/Target.java` | 관심 대상 테이블 |
| `entity/Roi.java` | 감지 구역 / 가상 라인 테이블 |
| `entity/Event.java` | 탐지 이벤트 핵심 테이블 |
| `entity/Report.java` | 증거 PDF 메타 테이블 |

### 1.3 허용값 목록 (Enum)

| 파일 | 역할 |
|------|------|
| `entity/enums/EventType.java` | 수배자 / 흉기 / 미등록차량 / 낙하물 등 이벤트 종류 |
| `entity/enums/ObjectClass.java` | PERSON / VEHICLE / OBJECT |
| `entity/enums/RoiType.java` | ZONE / LINE |
| `entity/enums/TargetType.java` | PERSON / VEHICLE |
| `entity/enums/TargetStatus.java` | ACTIVE / CLOSED |
| `entity/enums/ReportStatus.java` | PENDING / GENERATED / FAILED |

### 1.4 DB 조회 (Repository)

| 파일 | 역할 |
|------|------|
| `repository/TargetRepository.java` | target 테이블 CRUD·조회 (status별 페이징 조회 포함) |
| `repository/RoiRepository.java` | roi 테이블 CRUD·조회 (camId별 페이징 조회 포함) |
| `repository/EventRepository.java` | event 테이블 CRUD·카메라/타입별 조회 |
| `repository/ReportRepository.java` | report 테이블 CRUD·이벤트별 조회 |

### 1.5 요청 / 응답 형식 (DTO)

> 2.2 수정: `EventCreateRequest`의 필드 설명이 실제 코드와 다르게 적혀 있던 것을
> 정정함. `class`, `timestamp`라는 필드는 존재하지 않으며, 실제로는 아래 필드명을 사용함.

| 파일 | 역할 |
|------|------|
| `dto/EventCreateRequest.java` | POST 이벤트 JSON 받는 형식. 이벤트 스키마 규격서와 1:1 매핑되며 실제 필드는 `camId`, `trackId`, `eventType`, `objectClass`, `bbox`([x,y,w,h] 배열), `confidence`, `occurredAt`, `location`({lat,lng} 객체), `isRegisteredTarget`, `targetId`, `roiId`, `meta`, `frameRefBefore`, `frameRefAfter` |
| `dto/EventResponse.java` | 이벤트 응답 형식. DB에 분리 저장된 bbox 4컬럼과 lat/lng를 다시 배열/객체 형태로 합쳐서 반환 |
| `dto/LocationDto.java` | `location: {lat, lng}` 중첩 객체 매핑용 보조 DTO |
| `dto/ReportCreateRequest.java` | 리포트 등록 요청 (`eventId`, `pdfPath`, `status`) |
| `dto/ReportResponse.java` | 리포트 응답 형식 (`id`, `eventId`, `pdfPath`, `status`, `generatedAt`, `createdAt`) |
| `dto/TargetCreateRequest.java` | 관심 대상 등록 요청 (`targetType`, `plateNumber`, `personRefId`, `label`, `registeredBy`) — VEHICLE이면 plateNumber, PERSON이면 personRefId 필수(서비스에서 검증) |
| `dto/TargetResponse.java` | 관심 대상 응답 형식 (`id`, `targetType`, `plateNumber`, `personRefId`, `label`, `registeredBy`, `status`, `createdAt`, `closedAt`) |
| `dto/RoiCreateRequest.java` | ROI 등록 요청 (`camId`, `roiType`, `name`, `geometryJson`) |
| `dto/RoiResponse.java` | ROI 응답 형식 (`id`, `camId`, `roiType`, `name`, `geometryJson`, `createdAt`) |

### 1.6 비즈니스 로직 (Service)

| 파일 | 역할 |
|------|------|
| `service/EventService.java` | 이벤트 저장, 필터 조회, 저장 후 WebSocket 전송 |
| `service/ReportService.java` | 리포트 등록·조회·PDF 파일 로드 |
| `service/TargetService.java` | 관심 대상 등록·상태별 조회·추적 종료(close) |
| `service/RoiService.java` | ROI 등록·camId별 조회 |

### 1.7 API 입구 (Controller) · 실시간 알림

| 파일 | 역할 |
|------|------|
| `controller/HealthController.java` | `GET /api/health` — 서버·DB 살아있는지 확인 |
| `controller/EventController.java` | `/api/events` 저장·목록·단건 |
| `controller/ReportController.java` | `/api/reports` 등록·목록·다운로드 |
| `controller/TargetController.java` | `/api/targets` 등록·목록·단건·추적 종료(`PATCH /{id}/close`) — 기능 ③ 관심 대상 등록 화면이 붙는 곳 |
| `controller/RoiController.java` | `/api/rois` 등록·목록·단건 — 기능 ⑤·⑦ ROI/가상 라인 설정이 붙는 곳 |
| `config/WebSocketConfig.java` | 실시간 알림 (`/ws`, `/topic/events`) |

### 1.8 테스트용

| 파일 | 역할 |
|------|------|
| `scripts/mock_events.py` | YOLO 없이 가짜 이벤트를 API로 보내는 스크립트 |

---

## 2. b_report (증거 리포트)

| 파일 | 역할 |
|------|------|
| `requirements.txt` | Python 패키지 (OpenCV, ReportLab, requests) |
| `src/capture.py` | 영상/이미지에서 전·후 프레임 확보 |
| `src/generate_pdf.py` | 캡쳐·번호판·시각 등으로 PDF 생성 |
| `src/register_report.py` | 만든 PDF 경로를 b_gateway에 `POST /api/reports` |
| `src/main.py` | 위 과정을 한 번에 실행하는 CLI |
| `src/__init__.py` | Python 패키지 표시용 (거의 빈 파일) |
| `README.md` | 설치·사용법 |
| `.gitignore` | `.venv`, `output` 등 제외 |

---

## 3. b_dashboard (관제 대시보드, React + Vite)

기존엔 `b_gateway/src/main/resources/static/index.html`(정적 HTML)이었으나 React로 이전됨.
기능은 동일 (이벤트 리스트, 영상 뷰어, 자동 포커싱, 필터, WebSocket 실시간 수신).

| 파일 | 역할 |
|------|------|
| `src/App.jsx` | 최상위 상태 관리 (이벤트 목록, 필터, 포커스된 이벤트) |
| `src/hooks/useEventSocket.js` | WebSocket(`/ws`, STOMP/SockJS) 연결 + `/topic/events` 구독 |
| `src/api.js` | `GET /api/events` 초기 목록 조회 |
| `src/constants.js` | 이벤트 유형별 한글 라벨 / 색상 매핑 |
| `src/components/Header.jsx` | 상단 바 — 연결 상태, 통계, 필터, 자동 포커싱 토글 |
| `src/components/Viewer.jsx` | 영상 뷰어 패널 (선택된 이벤트 상세 + before/after 이미지) |
| `src/components/EventList.jsx` | 이벤트 리스트 패널 |
| `src/components/Badge.jsx` | 이벤트 유형 뱃지 (공통 컴포넌트) |
| `src/components/FrameImage.jsx` | 캡쳐 이미지 1장 (로드 실패 시 대체 표시) |
| `vite.config.js` | dev 서버 proxy 설정 (`/api`, `/ws` → `localhost:8080`) |

개발 중엔 `npm run dev`(5173 포트, 게이트웨이로 proxy)로 띄우고, 배포/데모 때는
`npm run build` 후 `dist/`를 `b_gateway/.../static/`에 복사해서 게이트웨이 하나로 같이 띄움.
자세한 실행법은 `b_dashboard/README.md` 참고.

---

## 4. 전체 흐름

```
탐지 / Mock
    ↓
POST /api/events  (b_gateway)
    ↓
Event 테이블 저장
    ↓
WebSocket /topic/events 알림  ──────→  b_dashboard가 실시간 수신·표시
    ↓
b_report가 PDF 생성 (capture → generate_pdf)
    ↓
POST /api/reports  (b_gateway)
    ↓
Report 테이블에 pdf 경로 저장
```

---

## 5. 참고

- 프로젝트 루트 `b_structure.txt`: 파일 트리 + 각 파일 소스 코드 덤프본 (별도 최신화 필요 — 검증서 2.1 항목 참고)
- DB명: **omecca**
- 테이블: `target` / `roi` / `event` / `report`