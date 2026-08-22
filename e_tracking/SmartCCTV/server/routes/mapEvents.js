/**
 * routes/mapEvents.js
 * ------------------------------------------------------------
 * realtime_anomaly.py(AI) → 이 서버(Express + WebSocket) → web/map.js
 *
 * 새 통신 방식을 새로 발명하지 않고, 이미 이 프로젝트에 있는 구조를 그대로 재사용한다.
 *   - 수신(Python → 서버): server.js가 이미 쓰고 있는 Express REST 방식 그대로,
 *     POST /api/map/events 엔드포인트 하나만 추가한다.
 *   - 송신(서버 → 브라우저): map.js 상단 주석(1~19줄, 1828~1836줄)에 이미
 *     "향후 WebSocket 연동 시 이렇게 연결하면 된다"고 설계돼 있던
 *     ws://localhost:PORT/events 경로를 그대로 구현한다.
 *
 * AI Python 프로세스가 map.js 파일을 직접 수정/생성하지 않는다 - 항상 이 서버를
 * 경유해서 이벤트를 전달한다 (요구사항 12번 "AI Python이 map.js를 직접 파일
 * 수정하는 방식은 사용하지 않는다"를 만족시키는 지점).
 *
 * 이 모듈은 라우터와 "브로드캐스트 가능한 WebSocket 서버"를 함께 만들어 반환한다.
 * server.js에서 http.Server에 붙여서 사용한다.
 */

const express = require("express");
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const { WebSocketServer } = require("ws");
const db = require("../db");
const { forwardToGateway, deleteExistingDemoEvent, updateGatewayCaptures } = require("../gatewayForward");

// [신규] map.js가 "CCTV 영상 보기"로 연결한 <video>에서 캡쳐한 사전/사후 프레임을 저장하는
// 폴더 - a_core/yolo_infer.py(낙하물 캡쳐), realtime_anomaly.py와 동일한 관례를 그대로
// 따른다: b_dashboard/public/captures/에 JPEG로 저장하고, DB/이벤트에는 b_dashboard가
// 정적으로 서빙하는 "/captures/<uuid>.jpg" 경로만 넘긴다. 이 파일은
// e_tracking/SmartCCTV/server/routes/ 안에 있으므로 프로젝트 루트까지 네 단계 위로
// 올라가야 한다.
const CAPTURES_DIR = path.resolve(__dirname, "../../../../b_dashboard/public/captures");
try {
  fs.mkdirSync(CAPTURES_DIR, { recursive: true });
} catch (err) {
  console.warn("[CAPTURE] captures 폴더 생성 실패:", err.message);
}

// data:image/jpeg;base64,... 형태의 dataURL을 받아 JPEG 파일로 저장하고, b_dashboard가
// 그대로 서빙할 수 있는 루트-절대 경로를 돌려준다. 형식이 이상하거나 저장에 실패하면
// null을 돌려준다(호출부는 예외 없이 그냥 "캡쳐 없음"으로 넘어간다).
function saveDataUrlAsJpeg(dataUrl) {
  if (!dataUrl || typeof dataUrl !== "string") return null;
  const match = /^data:image\/[a-zA-Z+.-]+;base64,(.+)$/.exec(dataUrl);
  if (!match) {
    console.warn("[CAPTURE] 알 수 없는 이미지 데이터 형식 - 저장하지 않습니다.");
    return null;
  }
  const filename = `${crypto.randomUUID()}.jpg`;
  try {
    fs.writeFileSync(path.join(CAPTURES_DIR, filename), Buffer.from(match[1], "base64"));
  } catch (err) {
    console.warn("[CAPTURE] 캡쳐 이미지 저장 실패:", err.message);
    return null;
  }
  return `/captures/${filename}`;
}

// realtime_anomaly.py의 EVENT_LOG_PATH(ai_map_events.log)와는 별개로,
// "서버가 실제로 브로드캐스트한 이벤트"만 별도로 남겨서 디버깅에 쓴다.
const BROADCAST_LOG_PATH = path.resolve(__dirname, "../../ai_map_events_broadcast.log");

