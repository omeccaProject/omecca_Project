# b_gateway — 백엔드 게이트웨이

오메카3 프로젝트의 이벤트 수신·저장·조회·실시간 알림 API.

> 2026-08-06: 공통 이벤트 스키마 규격서 / DB 스키마 설계서 기준으로 코드를 재정렬함
> (eventType 값, location 좌표 구조, bbox 4컬럼, target/roi 필드를 원래 설계로 복원).

## 실행 전제

1. MySQL에 `omecca` DB 및 테이블 생성

```bash
mysql -u root -p < src/main/resources/schema.sql
```

2. DB 비밀번호가 있으면 환경변수로 전달

```bash
export DB_USERNAME=root
export DB_PASSWORD=your_password
```

3. 앱 실행

```bash
./mvnw spring-boot:run
# 또는
mvn spring-boot:run
```

## API

| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/health` | 서비스·DB 헬스체크 |
| POST | `/api/events` | 탐지 이벤트 저장 + `/topic/events` 브로드캐스트 |
| GET | `/api/events?camId=&eventType=&page=&size=` | 이벤트 목록 |
| GET | `/api/events/{id}` | 이벤트 단건 |
| POST | `/api/reports` | 리포트 메타 등록 (b_report 연동용) |
| GET | `/api/reports` | 리포트 목록 |
| GET | `/api/reports/{id}` | 리포트 단건 |
| GET | `/api/reports/{id}/download` | PDF 다운로드 |

WebSocket(STOMP): 엔드포인트 `/ws`, 구독 `/topic/events`

### POST /api/events 요청 예시 (공통 이벤트 스키마 규격서 기준)

```json
{
  "camId": "CAM-01",
  "trackId": "trk-1234",
  "eventType": "UNREGISTERED_VEHICLE",
  "objectClass": "VEHICLE",
  "bbox": [120, 80, 90, 140],
  "confidence": 0.93,
  "occurredAt": "2026-08-06T10:12:33",
  "location": { "lat": 37.5326, "lng": 127.0246 },
  "isRegisteredTarget": false,
  "targetId": null,
  "roiId": null,
  "meta": { "plateNumber": "12가3456", "matchedDbId": "wanted_001" },
  "frameRefBefore": "s3://.../before.jpg",
  "frameRefAfter": "s3://.../after.jpg"
}
```

`eventType`은 `WANTED_PERSON` / `WEAPON` / `UNREGISTERED_VEHICLE` / `DEBRIS` /
`DUI_PATTERN` / `SIGNAL_VIOLATION` / `UTURN_VIOLATION` 중 하나여야 합니다.
`objectClass`는 `PERSON` / `VEHICLE` / `OBJECT` 중 하나입니다 (세부 종류는 `meta`에 담습니다).

## Mock 이벤트

```bash
python scripts/mock_events.py --count 10 --interval 1
```
