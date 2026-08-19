# 빠른 시작

처음 받은 사람이 화면까지 보는 데 필요한 전부. **DB 는 손대지 않는다.**

---

## 0. 설치돼 있어야 하는 것

| | 확인 |
|---|---|
| MySQL 8 | `mysql --version` |
| Java 21 | `java -version` |
| Node 18+ | `node -v` |
| Python 3 | `python --version` |

MySQL 은 **서버만 켜져 있으면 된다.** 데이터베이스나 테이블은 만들지 않는다 — Flyway 가 한다.

---

## 1. 빌드 (처음 한 번, 5분)

```powershell
cd omecca_Project

cd b_gateway;                        .\mvnw clean package -DskipTests;  cd ..
cd b_dashboard;                      npm install;                       cd ..
cd e_tracking\SmartCCTV\server;      npm install;                       cd ..\..\..
```

---

## 2. 비밀번호 한 줄 (처음 한 번)

```powershell
copy b_gateway\.env.example b_gateway\.env
notepad b_gateway\.env
```

`DB_PASSWORD` 를 **본인 MySQL 비밀번호**로 바꾼다. 나머지는 그대로 둔다
(`GATEWAY_API_KEY` 와 `JWT_SECRET` 은 팀 전체가 같은 값이어야 한다).

---

## 3. 실행

```powershell
.\start.ps1 -Run
```

창 3개가 뜨고 브라우저가 열린다.

```
b_gateway    :8080   API + DB
지도 서버     :4000   GIS
b_dashboard  :5173   관제 화면
```

로그인 — **`admin` / `admin1234`**

> 준비가 됐는지만 보려면 `.\start.ps1` (실행 없이 점검만).
> 화면에 데이터까지 채우려면 `.\start.ps1 -Run -Mock`.

---

## 4. 화면에 데이터 넣기

### 가짜 이벤트 (연결 확인용, 10초)

```powershell
cd b_gateway
python scripts\mock_events.py --count 10 --interval 1
```

### 진짜 — 영상에서 번호판·위반 감지

```powershell
cd d_lpr
python run_uturn.py --video 123.mp4 --cam UTURN3 `
  --weights ..\e_tracking\SmartCCTV\yolo11m.pt `
  --lpr --gateway http://localhost:8080
```

먼저 가짜로 화면이 도는지 보고, 그다음 진짜를 돌리면 문제가 생겼을 때
**연결 문제인지 모델 문제인지** 바로 갈린다.

---

## DB 는 왜 안 만드나

Flyway 가 게이트웨이 기동 때 자동으로 한다.

```
java -jar ...
  → 데이터베이스 omecca 생성 (없으면)
  → V1 camera, camera_catalog, target, roi, event, report, user
  → V2 vehicle, plate_read_log        (d_lpr)
  → V3 시연용 차량 12대
```

두 번째부터는 **이미 적용된 건 건너뛴다.** "내가 이거 돌렸던가?" 를 고민할 필요가 없다.

`schema.sql` 을 직접 실행하던 방식은 더 이상 쓰지 않는다.

### 스키마를 바꿔야 할 때

`b_gateway/src/main/resources/db/migration/` 에 **새 파일**을 만든다.

```
V4__add_something.sql
```

**이미 적용된 V1~V3 를 수정하면 안 된다.** Flyway 가 체크섬을 기록해 두기 때문에
바뀌면 다음 실행에서 "Migration checksum mismatch" 로 기동이 멈춘다.

번호가 겹치면 충돌하니 만들기 전에 팀에 한마디 한다.

### `flyway clean` 금지

스키마의 **모든 테이블**을 지운다. `clean-disabled: true` 로 막아 뒀다. 빼지 말 것.

---

## 안 될 때

| 증상 | 원인 |
|---|---|
| `Access denied for user 'root'` | `b_gateway\.env` 의 `DB_PASSWORD` 가 자리표시자 그대로거나 틀림 |
| `Could not resolve placeholder 'DB_USERNAME'` | `.env` 가 없거나, `b_gateway` **밖에서** 실행함 |
| `Could not find or load main class` | 경로에 한글이 있을 때 `mvnw spring-boot:run` 이 실패한다 → `java -jar` 로 실행 |
| `Unknown database 'omecca'` | JDBC URL 에 `createDatabaseIfNotExist=true` 가 빠짐 |
| 대시보드에 `ECONNREFUSED /ws/info` | 게이트웨이가 아직 안 뜸. **뜨면 저절로 멎는다** |
| 지도만 비어 있음 | 지도 서버(:4000)가 안 떴다 |
| `[PostGIS] 연결 실패` | 정상. 경로 저장용 선택 기능이라 지도는 그대로 된다 |
| `Whitelabel Error Page` (8080) | 정상. API 서버라 `/` 에 화면이 없다 |

---

## 매번 실행할 때

1~2 는 처음 한 번뿐이다. 그다음부터는:

```powershell
.\start.ps1 -Run
```
