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

`omecca` 데이터베이스와 `camera` / `camera_catalog` / `target` / `roi` / `event` / `report` / `user`
총 7개 테이블이 생성됩니다. `camera`/`camera_catalog`에는 실시간 CCTV 카메라 23개가,
`user`에는 관리자 계정(`admin` / `admin1234` — 로그인 후 꼭 변경할 것)이 시드 데이터로 같이 들어갑니다.

> 이미 예전 버전의 DB(4개 테이블만 있던 시절)를 갖고 있어서 `camera`/`camera_catalog`/`user`가
> 없다면, `schema.sql`을 다시 실행하지 말고(기존 데이터가 전부 날아감) `DB_마이그레이션_가이드.md`를
> 참고해서 없는 테이블만 개별 추가하세요.

### 환경변수 설정 (`.env` 파일 방식 — 추천)

`b_gateway/.env.example`을 복사해서 같은 폴더에 `.env`로 저장하고 값을 채우면, `./mvnw spring-boot:run`
실행 시 자동으로 읽어들입니다(매번 `export` 칠 필요 없음):

```bash
cp .env.example .env
```

`.env` 안에 최소 아래 4개 값이 있어야 합니다.

```
GATEWAY_API_KEY=omecca-dev-key-2026
JWT_SECRET=omecca-jwt-secret-change-this
DB_USERNAME=root
DB_PASSWORD=본인_로컬_MySQL_비밀번호
```

`GATEWAY_API_KEY`/`JWT_SECRET`은 기본값이 없어서 안 넣으면 게이트웨이가 아예 안 켜집니다.
팀 전체가 같은 값을 써야 모듈→게이트웨이 인증(`X-API-Key`)이 맞으니 위 값 그대로 쓰세요.
`.env`는 `.gitignore`에 등록돼 있어 git에는 올라가지 않습니다.

> **주의 — 셸 환경변수가 `.env`보다 우선 적용됨**: `~/.zshrc`, `~/.bash_profile` 같은 셸 프로필에
> 예전에 `export DB_USERNAME=...` 같은 줄을 추가해둔 적이 있다면, `.env` 파일 값을 아무리 바꿔도
> 그 셸 값이 계속 우선 적용돼서 반영이 안 되는 것처럼 보입니다(dotenv 라이브러리가 이미 설정된
> 시스템 환경변수를 덮어쓰지 않기 때문). 이런 증상이 생기면 `echo $DB_USERNAME`으로 셸에 값이
> 남아있는지부터 확인하고, 남아있으면 프로필 파일에서 그 줄을 지우거나 `unset DB_USERNAME`으로
> 임시 제거한 뒤 재실행하세요.

### (대안) 터미널에서 직접 export 하는 방식

`.env` 대신 매번 터미널에서 직접 지정하고 싶다면:

```bash
export DB_USERNAME=root
export DB_PASSWORD=Omecca\!2026 #비밀번호에 특수문자 있을 시 앞에 \넣기
export GATEWAY_API_KEY=omecca-dev-key-2026
export JWT_SECRET=omecca-jwt-secret-change-this
```

> **Windows(PowerShell) 쓰는 사람은 주의**: 위 `export` 명령어는 Mac/Linux(bash·zsh) 전용
> 문법입니다. PowerShell에서는 아무 에러 없이 그냥 무시되기 때문에 환경변수가 하나도
> 설정되지 않은 채로 실행하게 되는데, 겉으로는 "가이드대로 했는데 인증이 안 된다"처럼
> 보입니다. PowerShell에서는 아래처럼 쓰세요(4개 값 전부 동일하게 적용):
>
> ```powershell
> $env:DB_USERNAME="root"
> $env:DB_PASSWORD="Omecca!2026"
> $env:GATEWAY_API_KEY="omecca-dev-key-2026"
> $env:JWT_SECRET="omecca-jwt-secret-change-this"
> ```
>
> 이 방식은 그 터미널 창을 닫으면 사라집니다. 매번 다시 치기 싫으면 위의 `.env` 파일 방식을
> 쓰는 걸 추천합니다 — 셸 프로필에 영구로 export를 박아두면 나중에 값을 바꿔야 할 때
> (예: 카페24 같은 다른 DB로 테스트) 셸 값이 우선 적용돼서 헷갈리는 원인이 됩니다.

