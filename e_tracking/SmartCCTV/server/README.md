# UTIC CCTV Open API 프록시 테스트 서버

브라우저(프론트엔드)가 UTIC API Key를 직접 다루지 않도록,
이 작은 Node.js/Express 서버가 중간에서 UTIC 공식 CCTV Open API를 대신 호출합니다.

```
브라우저 → 이 서버(GET /api/utic/cctv/test) → UTIC 공식 CCTV Open API → 이 서버 → 브라우저
```

기존 `web/`(프론트엔드), `videos/`, `anomaly_detection.py`, `export_track_log.py`는
이 작업에서 전혀 건드리지 않았습니다. 완전히 독립된 새 폴더입니다.

## 1. 설치 위치

이 `server/` 폴더를 프로젝트 루트(`anomaly_detection.py`, `web/`, `videos/`가 있는 위치)에
그대로 넣어주세요.

```
SMARTCCTV/
├── .env                  ← 새로 만들 파일 (아래 2번 참고)
├── .gitignore             ← .env 추가 필요 (아래 3번 참고)
├── server/                ← 이번에 추가된 폴더
│   ├── server.js
│   ├── package.json
│   ├── routes/utic.js
│   └── utic/uticClient.js
├── web/                   ← 기존 프론트엔드 (변경 없음)
├── videos/                ← 기존 (변경 없음)
├── anomaly_detection.py   ← 기존 (변경 없음)
└── export_track_log.py    ← 기존 (변경 없음)
```

## 2. .env 만들기

`project-root-additions/.env.example` 파일을 프로젝트 루트로 복사해서 이름을 `.env`로 바꾸고,
실제 발급받은 키와 UTIC 매뉴얼에 적힌 정보를 채워주세요.

```
cp .env.example .env
```

**중요**: `UTIC_CCTV_API_URL`은 UTIC에서 API Key 발급 시 함께 준 매뉴얼(PDF/문서)에 적힌
실제 요청 URL로 반드시 교체해야 합니다. `REPLACE_ME...` 상태로 두면 서버가 명확한 에러를
내며 호출 자체를 하지 않습니다 (잘못된 곳에 요청을 보내 키를 낭비하지 않기 위한 안전장치입니다).

## 3. .gitignore 확인

프로젝트 루트의 `.gitignore`에 `.env`가 포함되어 있는지 확인해주세요.
없다면 `project-root-additions/.gitignore.snippet.txt`의 내용을 추가해주세요.

이미 Git 저장소를 쓰고 계시다면, 아래 명령으로 `.env`가 추적되고 있지 않은지 확인할 수 있습니다.

```
git status
# .env 가 목록에 안 보이면 정상 (무시되고 있는 것)
git check-ignore -v .env
# 위 명령이 뭔가 출력하면 정상적으로 무시되고 있다는 뜻
```

## 4. 설치 및 실행

```
cd server
npm install
npm start
```

정상적으로 뜨면 이런 로그가 보입니다.

```
UTIC 프록시 테스트 서버 실행 중: http://localhost:4000
헬스체크:            http://localhost:4000/api/health
테스트(H4642 기본):  http://localhost:4000/api/utic/cctv/test
테스트(J7878 지정):  http://localhost:4000/api/utic/cctv/test?camId=J7878
```

## 5. 테스트

브라우저 주소창이나 curl로:

```
curl http://localhost:4000/api/utic/cctv/test
curl http://localhost:4000/api/utic/cctv/test?camId=J7878
```

서버를 실행한 터미널 창에 `[UTIC CCTV API TEST]`로 시작하는 진단 로그가 출력됩니다.
(API Key는 절대 로그/응답에 나타나지 않고, 요청 URL의 키 부분은 `***`로 마스킹됩니다.)

## 6. 이번 단계에서 하지 않은 것

- 프론트엔드(`web/map.js`)는 전혀 수정하지 않았습니다. 지금은 이 테스트 서버만 단독으로 호출해보는 단계입니다.
- 4,255개 CCTV 전체를 UTIC API로 교체하지 않았습니다.
- `H4642 → videos/0805.mp4`, `J7878 → videos/traffic.mp4` 연결과 AI 분석 기능은 그대로입니다.
