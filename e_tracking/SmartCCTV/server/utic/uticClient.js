/**
 * uticClient.js
 * ------------------------------------------------------------
 * UTIC(도시교통정보센터) CCTV Open API를 호출하는 저수준 클라이언트.
 *
 * - API Key는 오직 process.env.UTIC_API_KEY 에서만 읽는다. 코드에 하드코딩하지 않는다.
 * - 콘솔에는 API Key를 절대 출력하지 않는다 (요청 URL도 key 부분은 마스킹해서만 출력).
 * - 실제 UTIC 엔드포인트/파라미터명은 발급 시 받은 매뉴얼에 있는 값을
 *   .env(UTIC_CCTV_API_URL 등)에 넣어야 한다. 여기 있는 기본값은 국토교통부 계열
 *   CCTV Open API에서 흔히 쓰는 관례를 따른 "추정값"이며, UTIC의 실제 스펙과
 *   다를 수 있다 (그래서 코드에 박아넣지 않고 .env로 분리해뒀다).
 */

// Node.js 18+ 내장 fetch를 사용한다 (별도 HTTP 라이브러리 의존성 추가 없음).

function buildBoundingBox(lat, lng, marginDeg = 0.003) {
  // marginDeg 0.003 ≈ 위도 기준 약 330m. "너무 넓지 않은" 테스트 영역을 위한 기본값.
  return {
    minX: (lng - marginDeg).toFixed(6),
    maxX: (lng + marginDeg).toFixed(6),
    minY: (lat - marginDeg).toFixed(6),
    maxY: (lat + marginDeg).toFixed(6),
  };
}

function maskKeyInUrl(url, keyParamName) {
  const pattern = new RegExp(`(${keyParamName}=)[^&]+`, "i");
  return url.replace(pattern, "$1***");
}

class UticConfigError extends Error {}

async function callUticCctvApi({ lat, lng }) {
  const apiKey = process.env.UTIC_API_KEY;
  if (!apiKey) {
    throw new UticConfigError(
      "UTIC_API_KEY가 설정되어 있지 않습니다. 프로젝트 루트의 .env 파일을 확인해주세요."
    );
  }

  const baseUrl = process.env.UTIC_CCTV_API_URL;
  if (!baseUrl || baseUrl.includes("REPLACE_ME")) {
    throw new UticConfigError(
      "UTIC_CCTV_API_URL이 아직 실제 엔드포인트로 설정되지 않았습니다. " +
        "UTIC에서 API Key 발급 시 함께 제공한 매뉴얼의 요청 URL을 .env에 넣어주세요."
    );
  }

  const keyParamName = process.env.UTIC_KEY_PARAM_NAME || "key";
  const typeParamValue = process.env.UTIC_TYPE_PARAM_VALUE; // 예: 'all' | 'its' | 'ex' (매뉴얼 값에 맞게 조정)
  const getType = process.env.UTIC_GETTYPE || "json";
  const box = buildBoundingBox(lat, lng);

  const params = new URLSearchParams();
  params.set(keyParamName, apiKey);
  if (typeParamValue) params.set("type", typeParamValue);
  params.set("minX", box.minX);
  params.set("maxX", box.maxX);
  params.set("minY", box.minY);
  params.set("maxY", box.maxY);
  params.set("getType", getType);

  const requestUrl = `${baseUrl}?${params.toString()}`;
  const maskedUrl = maskKeyInUrl(requestUrl, keyParamName);

  console.log("\n[UTIC API] 요청 URL (키 마스킹됨):", maskedUrl);
  console.log("[UTIC API] 요청 파라미터 (키 제외):", {
    type: typeParamValue,
    ...box,
    getType,
  });

  let response;
  try {
    response = await fetch(requestUrl, { method: "GET" });
  } catch (networkErr) {
    // DNS 실패, 타임아웃, 연결 거부 등 - HTTP 상태 코드 자체를 받지 못한 경우
    throw new Error(`네트워크 오류로 UTIC API에 연결하지 못했습니다: ${networkErr.message}`);
  }

  const rawText = await response.text();

  return {
    status: response.status,
    ok: response.ok,
    rawText,
    requestUrl: maskedUrl,
    box,
  };
}

module.exports = { callUticCctvApi, buildBoundingBox, UticConfigError };
