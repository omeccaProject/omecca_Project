# 오메카3 스마트 관제 — 번호판 인식(LPR) / 차량 위반 감지

**담당: 박지원 (부팀장)** · 개발 내용 ④·⑦ · 담당 영역 `lpr/`, `violation/`, `vehicle` 테이블

| 항목 | 내용 |
|---|---|
| ④ DB 미등록 차량 실시간 감지 | 번호판 인식 → 차량 원장 대조 → 대포차·수배·도난·미등록 시 **고위험 차량 경보** |
| ⑦ 불법 유턴·신호 위반 감지 | 가상 라인(ROI) **통과 방향·순서** + 궤적 형태 분석으로 자동 검출 |
| 추가 | 한국형 번호판 전처리·보정, 위반 유형별 발생 현황·통계 화면 |

영상이나 모델 가중치 없이도 **Mock 모드로 전체 흐름이 그대로 돌아간다.**

---

## 1. 빠른 시작

```bash
pip install -r requirements.txt

python run_demo.py --reset          # Mock 시나리오 6종 실행
python -m pytest tests -q           # 테스트 241건
python run_demo.py --reset --serve  # 서버 기동 → http://localhost:8010
```

**사진·영상으로 확인**

```bash
python try_lpr.py 사진.jpg --stages   # 검출 크롭 → 기울기 보정 → 이진화 단계까지 저장
python try_lpr.py 사진폴더/
python try_lpr.py 블랙박스.mp4         # 프레임 다수결로 확정
```

결과는 `output/` 에 저장된다. 검출 박스, 인식 번호판, 신뢰도, DB 조회 결과(수배·대포차·미등록)가 그려진다.

---

## 2. 팀 연동 규격 ★

**다른 팀원과 코드를 합칠 때 이 장만 보면 된다.**

```
CCTV 프레임
   │
   ├─ [김관용] YOLOv11 차량 탐지 ─┐
   ├─ [김준호] ByteTrack track_id ┤
   │                              ▼
   │                      Detection  ──→  [박지원] ViolationEngine.process()
   │                                              │
   │                                      ViolationEvent
   │                                              │
   │              ┌───────────────────────────────┼───────────────────┐
   │              ▼                               ▼                   ▼
   │      [장성혁] WebSocket 허브          MySQL violation 테이블   [김준호] GIS
   │      [장성혁] PDF 증거 리포트                                    경로 표시
```

### 입력 — 김관용·김준호 → 박지원

`app/core/schemas.py` 의 `Detection` 을 그대로 만들어 `ViolationEngine.process()` 에 넣으면 된다.

```python
from app.core.schemas import Detection, BBox, ObjectClass
from app.violation.engine import ViolationEngine

engine = ViolationEngine()

det = Detection(
    cam_id="CAM-001",        # str   카메라 식별자
    track_id=101,            # int   ByteTrack 이 부여한 객체 ID
    cls=ObjectClass.CAR,     # car / bus / truck / motorcycle
    bbox=BBox(700, 900, 860, 1020),   # 좌상단 x1,y1 / 우하단 x2,y2 (픽셀)
    timestamp=1786068661.15, # float 유닉스 시각(초)
    confidence=0.92,         # float 0~1
    frame_no=1530,           # int   프레임 번호 (증거 캡처 구간 특정용)
)

events = engine.process(det, frame=원본프레임)   # frame 은 numpy BGR 이미지
```

- **프레임마다 차량 하나씩** 넣으면 된다. 내부에서 track_id 별로 궤적을 쌓는다.
- `frame` 을 주면 번호판까지 읽고, `None` 이면 위반 판정만 한다.
- 반환값은 `list[ViolationEvent]` (없으면 빈 리스트).

### 출력 — 박지원 → 장성혁·김준호

`ViolationEvent.to_payload()` 결과. WebSocket `/ws` 와 REST `/api/violations` 가 같은 구조를 쓴다.

```json
{
  "event_id": "fff813e4855e422d",
  "type": "red_light",
  "label": "신호 위반",
  "cam_id": "CAM-001",
  "track_id": 101,
  "timestamp": 1786068661.155,
  "plate_no": "12가3456",
  "plate_confidence": 0.91,
  "risk_level": "high",
  "vehicle_status": "wanted",
  "zone_id": "INT-A",
  "detail": "적색 신호 중 정지선 통과",
  "evidence_frames": [1520, 1560],
  "trajectory": [[760.0, 480.0], [760.0, 700.0]],
  "location": [37.5665, 126.978]
}
```

| 필드 | 값 | 쓰는 곳 |
|---|---|---|
| `type` | `red_light` / `illegal_uturn` / `high_risk_vehicle` | 화면 분류 |
| `risk_level` | `high` / `caution` / `normal` | 경보 색상 |
| `vehicle_status` | `registered` `unregistered` `stolen` `wanted` `fake_plate` `impound` `insurance_expired` | 상세 표시 |
| `evidence_frames` | `[시작, 끝]` 프레임 번호 | **장성혁** PDF 증거 리포트 캡처 구간 |
| `trajectory` | 최근 30개 `[x, y]` | **김준호** GIS 이동 경로 |
| `location` | `[위도, 경도]` | **김준호** 지도 표시 |

