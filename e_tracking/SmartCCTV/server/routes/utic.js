/**
 * routes/utic.js
 * ------------------------------------------------------------
 * GET /api/utic/cctv/test?camId=H4642
 *
 * traffic-cameras-seoul.json에서 실제로 존재하는 CCTV(기본값: H4642 이수어린이집 앞)의
 * 위도/경도를 가져와 UTIC CCTV Open API를 호출하고, 응답을 진단해서 콘솔/응답으로 알려준다.
 *
 * - 임의의 CCTV 데이터를 새로 만들지 않는다 (web/data/traffic-cameras-seoul.json 그대로 사용).
 * - API Key는 절대 응답/로그에 포함하지 않는다.
 */

const express = require("express");
const fs = require("fs");
const path = require("path");
const { callUticCctvApi, UticConfigError } = require("../utic/uticClient");

const router = express.Router();

// server/ 기준 ../../web/data/traffic-cameras-seoul.json (프로젝트 루트/web/data/...)
const CAMERAS_JSON_PATH = path.resolve(__dirname, "../../web/data/traffic-cameras-seoul.json");

function loadTestCamera(camId) {
  const raw = fs.readFileSync(CAMERAS_JSON_PATH, "utf-8");
  const parsed = JSON.parse(raw);
  const record = (parsed.records || []).find(
    (r) => r["무인교통단속카메라관리번호"] === camId
  );
  if (!record) return null;

  return {
    camId,
    name: record["설치장소"],
    district: record["시군구명"],
    lat: parseFloat(record["위도"]),
    lng: parseFloat(record["경도"]),
  };
}

// UTIC 응답이 JSON인지 아닌지 확실히 모르므로, 우선 JSON 파싱을 시도하고
// 실패하면(XML 등) 원문 텍스트를 그대로 보존해서 사용자가 직접 확인할 수 있게 한다.
function parseResponseBody(rawText) {
  try {
    return { format: "json", data: JSON.parse(rawText) };
  } catch (e) {
    return { format: "text", data: rawText };
  }
}

// 흔히 쓰이는 공공 Open API JSON 응답 구조 후보들을 순서대로 시도해서 CCTV 배열을 찾는다.
// (UTIC의 정확한 응답 구조가 확인되면 이 목록 맨 앞에 실제 경로를 추가하면 된다)
function extractCctvItems(parsed) {
  if (parsed.format !== "json" || !parsed.data) return [];
  const d = parsed.data;
  const candidates = [d?.response?.data, d?.body?.items?.item, d?.items, d?.data, d?.response];
  for (const c of candidates) {
    if (Array.isArray(c)) return c;
    if (c && typeof c === "object") return [c];
  }
  return [];
}

function pickField(obj, ...names) {
  for (const n of names) {
    if (obj && obj[n] !== undefined && obj[n] !== null && obj[n] !== "") return obj[n];
  }
  return null;
}

function classifyHttpError(status) {
  if (status === 401 || status === 403) {
    return "API Key 또는 IP 인증 문제 가능성 (등록된 IP 대역 211.48.113.0/24에서 호출 중인지, Key가 유효한지 확인 필요)";
  }
  if (status === 400) return "요청 파라미터 문제 가능성 (파라미터명/좌표 형식이 매뉴얼과 일치하는지 확인 필요)";
  if (status === 404) return "요청 URL 문제 가능성 (엔드포인트 경로가 올바른지 확인 필요)";
  if (status >= 500) return "UTIC 서버 문제 가능성 (잠시 후 재시도 필요)";
  return null;
}

router.get("/cctv/test", async (req, res) => {
  const camId = req.query.camId || "H4642"; // 기본값: 이수어린이집 앞 (원하면 ?camId=J7878 로 이수역사거리 테스트 가능)

  let testCamera;
  try {
    testCamera = loadTestCamera(camId);
  } catch (err) {
    return res.status(500).json({ error: `traffic-cameras-seoul.json 읽기 실패: ${err.message}` });
  }

  if (!testCamera) {
    return res.status(404).json({ error: `traffic-cameras-seoul.json에서 cam_id(${camId})를 찾을 수 없습니다.` });
  }

  console.log("\n[UTIC CCTV API TEST]\n");
  console.log("검색 CCTV:");
  console.log(`- 이름: ${testCamera.name}`);
  console.log(`- cam_id: ${testCamera.camId}`);
  console.log(`- 위도: ${testCamera.lat}`);
  console.log(`- 경도: ${testCamera.lng}`);

  try {
    const result = await callUticCctvApi({ lat: testCamera.lat, lng: testCamera.lng });
    const parsed = parseResponseBody(result.rawText);
    const errorHint = !result.ok ? classifyHttpError(result.status) : null;

    console.log(result.ok ? `\n요청 성공 (HTTP ${result.status})` : `\n요청 실패 (HTTP ${result.status})`);
    if (errorHint) console.log("- 추정 원인:", errorHint);

    console.log("\nUTIC 응답 원문 (최대 2000자, 진단용):");
    const rawPreview =
      typeof parsed.data === "string" ? parsed.data : JSON.stringify(parsed.data, null, 2);
    console.log(rawPreview.slice(0, 2000));

    const items = extractCctvItems(parsed);
    const first = items[0] || null;

    const cctvId = first ? pickField(first, "cctvid", "CCTVID", "cctvId", "id") : null;
    const cctvName = first ? pickField(first, "cctvname", "CCTVName", "cctvName", "name") : null;
    const cctvUrl = first ? pickField(first, "cctvurl", "CCTVurl", "cctvUrl", "url") : null;
    const cctvFormat = first ? pickField(first, "cctvformat", "CCTVFormat", "cctvFormat", "format") : null;
    const cctvResolution = first
      ? pickField(first, "cctvresolution", "CCTVResolution", "cctvResolution", "resolution")
      : null;

    console.log("\nUTIC 응답 요약:");
    if (first) {
      console.log("- CCTV ID:", cctvId || "(필드 미확인 - 원문을 직접 확인해주세요)");
      console.log("- CCTV 이름:", cctvName || "(필드 미확인)");
      console.log("- 영상 URL 존재:", cctvUrl ? "YES" : "NO");
      console.log("- 영상 형식:", cctvFormat || "(필드 미확인)");
      console.log("- 해상도:", cctvResolution || "(필드 미확인)");
    } else {
      console.log("- 응답에서 CCTV 목록 구조를 자동으로 찾지 못했습니다. 위 원문을 직접 확인해주세요.");
    }

    res.json({
      requestSucceeded: result.ok,
      httpStatus: result.status,
      requestUrl: result.requestUrl, // 키는 마스킹된 상태
      requestParams: result.box,
      testCamera,
      errorHint,
      responseFormat: parsed.format,
      cctvCount: items.length,
      cctv: first
        ? {
            id: cctvId,
            name: cctvName,
            videoUrl: cctvUrl,
            videoUrlPresent: !!cctvUrl,
            format: cctvFormat,
            resolution: cctvResolution,
          }
        : null,
      rawResponsePreview: rawPreview.slice(0, 2000),
    });
  } catch (err) {
    if (err instanceof UticConfigError) {
      console.error("\n[UTIC CCTV API TEST] 설정 오류:", err.message);
      return res.status(500).json({ error: err.message, kind: "CONFIG_ERROR" });
    }
    console.error("\n[UTIC CCTV API TEST] 호출 중 오류:", err.message);
    res.status(502).json({ error: err.message, kind: "REQUEST_ERROR" });
  }
});

module.exports = router;
