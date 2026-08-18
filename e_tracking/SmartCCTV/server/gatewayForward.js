/**
 * gatewayForward.js
 * ------------------------------------------------------------
 * 이 모듈이 감지한 이상운전 이벤트를 b_gateway(팀 공통 이벤트 파이프라인)로도
 * 전달한다. 실패해도 지도 표시(WebSocket)에는 영향 없다.
 *
 * eventType은 팀 공통 규격의 DUI_PATTERN을 사용한다.
 * 계속 이어지는 프레임마다 다 보내면 event 테이블이 도배되므로, 차량(global_vehicle_id)당
 * 쿨다운을 둬서 일정 간격으로만 전송한다 (지도용 PostGIS 저장은 이 쿨다운과 무관하게
 * db.js에서 매 프레임 다 저장 - 경로를 매끄럽게 그리려면 그쪽은 촘촘해야 함).
 */

const GATEWAY_URL = process.env.GATEWAY_URL || "http://localhost:8080";
const GATEWAY_API_KEY = process.env.GATEWAY_API_KEY || "omecca-dev-key-2026";
const FORWARD_COOLDOWN_MS = 30_000;

const lastForwarded = new Map();

function toGatewayPayload(mapEvent) {
  return {
    camId: mapEvent.source_id,
    trackId: mapEvent.global_vehicle_id || null,
    eventType: "DUI_PATTERN",
    objectClass: "VEHICLE",
    bbox: mapEvent.video_position_px
      ? [mapEvent.video_position_px.x, mapEvent.video_position_px.y, 0, 0]
      : [0, 0, 0, 0],
    confidence: mapEvent.confidence ?? 0.7,
    occurredAt: new Date((mapEvent.timestamp || Date.now() / 1000) * 1000).toISOString().slice(0, 23),
    location: { lat: mapEvent.latitude, lng: mapEvent.longitude },
    isRegisteredTarget: false,
    targetId: null,
    roiId: null,
    meta: {
      source: "e_tracking/SmartCCTV",
      sourceType: mapEvent.source_type,
      reason: mapEvent.reason || null,
      locationName: mapEvent.location_name || null,
      plate: mapEvent.plate || null,
    },
    frameRefBefore: null,
    frameRefAfter: null,
  };
}

async function forwardToGateway(mapEvent) {
  const key = mapEvent.global_vehicle_id || mapEvent.source_id;
  const now = Date.now();
  const last = lastForwarded.get(key) || 0;
  if (now - last < FORWARD_COOLDOWN_MS) return false; // 쿨다운 중 - 조용히 스킵

  try {
    const res = await fetch(`${GATEWAY_URL}/api/events`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-API-Key": GATEWAY_API_KEY },
      body: JSON.stringify(toGatewayPayload(mapEvent)),
    });
    if (!res.ok) {
      console.warn(`[GATEWAY] 전송 실패 (${res.status}): ${await res.text().catch(() => "")}`);
      return false;
    }
    lastForwarded.set(key, now);
    return true;
  } catch (err) {
    console.warn("[GATEWAY] 전송 실패:", err.message);
    return false;
  }
}

module.exports = { forwardToGateway };