### b_gateway 로 보내기 (장성혁 담당 서버) ★

`shared/schemas/이벤트_스키마_규격서.md` 규격으로 변환해 `POST /api/events` 로 보낸다.
**한 줄만 추가하면 위반 이벤트가 자동으로 게이트웨이까지 흘러간다.**

```python
from app.core.gateway import GatewayClient
from app.violation.engine import ViolationEngine

gw = GatewayClient(base_url="http://localhost:8080").start()
gw.subscribe_to_bus()          # 이 한 줄

engine = ViolationEngine()
engine.process(det, frame=프레임)   # 이후 모든 위반이 게이트웨이로 전송된다
```

내부 표현과 전송 규격이 다른 부분은 `app/core/gateway.py` 가 알아서 변환한다.

| 항목 | 우리 내부 | 게이트웨이 규격 |
|---|---|---|
| 필드명 | `cam_id` | `camId` (camelCase) |
| trackId | `101` (int) | `"trk-101"` (string) |
| 이벤트명 | `red_light` | `SIGNAL_VIOLATION` |
| | `illegal_uturn` | `UTURN_VIOLATION` |
| | `high_risk_vehicle` | `UNREGISTERED_VEHICLE` |
| bbox | `[x1,y1,x2,y2]` | `[x, y, w, h]` |
| 시각 | 유닉스 초 | `"2026-08-06T10:12:33"` |
| 위치 | `[위도, 경도]` | `{"lat":.., "lng":..}` |
| 위험도·판정근거 | 최상위 | `meta` 안 (규격 4장) |

전송은 **백그라운드 큐**로 나가므로 게이트웨이가 죽어 있어도 탐지는 계속 돈다.

### 이벤트 버스 (같은 프로세스에서 받을 때)

```python
from app.core.bus import bus, TOPIC_VIOLATION, TOPIC_ALERT

def on_event(topic, payload):
    print(topic, payload["plate_no"])

bus.subscribe(on_event)
```

| 토픽 | 언제 |
|---|---|
| `lpr.plate` | 번호판이 확정될 때마다 |
| `vehicle.alert` | 대포차·수배·도난·미등록 감지 |
| `violation.event` | 위 셋 + 신호위반·불법유턴 전부 |

### REST / WebSocket (다른 프로세스에서 받을 때)

```bash
python -m uvicorn app.api.server:app --port 8010
```

| 메서드 | 경로 | 설명 |
|---|---|---|
| WS | `/ws` | 위반·경보 실시간 푸시 |
| GET | `/api/violations` | 위반 목록 (`type`, `cam_id`, `risk_level`, `limit`) |
| GET | `/api/stats` | 전체 통계 (요약/유형별/카메라별/시간대별/일자별/위험도별) |
| GET | `/api/vehicles/{plate_no}` | 번호판 단건 조회 (1글자 오차 유사매칭 포함) |
| GET | `/api/zones` | 카메라별 가상 라인·ROI (화면 오버레이용) |
| GET | `/health` | 상태 확인 |

### DB 테이블

`sql/schema.sql` — `vehicle`, `violation`, `plate_read_log` (MySQL 8.0).
`violation.plate_no` 에는 **FK 를 걸지 않았다.** 미등록 차량 감지가 핵심 기능이라
원장에 없는 번호판도 기록되어야 하기 때문이다.

---

## 3. 구조

```
app/
├── core/
│   ├── schemas.py       공통 규격 (Detection, PlateResult, ViolationEvent)
│   ├── geometry.py      라인 통과·ROI 포함·진행 방향 각도
│   ├── config.py        설정 로더
│   └── bus.py           이벤트 버스
├── lpr/                 ── 번호판 인식 ──
│   ├── detector.py      번호판 영역 검출 (YOLO → OCR 텍스트검출 → CV 폴백)
│   ├── preprocess.py    확대·CLAHE·잡음제거·기울기보정·여백정리·이진화
│   ├── segment.py       글자 분할 + 숫자/한글 자리 판별
│   ├── recognizer.py    EasyOCR (자리별 allowlist 2패스)
│   ├── plate_format.py  한국형 포맷 검증 + 오인식 보정
│   ├── pipeline.py      다중 프레임 가중 다수결
│   └── visualize.py     결과 그리기 (한글 라벨, 한글 경로 안전 입출력)
├── vehicle/             ── 차량 DB 대조 ──
│   ├── repository.py    SQLite ↔ MySQL
│   └── matcher.py       실시간 대조 + 고위험 경보
├── violation/           ── 위반 감지 ──
│   ├── roi.py           가상 라인 / ROI
│   ├── signal_state.py  신호 상태 (고정주기 / 외부 주입)
│   ├── trajectory.py    track별 궤적 버퍼
│   ├── detectors.py     신호위반 · 불법유턴 판정
│   └── engine.py        전체 조립
├── api/                 FastAPI REST + WebSocket + 통계
└── simulator.py         Mock 궤적 생성기
```