// section 11 규격의 필수 필드. 이것만 있으면 최소한의 지도 표시가 가능하다.
// (그 외 필드 - reason/track_id/plate/confidence/video_position_px 등 - 는
//  있으면 그대로 전달하고, 없어도 에러 내지 않는다.)
const REQUIRED_FIELDS = ["source_type", "source_id", "latitude", "longitude", "anomaly"];

function validateEvent(body) {
  if (!body || typeof body !== "object") return "요청 본문이 JSON 객체가 아닙니다.";
  for (const field of REQUIRED_FIELDS) {
    if (body[field] === undefined) return `필수 필드 누락: ${field}`;
  }
  if (body.source_type !== "UTIC" && body.source_type !== "DEMO") {
    return `source_type은 'UTIC' 또는 'DEMO'여야 합니다 (받은 값: ${body.source_type})`;
  }
  if (body.source_type === "DEMO" && !body.global_vehicle_id) {
    return "source_type이 'DEMO'이면 global_vehicle_id가 필요합니다.";
  }
  return null;
}

/**
 * @returns {{ router: express.Router, wss: WebSocketServer, attach: (httpServer) => void }}
 */
function createMapEventsModule() {
  const router = express.Router();
  const wss = new WebSocketServer({ noServer: true });
  const clients = new Set();

  wss.on("connection", (socket) => {
    clients.add(socket);
    console.log(`[MAP WS] 클라이언트 연결됨 (현재 ${clients.size}개)`);
    socket.on("close", () => {
      clients.delete(socket);
      console.log(`[MAP WS] 클라이언트 연결 종료 (현재 ${clients.size}개)`);
    });
    socket.on("error", () => clients.delete(socket));
  });

  function broadcast(payload) {
    const line = JSON.stringify(payload);
    for (const socket of clients) {
      // readyState 1 === OPEN
      if (socket.readyState === 1) socket.send(line);
    }
    try {
      fs.appendFileSync(BROADCAST_LOG_PATH, line + "\n", "utf-8");
    } catch (err) {
      console.warn("[MAP WS] 브로드캐스트 로그 기록 실패:", err.message);
    }
  }

  // realtime_anomaly.py의 event_aggregator 프로세스가 호출하는 단일 진입점.
  // ERD 규격서(오메카3_통합ERD_규격서_v1.0.docx 6장)의 "POST /api/events" 관례와
  // 동일한 스타일로 맞췄다 (이 프로젝트는 지도 데모 전용이라 경로만 /api/map/events로 구분).
  router.post("/events", (req, res) => {
    const err = validateEvent(req.body);
    if (err) {
      console.warn(`[MAP EVENT] 검증 실패: ${err}`, req.body);
      return res.status(400).json({ ok: false, error: err });
    }

    broadcast(req.body);
    db.saveEvent(req.body).catch(() => {});
    forwardToGateway(req.body).catch(() => {});
    console.log(
      `[MAP EVENT] ${req.body.source_type} ${req.body.source_id} → WebSocket 클라이언트 ${clients.size}개에 전달`
    );
    res.json({ ok: true, delivered_to: clients.size });
  });

  router.get("/events/health", (req, res) => {
    res.json({ ok: true, connectedClients: clients.size });
  });

  // [신규] map.js가 "CCTV 영상 보기"로 영상을 연결한 시점에 이미 화면에 떠 있는 그
  // <video>를 캔버스로 캡쳐해서 보내는 endpoint. 낙하물 캡쳐(a_core)/realtime_anomaly.py의
  // 사전·사후 캡쳐와 저장 방식(JPEG → b_dashboard/public/captures/)은 동일하지만, 소스가
  // "백엔드가 별도로 연 스트림"이 아니라 "프론트엔드에 이미 재생 중인 영상"이라는 점이
  // 다르다 - 그래서 새 영상 창/연결을 따로 열지 않는다.
  //
  // body: { trackId, beforeImage?, afterImage? } - beforeImage/afterImage는
  // "data:image/jpeg;base64,..." 형태의 canvas.toDataURL() 결과. 저장에 성공한 경로만
  // b_gateway로 반영한다(둘 다 실패하면 아무것도 하지 않고 400).
  router.post("/captures", (req, res) => {
    const { trackId, beforeImage, afterImage } = req.body || {};
    if (!trackId) {
      return res.status(400).json({ ok: false, error: "trackId가 필요합니다." });
    }
    const frameRefBefore = saveDataUrlAsJpeg(beforeImage);
    const frameRefAfter = saveDataUrlAsJpeg(afterImage);
    if (!frameRefBefore && !frameRefAfter) {
      return res.status(400).json({ ok: false, error: "저장할 수 있는 이미지가 없습니다." });
    }
    updateGatewayCaptures(trackId, frameRefBefore, frameRefAfter).catch(() => {});
    console.log(`[CAPTURE] trackId=${trackId} 캡쳐 저장: before=${frameRefBefore} after=${frameRefAfter}`);
    res.json({ ok: true, frameRefBefore, frameRefAfter });
  });

  // [신규] "새로고침하는 순간 바로 0이 되어야 함" - web/map.js가 페이지 로드 직후(20초
  // 대기 시작과 동시에) 이 endpoint를 호출해서, 이전 세션에서 게이트웨이에 저장해 둔
  // Forza DEMO 이벤트를 즉시 지운다. 이렇게 해야 "새로고침 직후~20초" 구간에도
  // 대시보드 이벤트 리스트가 0을 보여주고, 20초 뒤 알림이 뜰 때 비로소 1이 된다
  // (지금까지처럼 "새 이벤트 보내기 직전에만" 지우면, 그 사이 구간엔 이전 세션의
  // 이벤트가 여전히 남아있는 것처럼 보였다).
  //
  // body: { trackId: "DEMO-DRUNK-001" } - map.js의 CONFIG.DEMO_VEHICLE_ID를 그대로 보낸다.
  router.post("/demo/reset", async (req, res) => {
    const trackId = req.body && req.body.trackId;
    if (!trackId) {
      return res.status(400).json({ ok: false, error: "trackId가 필요합니다." });
    }
    try {
      await deleteExistingDemoEvent(trackId);
      res.json({ ok: true, trackId });
    } catch (err) {
      // 게이트웨이가 꺼져 있어도 데모 자체(지도 표시)는 계속 진행돼야 하므로 500을
      // 주지 않고 그냥 "시도는 했다"는 의미로 200을 준다 - 실패 원인은 콘솔에만 남긴다.
      console.warn("[MAP EVENT] /demo/reset 처리 중 오류:", err.message);
      res.json({ ok: false, error: err.message });
    }
  });

  router.get("/trajectory/:vehicleId", async (req, res) => {
    const rows = await db.getTrajectory(req.params.vehicleId);
    res.json({ vehicleId: req.params.vehicleId, points: rows });
  });

  router.get("/vehicles/recent", async (req, res) => {
    const rows = await db.listRecentVehicles();
    res.json({ vehicles: rows });
  });

  return {
    router,
    // http.Server의 'upgrade' 이벤트를 받아서 /events 경로만 이 WebSocketServer로 넘긴다.
    attach(httpServer, wsPath = "/events") {
      httpServer.on("upgrade", (request, socket, head) => {
        const { pathname } = new URL(request.url, `http://${request.headers.host}`);
        if (pathname !== wsPath) return; // 다른 경로는 이 모듈이 관여하지 않는다
        wss.handleUpgrade(request, socket, head, (ws) => {
          wss.emit("connection", ws, request);
        });
      });
    },
  };
}

module.exports = { createMapEventsModule };