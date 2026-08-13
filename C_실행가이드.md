# 오메카3 B담당 — 처음부터 실행하는 순서

작성: 장성혁 · 2026-08-06

`b_gateway`(백엔드 API) + `b_dashboard`(관제 대시보드, React) + `b_report`(증거 PDF) 를
완전히 처음 상태에서 켜서 event → 저장 → 실시간 알림 → 대시보드 표시 → PDF 리포트 생성 →
등록까지 전체 흐름을 검증하는 순서입니다. 팀원 모델이 아직 없어도 mock 데이터로 전부 확인 가능합니다.

---

## 0. 사전 준비물

- MySQL (로컬에 설치되어 있고 root 계정으로 접속 가능해야 함)
- Java 21 (`java -version`으로 확인)
- Node.js 18 이상 (`node -v`로 확인 — `b_dashboard` 실행용)
- Python 3.x

---

## 1. DB 테이블 생성

`b_gateway` 폴더에서:

```bash
cd b_gateway
mysql -u root -p < src/main/resources/schema.sql
```

`omecca` 데이터베이스와 `target` / `roi` / `event` / `report` 4개 테이블이 생성됩니다.
DB 비밀번호가 root 기본값이 아니면 실행 전에 환경변수로 지정:

```bash
export DB_USERNAME=root
export DB_PASSWORD=your_password
```

---

## 2. 게이트웨이(Spring Boot) 실행

```bash
cd b_gateway
./mvnw spring-boot:run
```

- 기본 포트 `8080`. **"Port 8080 was already in use"** 에러가 나면 이미 떠 있는 이전 프로세스가 있다는 뜻 →
  `lsof -i :8080` 으로 PID 확인 후 `kill -9 <PID>`, 또는 그냥 이미 떠 있는 그 프로세스를 그대로 사용.
- 정상 기동되면 헬스체크로 확인:
  ```bash
  curl localhost:8080/api/health
  ```

---

## 3. 관제 대시보드 확인

대시보드는 `b_dashboard/`(React + Vite)로 이전됨. 개발 중엔 별도 서버로 띄우는 게 편함:

```bash
cd b_dashboard
npm install     # 처음 한 번만
npm run dev
```

브라우저에서 `http://localhost:5173` 접속 (게이트웨이는 2단계에서 이미 떠 있어야 함 —
Vite가 `/api`, `/ws` 요청을 자동으로 `localhost:8080`에 전달해줌).

> 주의: 반드시 **http**로 접속. 브라우저가 자동으로 https로 리다이렉트하면 TLS 관련
> 에러가 서버 로그에 찍힘 — 시크릿창 또는 `http://127.0.0.1:5173`으로 우회.

상단 연결 상태가 "실시간 연결됨"(초록 점)으로 뜨는지 확인.

게이트웨이 하나로 프론트+백엔드를 같이 띄우고 싶으면(데모/시연용):

```bash
cd b_dashboard
npm run build
rm -rf ../b_gateway/src/main/resources/static/*
cp -r dist/* ../b_gateway/src/main/resources/static/
```

---

## 4. Target / ROI 등록 API 테스트 (선택)

```bash
# 관심 대상 등록
curl -X POST localhost:8080/api/targets \
  -H "Content-Type: application/json" \
  -d '{"targetType":"VEHICLE","plateNumber":"12가3456","registeredBy":"operator01"}'

# ROI 등록
curl -X POST localhost:8080/api/rois \
  -H "Content-Type: application/json" \
  -d '{"camId":"CAM-01","roiType":"ZONE","name":"1번 차로 정지구역","geometryJson":{"type":"polygon","points":[[0,0],[100,0],[100,100],[0,100]]}}'
```

---

## 5. Mock 이벤트로 파이프라인 흘려보기

```bash
cd b_gateway
python3 scripts/mock_events.py --count 10 --interval 1
```

- 콘솔에 `[201] {...}` 로 저장된 이벤트가 찍힘
- 동시에 브라우저 대시보드 이벤트 리스트에 실시간으로 뜨고, "신규 이벤트 자동 포커싱"이 켜져있으면
  영상 뷰어가 자동으로 해당 CCTV로 전환되는지 확인

---

## 6. b_report — 증거 PDF 생성 + 등록

### 6.1 환경 세팅 (처음 한 번만)

```bash
cd b_report
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 6.2 테스트용 이미지 준비 (실제 캡쳐 이미지 없을 때)

```bash
python3 -c "
from PIL import Image
Image.new('RGB', (640,480), (40,60,90)).save('samples_before.jpg')
Image.new('RGB', (640,480), (90,40,40)).save('samples_after.jpg')
"
```

### 6.3 PDF 생성 + 게이트웨이 등록

5단계에서 만든 mock 이벤트 중 아직 리포트를 등록하지 않은 `event-id`를 사용
(같은 이벤트로 두 번 등록하면 `409 Conflict` — report는 이벤트 1건당 1건만 허용됨):

```bash
python -m src.main \
  --event-id 4 \
  --title "신호위반 증거 리포트" \
  --event-type SIGNAL_VIOLATION \
  --occurred-at "2026-08-06T13:22:27" \
  --location "교차로 A" \
  --cam-id CAM-02 \
  --track-id trk-3629 \
  --confidence 0.841 \
  --bbox 242 125 120 143 \
  --plate "12가3456" \
  --before samples_before.jpg \
  --after samples_after.jpg \
  --gateway-url http://localhost:8080
```

`--cam-id` / `--track-id` / `--confidence` / `--bbox`는 선택값이라 없어도 동작함
(bbox를 넣으면 PDF 이미지에 탐지 영역이 빨간 박스로 표시됨).

### 6.4 등록 결과 확인

```bash
curl localhost:8080/api/reports
```

방금 등록한 리포트가 `GENERATED` 상태로 보이면 정상. 콘솔에 출력된
`output/event_2/report_2_....pdf` 경로를 열어서 내용 확인.

---

## 참고 — 알아두면 좋은 점

- PDF 한글은 reportlab 내장 CID 폰트(`HYSMyeongJo-Medium`, `HYGothic-Medium`)로 렌더링됨.
  별도 폰트 파일 설치 불필요하나, `·`(가운뎃점) 같은 특수문자는 깨지므로 텍스트에 넣지 말 것 — `/`나 `-`로 대체.
- report는 `event_id`당 1건만 등록 가능 (DB `UNIQUE` 제약). 같은 이벤트로 재테스트하려면 다른 이벤트 id 사용.
- 인증/권한은 아직 미구현 상태 (탐지 모듈용 API 키, 관제요원 로그인/JWT 예정 — 다음 작업).

---

## 전체 순서 한눈에 보기

1. `mysql -u root -p < b_gateway/src/main/resources/schema.sql`
2. `cd b_gateway && ./mvnw spring-boot:run`
3. `cd b_dashboard && npm install && npm run dev` → 브라우저 `http://localhost:5173` 접속 확인
4. (선택) `/api/targets`, `/api/rois` curl 테스트
5. `python3 scripts/mock_events.py --count 10 --interval 1`
6. `cd b_report && source .venv/bin/activate && python -m src.main ...`
7. `curl localhost:8080/api/reports` 로 최종 확인