`JWT_SECRET`은 길이 제한이 있는 값이 아닙니다 — 이 프로젝트는 jjwt 같은 외부 라이브러리 없이
HMAC-SHA256을 직접 구현해서 쓰기 때문에(`JwtService.java`), 32바이트 미만이라고 `WeakKeyException`
같은 에러가 나지 않습니다. 즉 **아무 문자열이나 써도 되지만, 그 값을 팀원 전원이 정확히 똑같이
써야만** 합니다. JWT는 "발급한 서버"와 "검증하는 서버"가 같은 비밀키로 서명을 확인하는 구조라,
한 글자라도 다르면 다른 사람이 로그인해서 받은 토큰이 내 서버에서 401로 거부됩니다 — 새로운
값을 만들 필요는 없고, 위에 적힌 `omecca-jwt-secret-change-this`를 그대로 맞춰 쓰면 됩니다.

### 1-1. 로컬 DB 대신 공용 DB(카페24) 쓰기

지금은 팀원마다 로컬 DB가 따로 있어서(각자 `localhost:3306`) 회원가입/승인 같은 게 서로한테
안 보이는 문제가 있어서, 카페24에 공용 MariaDB를 하나 띄워서 다 같이 그걸 보게 만들었습니다.
**로컬 DB를 계속 써도 되고(개인 개발용), 공용 DB로 전환해서 써도 됩니다** — `application.yml`이
`DB_HOST`/`DB_PORT`/`DB_NAME` 환경변수를 안 넣으면 기존처럼 로컬(`localhost:3306/omecca`)을
그대로 쓰도록 기본값이 잡혀 있어서, 아무것도 안 바꾸면 지금까지 하던 대로 동작합니다.

**공용 DB로 전환하려면** `.env`에서 로컬 DB 줄 4개(`DB_USERNAME`/`DB_PASSWORD`)를 주석 처리하고,
아래 5개 줄의 주석을 풀고 비밀번호만 채워 넣으면 됩니다(두 세트를 동시에 켜두면 안 됨 — 마지막에
읽히는 값으로 덮어써져서 꼬입니다).

```
# DB_USERNAME=root
# DB_PASSWORD=본인_로컬_MySQL_비밀번호

DB_HOST=thebrains27.cafe24.com
DB_PORT=3306
DB_NAME=thebrains27
DB_USERNAME=thebrains27
DB_PASSWORD=성혁님한테_받은_카페24_DB_비밀번호
```

> 공용 DB에는 이미 `schema.sql`에 해당하는 테이블 7개(camera/camera_catalog/target/roi/event/report/user)와
> 카메라 23개, admin 계정이 다 들어가 있는 상태입니다 — **여기다 대고 `schema.sql`을 다시 실행하지
> 마세요** (`DROP TABLE`부터 하는 스크립트라 다른 사람 데이터까지 다 날아갑니다). 위 1번 단계는
> 로컬 DB를 쓸 때만 필요한 단계입니다.

**접속하려면 카페24 IP 등록이 먼저 필요합니다.** 공용 DB는 카페24 "MySQL 외부 IP 접근설정"에
등록된 IP에서만 접속을 허용합니다. 등록 안 된 곳에서 접속하면 타임아웃/연결 거부가 나는데,
이건 코드나 `.env` 설정 문제가 아니라 IP 등록이 안 된 것이니 성혁님한테 본인 **공인(외부) IP**를
알려주고 등록을 요청하세요 (구글에서 "내 IP" 검색해서 나오는 값 — `ipconfig`/시스템 설정에서 보이는
`172.x`/`192.168.x` 같은 내부 IP를 알려주면 등록해도 소용없습니다). 와이파이를 옮기면 공인 IP가
바뀌어서 다시 막힐 수 있다는 것도 알아두세요.

HeidiSQL 같은 DB 클라이언트로 직접 접속해서 데이터 확인하고 싶으면 이 값을 쓰면 됩니다.

- 호스트: `thebrains27.cafe24.com`
- 포트: `3306`
- 사용자: `thebrains27`
- DB 종류: MariaDB

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

> **참고**: `GATEWAY_API_KEY`/`JWT_SECRET`을 위 1번 단계에서 export 안 하고 그냥 실행하면
> `Could not resolve placeholder 'GATEWAY_API_KEY'` 에러와 함께 게이트웨이가 안 켜집니다.
> `DB_USERNAME`/`DB_PASSWORD`와 동일하게 필수값으로 바뀌었으니 꼭 먼저 export하세요.

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

## 3-1. GIS 지도 서버(e_tracking/SmartCCTV) 실행