---

## 4. 판정 로직 요약

### 번호판 인식

1. **전처리** — 확대 → CLAHE → (조건부) 잡음 제거 → 기울기 보정 → 여백 정리 → 이진화.
   기울기는 **문자 블롭 중심선 + 판 테두리** 두 방식으로 추정해 교차 검증한다.
2. **자리별 2패스 인식** — 숫자와 한글을 한 allowlist 에 두면 OCR 이 한글 자리에서
   숫자를 골라 `나→4`, `아→0` 오인식이 대량 발생한다(실측 오류의 93%).
   한글 자리를 배경으로 덮고 **숫자 전용**으로 한 번, 한글 자리만 잘라 **한글 전용**으로
   한 번 인식한 뒤 합친다.
3. **포맷 보정** — `O→0`, `I→1`, `S→5`, `B→8` 자리별 교정 + 한국형 포맷 검증
4. **프레임 다수결** — 같은 track 에서 여러 프레임을 모아 과반 득표만 확정

### 신호 위반

정지선을 진행 방향으로 통과한 시점의 신호가 적색이면 후보 등록 → 진출선까지
통과해야 확정. 정지선만 밟고 멈춘 차량, 역방향 통과, 신호 전환 직후 유예(딜레마 존)는 제외.

### 불법 유턴

유턴 금지 ROI 안 궤적을 전·후반부로 나눠 평균 진행 방향 각도차를 본다.
150도 이상 + 시작·끝점 거리가 이동거리 대비 짧을 때만 판정 → 좌·우회전(약 90도)은 제외.

### 오탐 억제

| 상황 | 대응 |
|---|---|
| 같은 차량 연속 경보 | track·번호판 단위 쿨다운 (위반 10초 / 경보 30초) |
| OCR 1글자 오차 | 유사 매칭으로 구제, 동점 후보 둘 이상이면 미채택 |
| 미등록 오판 | 미등록 경보는 신뢰도 기준을 0.15 더 높게 |
| 좌표가 라인 위에 정확히 놓임 | 마지막 비영 부호 지점 기준 판정 |

---

## 5. 설정

`config.yaml` — 임계값은 실측으로 정했다.

| 설정 | 값 | 근거 |
|---|---|---|
| `deskew_limit` | 35.0 | 추정 오차 35도까지 0.02도, 40도부터 판독 실패 |
| `denoise_min_height` | 28 | 28px 미만은 잡음 제거가 오히려 해로움 |
| `min_plate_height` | 24 | 24px 미만은 정확도 급락 |
| `min_plate_conf` | 0.40 | EasyOCR 실측 분포 기준 |
| `structured_ocr` | true | 자리별 2패스 |

`config_zones.json` — 카메라별 정지선·진출선·유턴 금지 구역 좌표.
카메라를 추가하려면 여기에 픽셀 좌표를 넣으면 된다.

실제 영상으로 전환:

```yaml
lpr:
  mock: false
db:
  driver: mysql
```

---

## 6. 검증 현황

테스트 **241건 통과**.

| 항목 | 상태 |
|---|---|
| 위반 판정 (신호위반·불법유턴·ROI) | 오탐 반례 포함 통과 |
| 차량 DB 대조·고위험 경보 | 유사매칭·쿨다운·임계값 통과 |
| 전처리 (기울기 보정·이진화) | OpenCV 실행 검증 완료 |
| EasyOCR 인식 | 실제 사진으로 동작 확인 |
| 번호판 검출 (CV 폴백) | 실제 CCTV 4K 전체 화면에서 **3.3%** — YOLO 학습 필요 |
| MySQL DDL | 문법·런타임 SQL 검증 (서버 연결은 미검증) |

**남은 작업**

- [ ] 번호판 검출 YOLO 학습 (AI Hub 데이터, bbox 40,735개)
- [ ] 직접 촬영 사진으로 전체 번호판 인식률 측정
- [ ] MySQL 서버 연결 테스트
- [ ] 김관용 님 `Detection` 출력과 실연동

---

## 7. 개인정보보호법 대응

- 번호판 인식은 범죄 예방·교통 단속 목적으로 한정 (법 제25조 목적 제한)
- `plate_read_log` 는 인식률 튜닝 목적, **보관 30일 이내** 운영 전제
- 원본 프레임을 이벤트에 저장하지 않고 `evidence_frames`(번호)만 남겨,
  증거 리포트 생성 시점에만 이미지를 만든다
- 발표 자료에는 번호판을 마스킹할 것
