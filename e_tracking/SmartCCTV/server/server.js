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

const app = express();

// 로컬 테스트 단계이므로 CORS를 열어둔다. 실제 운영 배포 시에는 프론트엔드 origin으로 제한할 것.
app.use(cors());
app.use(express.json()); // realtime_anomaly.py가 POST하는 JSON 이벤트 바디를 파싱하기 위해 필요

app.get("/api/health", (req, res) => {
  res.json({ ok: true, hasApiKey: !!process.env.UTIC_API_KEY });
});

app.use("/api/utic", uticRouter);

// Forza 데모 mp4(프로젝트 루트 /videos)를 정적으로 제공한다. web/index.html이 어디서
// 서빙되든(python -m http.server, Live Server, file:// 등) 이 서버(server.js)를 통해서만
// 영상을 가져오면 항상 동일하게 동작한다 - web/map.js의 CONFIG.FORZA_DEMO_SOURCES가
// "http://localhost:<PORT>/videos/forza_A.mp4" 형태의 절대 URL로 이 경로를 참조한다.

app.use("/videos", express.static(path.resolve(__dirname, "../videos")));
app.use(express.static(path.resolve(__dirname, "../web")));   // ← 추가: web/index.html을 "/"에서 서빙

// realtime_anomaly.py(AI) → /api/map/events(POST) → WebSocket(/events) → web/map.js
// 새 통신 방식이 아니라, 이 파일이 이미 쓰고 있는 Express REST 구조를 그대로 확장한 것이다.
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
  console.log(`Forza 데모 영상:     http://localhost:${PORT}/videos/forza_A.mp4 (B/C/D 동일)`);
});