대시보드 화면 중앙의 지도는 `b_dashboard`가 아니라 **별도의 Node 서버**(`e_tracking/SmartCCTV/server`)가
`http://localhost:4000`에서 띄우는 페이지를 iframe(`?embed=map`)으로 불러오는 구조입니다.
이 서버를 안 띄우면 지도 부분만 비어 보이거나, 브라우저 콘솔에 `localhost:4000` 관련
**404 Not Found**가 찍힙니다 — 대시보드/게이트웨이가 멀쩡히 떠 있어도 지도 서버가 따로 안 떠 있으면 발생하는 정상적인 증상입니다.

```bash
cd e_tracking/SmartCCTV
cp .env.example .env    # 처음 한 번만 — 값 채워넣기(아래 참고)
cd server
npm install              # 처음 한 번만
node server.js
```

- 기본 포트 `4000`. 정상 기동되면 콘솔에 `UTIC 프록시 테스트 서버 실행 중: http://localhost:4000`이 찍힘.
- `.env`(`e_tracking/SmartCCTV/.env`, `server/`가 아니라 그 한 단계 위)에 최소한 아래 값은 채워야 함:
  - `GATEWAY_API_KEY=omecca-dev-key-2026` — **1단계에서 게이트웨이에 export한 값과 반드시 동일해야 함**
    (다르면 이 서버가 감지한 이상운전(DUI_PATTERN) 이벤트를 게이트웨이로 전달할 때 `401`로 거절당함)
  - `UTIC_API_KEY` / `UTIC_CCTV_API_URL` 등 UTIC 관련 값 — 실제 CCTV 영상 연동에만 필요, 없어도
    지도 자체(Forza 데모, 실시간 이벤트 표시)는 정상 동작함
  - `PGHOST` 등 PostGIS 값 — 연결 실패해도 서버는 죽지 않고 그대로 뜸(선택 사항)
- 헬스체크: `curl localhost:4000/api/health`
- **"Port 4000 was already in use"** 에러가 나면 `lsof -i :4000` → `kill -9 <PID>` 후 재시도.

---

## 4. Target / ROI 등록 API 테스트 (선택)

> 이 아래 `/api/**` 요청들은 전부 `ApiKeyFilter`가 걸려 있어서 `X-API-Key` 헤더가 없으면
> `401 {"error":"UNAUTHORIZED", ...}`로 거절당함(2단계에서 게이트웨이가 이미 떠 있어야 함).
> 기본 키는 `omecca-dev-key-2026`(application.yml의 `gateway.api-key` 기본값, `b_dashboard/src/config.js`와 동일 —
> `GATEWAY_API_KEY` 환경변수로 바꿔서 띄웠으면 그 값을 대신 넣을 것).

```bash
# 관심 대상 등록
curl -X POST localhost:8080/api/targets \
  -H "Content-Type: application/json" \
  -H "X-API-Key: omecca-dev-key-2026" \
  -d '{"targetType":"VEHICLE","plateNumber":"12가3456","registeredBy":"operator01"}'

# ROI 등록
curl -X POST localhost:8080/api/rois \
  -H "Content-Type: application/json" \
  -H "X-API-Key: omecca-dev-key-2026" \
  -d '{"camId":"CAM-01","roiType":"ZONE","name":"1번 차로 정지구역","geometryJson":{"type":"polygon","points":[[0,0],[100,0],[100,100],[0,100]]}}'
```

---

## 5. Mock 이벤트로 파이프라인 흘려보기

```bash
cd b_gateway
python3 scripts/mock_events.py --count 10 --interval 1
# GATEWAY_API_KEY를 기본값이 아닌 다른 값으로 띄웠다면: --api-key <그 값>도 같이 넘길 것
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
- 인증/권한은 이미 구현 완료 — 모듈→게이트웨이는 `X-API-Key`, 관제요원 로그인은 JWT(1단계 참고).

---

## 전체 순서 한눈에 보기

1. `mysql -u root -p < b_gateway/src/main/resources/schema.sql`
2. `export GATEWAY_API_KEY=... JWT_SECRET=...` (1단계 참고) → `cd b_gateway && ./mvnw spring-boot:run`
3. `cd b_dashboard && npm install && npm run dev` → 브라우저 `http://localhost:5173` 접속 확인
4. `cd e_tracking/SmartCCTV/server && npm install && node server.js` → 지도가 안 뜨거나 404가 나면 이 서버가 꺼져있는 것
5. (선택) `/api/targets`, `/api/rois` curl 테스트
6. `python3 scripts/mock_events.py --count 10 --interval 1`
7. `cd b_report && source .venv/bin/activate && python -m src.main ...`
8. `curl localhost:8080/api/reports` 로 최종 확인
