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
// [버그 수정: "새로고침할 때마다 중복 이벤트가 계속 쌓이는 문제" - 3차 수정]
// Forza DEMO는 페이지를 새로고침할 때마다(20초 뒤) 항상 같은 시나리오(DEMO-DRUNK-001)를
// 처음부터 다시 재생한다. 지금까지는 "이미 보낸 적 있으면 다시 안 보낸다"(평생 1번) 방식
// 이었는데, 실제로 원하는 동작은 그게 아니라 "새로고침할 때마다 이전 것은 지우고 항상
// 최신 1건만 DB에 남긴다"였다. 그래서 이제는:
//   1) 매번 DUI_PATTERN 이벤트를 보내기 "직전"에 b_gateway에 DELETE /api/events/by-track/{trackId}를
//      먼저 호출해서 이 데모 차량의 기존 기록을 전부 지운다.
//   2) 그 다음 항상 POST로 새 이벤트 1건을 만든다.
// 그 결과 "새로고침 → 20초 후 → DB에 정확히 1건(이전 것 삭제 + 새 것 생성)"이 매번 반복된다.
// (b_gateway/EventController에 이 DELETE endpoint를 새로 추가했다 - EventRepository/
// EventService/EventController 세 파일, deleteByTrackId 관련 부분만 추가, 기존 로직은 그대로.)
//
// 실제 UTIC 카메라 탐지(source_type="UTIC")는 "반복 재생"이 아니라 진짜 다른 시점의 실제
// 감지이므로 지우지 않는다 - 기존처럼 일정 시간(기본 5분) 쿨다운만 적용해 과도한 중복만 막는다.
const REAL_COOLDOWN_MS = 5 * 60 * 1000; // source_type === "UTIC"(실제 탐지)용 - 5분
const lastForwarded = new Map(); // 실제(UTIC) 탐지 전용 쿨다운 타임스탬프

// [버그 수정: "이벤트가 실제 시각보다 9시간 전(과거)으로 뜨는 문제"]
// 예전엔 new Date(...).toISOString()을 그대로 썼다. toISOString()은 항상 UTC 기준
// 문자열을 돌려주는데(예: 15:55 KST → "...T06:55:...Z"), b_gateway의 EventCreateRequest는
// 타임존이 없는 LocalDateTime이라 "Z"만 잘라낸 문자열을 그대로(=UTC 06:55을 로컬 시각인
// 것처럼) 저장한다. 그래서 대시보드에 실제 발생 시각보다 9시간(KST=UTC+9) 이른, 마치
// 예전에 있었던 일처럼 보이는 이벤트가 떴다 - 신규 이벤트가 리스트에 "뒤늦게" 나타나는
// 게 아니라, 정상적으로 즉시 들어왔는데 시각 표시만 9시간 어긋나 있었던 것이다.
//
// 한국은 서머타임이 없어 항상 UTC+9로 고정이므로, UTC 인스턴트에 9시간을 더한 뒤
// 그 결과를 "UTC인 것처럼" 포맷하면 KST 벽시계 시각과 정확히 같은 문자열이 나온다.
function toKstLocalDateTimeString(date) {
  const kstShifted = new Date(date.getTime() + 9 * 60 * 60 * 1000);
  return kstShifted.toISOString().slice(0, 23); // "Z" 제거 - LocalDateTime이 그대로 KST 벽시계 값으로 받아들인다
}

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
    occurredAt: toKstLocalDateTimeString(new Date((mapEvent.timestamp || Date.now() / 1000) * 1000)),
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

// b_gateway에 새로 추가한 DELETE /api/events/by-track/{trackId}를 호출한다.
// 실패해도(엔드포인트가 아직 없거나 게이트웨이가 꺼져 있어도) 조용히 넘어간다 - 못 지웠다고
// 새 이벤트 전송까지 막으면 안 되고, 최악의 경우여도 "예전처럼 중복이 남는" 정도로 그친다.
async function deleteExistingDemoEvent(trackId) {
  try {
    const res = await fetch(`${GATEWAY_URL}/api/events/by-track/${encodeURIComponent(trackId)}`, {
      method: "DELETE",
      headers: { "X-API-Key": GATEWAY_API_KEY },
    });
    if (!res.ok) {
      console.warn(`[GATEWAY] 기존 데모 이벤트 삭제 실패 (HTTP ${res.status}) - 그대로 진행합니다.`);
      return;
    }
    const body = await res.json().catch(() => null);
    if (body && body.deletedCount > 0) {
      console.log(`[GATEWAY] ${trackId}의 기존 이벤트 ${body.deletedCount}건 삭제 후 새로 전송합니다.`);
    }
  } catch (err) {
    console.warn("[GATEWAY] 기존 데모 이벤트 삭제 중 오류(그대로 진행):", err.message);
  }
}

async function forwardToGateway(mapEvent) {
  const key = mapEvent.global_vehicle_id || mapEvent.source_id;
  const isDemo = mapEvent.source_type === "DEMO";

  if (isDemo) {
    // 새 이벤트를 보내기 전에 이 차량의 기존 기록을 먼저 지운다 - "새로고침마다 1건만" 유지.
    await deleteExistingDemoEvent(key);
  } else {
    // 실제 UTIC 탐지는 시간 기반 쿨다운만 적용 - 같은 차량이 나중에 다시 탐지되면 보내야 함.
    const now = Date.now();
    const last = lastForwarded.get(key) || 0;
    if (now - last < REAL_COOLDOWN_MS) return false; // 쿨다운 중 - 조용히 스킵
  }

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
    if (!isDemo) {
      lastForwarded.set(key, Date.now());
    }
    return true;
  } catch (err) {
    console.warn("[GATEWAY] 전송 실패:", err.message);
    return false;
  }
}

module.exports = { forwardToGateway, deleteExistingDemoEvent };