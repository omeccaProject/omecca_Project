/**
 * server.js
 * ------------------------------------------------------------
 * UTIC CCTV Open API 프록시 테스트 서버.
 *
 * 브라우저 → 이 서버 → UTIC 공식 API → 이 서버 → 브라우저
 * API Key는 이 서버(Node.js 프로세스)에서만 process.env로 읽고, 절대 프론트엔드로 전달하지 않는다.
 */

const path = require("path");
const http = require("http");

// .env는 프로젝트 루트(server/ 폴더의 한 단계 위)에 있다고 가정한다.
require("dotenv").config({ path: path.resolve(__dirname, "../.env") });

const express = require("express");
const cors = require("cors");
const uticRouter = require("./routes/utic");
const { createMapEventsModule } = require("./routes/mapEvents");
const db = require("./db");
const { deleteExistingDemoEvent } = require("./gatewayForward");

// web/map.js의 CONFIG.DEMO_VEHICLE_ID와 반드시 동일한 문자열이어야 한다.
const DEMO_VEHICLE_ID = "DEMO-DRUNK-001";

const app = express();
db.init(); // PostGIS 연결 시도 (실패해도 서버는 계속 뜸)

// 로컬 테스트 단계이므로 CORS를 열어둔다. 실제 운영 배포 시에는 프론트엔드 origin으로 제한할 것.
app.use(cors());
// limit을 늘린 이유: map.js가 "CCTV 영상 보기"로 연결된 영상에서 캡쳐한 사전/사후
// JPEG 이미지를 base64 data URL로 POST /api/map/captures에 담아 보낸다(기본 100kb로는
// 이미지 두 장이 쉽게 넘침). realtime_anomaly.py가 보내는 일반 이벤트 JSON은 원래도 작다.
app.use(express.json({ limit: "8mb" })); // realtime_anomaly.py가 POST하는 JSON 이벤트 바디를 파싱하기 위해 필요

app.get("/api/health", (req, res) => {
  res.json({ ok: true, hasApiKey: !!process.env.UTIC_API_KEY });
});

app.use("/api/utic", uticRouter);

// Forza 데모 mp4(프로젝트 루트 /videos)를 정적으로 제공한다. web/index.html이 어디서
// 서빙되든(python -m http.server, Live Server, file:// 등) 이 서버(server.js)를 통해서만
// 영상을 가져오면 항상 동일하게 동작한다 - web/map.js의 CONFIG.FORZA_DEMO_SOURCES가
// "http://localhost:<PORT>/videos/forza_A.mp4" 형태의 절대 URL로 이 경로를 참조한다.

app.use(express.static(path.resolve(__dirname, "../web")));   // ← 추가: web/index.html을 "/"에서 서빙

// realtime_anomaly.py(AI) → /api/map/events(POST) → WebSocket(/events) → web/map.js
// [버그 수정: "/api/map/demo/reset이 404, ws://localhost:4000/events 연결 실패"]
// 이 모듈을 만들기만 하고 실제로 app에 연결(app.use)/http 서버에 연결(attach)하는
// 코드가 빠져 있었다 - 그래서 정적 파일(index.html/map.js)과 /api/health는 되는데
// /api/map/* 라우트 전부와 /events WebSocket만 항상 404/연결실패였다.
const mapEvents = createMapEventsModule();
app.use("/api/map", mapEvents.router);

// WebSocket은 express의 app.listen이 아니라 http.Server가 필요하므로,
// app을 감싸는 http.Server를 직접 만들고 그 서버로 listen한다 (동작은 기존과 동일).
const server = http.createServer(app);
mapEvents.attach(server, "/events");

const PORT = process.env.PORT || 4000;
server.listen(PORT, () => {
  console.log(`UTIC 프록시 테스트 서버 실행 중: http://localhost:${PORT}`);
  console.log(`헬스체크:            http://localhost:${PORT}/api/health`);
  console.log(`테스트(H4642 기본):  http://localhost:${PORT}/api/utic/cctv/test`);
  console.log(`테스트(J7878 지정):  http://localhost:${PORT}/api/utic/cctv/test?camId=J7878`);
  console.log(`AI 지도 이벤트 수신: POST http://localhost:${PORT}/api/map/events`);
  console.log(`AI 지도 이벤트 WS:   ws://localhost:${PORT}/events`);

});

// [신규] "서버를 끄면 그 순간 DB에 있던 데모 이상운전 데이터가 지워져야 함"
// Ctrl+C(SIGINT)나 프로세스 종료 신호(SIGTERM)를 받으면, 종료하기 전에 게이트웨이에
// 저장돼 있던 이 데모 차량의 이벤트를 먼저 지우고 나서 실제로 종료한다. 이렇게 하면
// "서버가 꺼져 있는 동안(=데모가 실제로 진행 중이 아닌 동안)에는 대시보드에 가짜
// 활성 알림이 남아있지 않는다"가 보장된다. (다음에 켜서 새로고침할 때도 페이지 로드
// 시점의 /api/map/demo/reset이 한 번 더 지워주므로 이중 안전장치가 된다.)
function shutdown(signal) {
  console.log(`\n[서버 종료] ${signal} 수신 - 서버를 종료합니다.`);

  // [버그 수정] 주석엔 "종료 전에 게이트웨이의 데모 이벤트를 지운다"고 돼있었지만
  // 실제로 그 호출이 빠져 있었다 - deleteExistingDemoEvent를 실제로 호출하도록 추가.
  deleteExistingDemoEvent(DEMO_VEHICLE_ID)
    .catch(() => {})
    .finally(() => {
      server.close(() => process.exit(0));
    });

  // 3초 안에 종료되지 않으면 강제 종료
  setTimeout(() => process.exit(0), 3000).unref();
}

process.on("SIGINT", () => shutdown("SIGINT"));
process.on("SIGTERM", () => shutdown("SIGTERM"));