# b_dashboard — 관제 대시보드 (React + Vite)

기존 `b_gateway/src/main/resources/static/index.html`(정적 HTML)을 React로 재구현한 버전.
기능은 동일함: 이벤트 리스트, 영상 뷰어(before/after 캡쳐), 신규 이벤트 자동 포커싱,
이벤트 유형/카메라 ID 필터, WebSocket(`/topic/events`) 실시간 수신.

## 개발 중 실행

```bash
npm install
npm run dev
```

`http://localhost:5173`으로 뜨고, `/api`·`/ws` 요청은 `vite.config.js`의 proxy 설정으로
`http://localhost:8080`(b_gateway)에 자동 전달됨. 즉 게이트웨이만 따로 띄워두면
(`cd ../b_gateway && ./mvnw spring-boot:run`) 코드 수정 시 바로바로 반영되면서 개발 가능.

## 배포용 빌드 (게이트웨이 하나로 같이 띄우고 싶을 때)

```bash
npm run build
```

`dist/` 폴더가 생기는데, 이 안의 내용을 그대로 `b_gateway/src/main/resources/static/`에
복사하면 됨 (기존 `index.html` 덮어쓰기). 그러면 `./mvnw spring-boot:run` 하나로
프론트+백엔드가 같이 뜸 — 지금까지 쓰던 방식 그대로.

```bash
npm run build
rm -rf ../b_gateway/src/main/resources/static/*
cp -r dist/* ../b_gateway/src/main/resources/static/
```

## 폴더 구조

```
src/
  main.jsx              # 진입점
  App.jsx                # 최상위 상태 관리 (이벤트 목록, 필터, 포커스)
  App.css / index.css    # 스타일 (기존 대시보드와 동일한 다크 테마)
  api.js                  # REST 호출 (GET /api/events)
  constants.js             # 이벤트 유형별 라벨/색상
  hooks/useEventSocket.js  # WebSocket(STOMP/SockJS) 연결 훅
  components/
    Header.jsx             # 상단 바 (연결 상태, 통계, 필터)
    Viewer.jsx              # 영상 뷰어 패널
    EventList.jsx            # 이벤트 리스트 패널
    Badge.jsx                 # 이벤트 유형 뱃지
    FrameImage.jsx             # before/after 캡쳐 이미지 (로드 실패 시 대체 표시)
```

## WebSocket 관련 — 팀원 모듈 개발자는 안 봐도 되는 부분

`hooks/useEventSocket.js`가 WebSocket 연결을 전부 처리함. 팀원 모듈이 `POST /api/events`로
이벤트를 보내면, 이 대시보드가 자동으로 받아서 화면에 반영함 — 대시보드 코드를
건드릴 필요 전혀 없음. 자세한 흐름은 프로젝트 루트의 `D_팀원_연동_가이드.md` 참고.
