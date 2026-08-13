/**
 * test-its-seoul-coverage.js
 * ------------------------------------------------------------
 * 1회성 검증 스크립트. 기존 프로젝트 파일(web/*, server/.env 등)은
 * 전혀 건드리지 않는다. 완전히 독립된 파일이며, 결과가 좋으면 이 코드를
 * 참고해서 server/ 쪽에 정식으로 옮기고, 결과가 안 좋으면 이 파일만
 * 지우면 그만이다.
 *
 * 하는 일
 * ----------------------------------------------------
 * 1. ITS(국가교통정보센터) Open API(openapi.its.go.kr:9443/cctvInfo)에
 *    서울 영역(minX/maxX/minY/maxY)으로 CCTV 목록을 요청한다.
 * 2. web/data/utic-cameras-seoul.json(UTIC 서울 CCTV 303건, 읽기 전용)과
 *    좌표 근접도 + 이름 유사도로 매칭을 시도한다.
 * 3. L010263(이수역, 37.4846/126.9824) 근처에 ITS 카메라가 있는지
 *    특별히 확인한다.
 * 4. 요청하신 7개 항목을 콘솔에 명확히 출력한다.
 *
 * 주의
 * ----------------------------------------------------
 * - ITS API는 UTIC과 별개 시스템이므로 별도의 ITS API Key가 필요하다.
 *   UTIC_API_KEY(.env)는 사용하지 않는다 - 절대 여기 재사용하지 않는다.
 * - 키는 절대 코드에 하드코딩하지 말고, 실행할 때 환경변수로만 넘긴다.
 * - 이 스크립트는 fetch() 결과를 콘솔에만 출력한다. 어떤 기존 파일도
 *   수정/삭제하지 않는다.
 *
 * 실행 방법 (프로젝트 루트에서, server/node_modules를 그대로 재사용):
 *
 *   ITS_API_KEY=발급받은_ITS키 node test-its-seoul-coverage.js
 *
 * (Node.js 18+ 내장 fetch를 사용하므로 별도 설치 필요 없음.
 *  단, web/data/utic-cameras-seoul.json 경로를 읽어야 하므로
 *  프로젝트 루트에서 실행해야 한다: web/ 폴더가 같은 위치에 있어야 함)
 */

const fs = require("fs");
const path = require("path");

const ITS_ENDPOINT = "https://openapi.its.go.kr:9443/cctvInfo";
const UTIC_SEOUL_JSON = path.resolve(__dirname, "web/data/utic-cameras-seoul.json");

// 조회 영역: 환경변수로 넘기면 그 값을 쓰고, 없으면 서울 전체 범위를 기본값으로 사용한다.
// 이번처럼 좁은 영역(이수역 주변)을 테스트하려면:
//   MINX=126.978 MAXX=126.987 MINY=37.480 MAXY=37.489 ITS_API_KEY=... node test-its-seoul-coverage.js
const PARAMS = {
  minX: process.env.MINX || "126.70",
  maxX: process.env.MAXX || "127.25",
  minY: process.env.MINY || "37.40",
  maxY: process.env.MAXY || "37.75",
  cctvType: "1",
  getType: "json",
};

// 매칭 판정 기준: 좌표가 이 거리(도, 대략 150m) 이내면 "근접"으로 간주 (도 단위 빠른 필터링용)
const MATCH_THRESHOLD_DEG = 0.0015;

// 정확한 두 지점 간 거리(미터)를 구하는 haversine 공식.
// (앞서 있던 유클리드 근사 대신, "직선거리를 미터 단위로 알려달라"는 요청에 맞춰 정확하게 계산)
function haversineMeters(lat1, lng1, lat2, lng2) {
  const R = 6371000; // 지구 반지름(m)
  const toRad = (deg) => (deg * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLng = toRad(lng2 - lng1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLng / 2) ** 2;
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return R * c;
}

function haversineApproxDeg(lat1, lng1, lat2, lng2) {
  // 도 단위 빠른 1차 필터용 (150m 근접 여부만 대략 판단할 때 사용)
  return Math.sqrt((lat1 - lat2) ** 2 + (lng1 - lng2) ** 2);
}

function pickField(obj, ...names) {
  for (const n of names) {
    if (obj && obj[n] !== undefined && obj[n] !== null && obj[n] !== "") return obj[n];
  }
  return null;
}

function extractItems(json) {
  const candidates = [json?.response?.body?.items?.item, json?.response?.data, json?.items, json?.data];
  for (const c of candidates) {
    if (Array.isArray(c)) return c;
    if (c && typeof c === "object") return [c];
  }
  return [];
}

async function main() {
  const apiKey = process.env.ITS_API_KEY;
  if (!apiKey) {
    console.error("환경변수 ITS_API_KEY가 없습니다. UTIC_API_KEY와는 다른, ITS에서 발급받은 키가 필요합니다.");
    console.error("실행 예: ITS_API_KEY=발급받은_ITS키 node test-its-seoul-coverage.js");
    process.exit(1);
  }

  // 1) UTIC 서울 CCTV 303건 로드 (읽기 전용, 수정하지 않음)
  const uticRaw = fs.readFileSync(UTIC_SEOUL_JSON, "utf-8");
  const uticData = JSON.parse(uticRaw);
  const uticCameras = uticData.cameras || [];
  console.log(`[1] UTIC 서울 CCTV 로드: ${uticCameras.length}건 (web/data/utic-cameras-seoul.json)`);

  const target = uticCameras.find((c) => c.cam_id === "L010263");
  if (!target) {
    console.error("!! L010263을 utic-cameras-seoul.json에서 찾지 못했습니다. 파일이 바뀌었는지 확인이 필요합니다.");
  } else {
    console.log(`    L010263 기준 좌표: lat=${target.lat}, lng=${target.lng} (${target.name})`);
  }

  // 2) ITS API 호출 (키는 마스킹해서만 로그에 남긴다)
  const qs = new URLSearchParams({ apiKey, type: "its", ...PARAMS });
  const url = `${ITS_ENDPOINT}?${qs.toString()}`;
  const maskedUrl = url.replace(/(apiKey=)[^&]+/, "$1***");
  console.log(`\n[2] ITS API 요청 (키 마스킹): ${maskedUrl}`);

  let res;
  try {
    res = await fetch(url);
  } catch (err) {
    console.error(`\n네트워크 오류로 ITS API에 연결하지 못했습니다: ${err.message}`);
    process.exit(1);
  }

  const rawText = await res.text();
  console.log(`HTTP 상태: ${res.status} (${res.ok ? "성공" : "실패"})`);

  if (!res.ok) {
    console.log("\n응답 원문 (최대 1500자):");
    console.log(rawText.slice(0, 1500));
    console.log("\n=> HTTP 오류로 더 진행할 수 없습니다. 위 원문에서 원인을 확인해주세요.");
    return;
  }

  let json;
  try {
    json = JSON.parse(rawText);
  } catch (e) {
    console.log("\n응답이 JSON이 아닙니다. 원문 (최대 1500자):");
    console.log(rawText.slice(0, 1500));
    return;
  }

  const items = extractItems(json);

  console.log("\n========================================");
  console.log("[결과 1] 조회 영역 내 CCTV 개수:", items.length);
  console.log("========================================");

  if (items.length === 0) {
    console.log("=> ITS API가 이 영역에서 CCTV를 0건 반환했습니다.");
    console.log("=> L010263과 매칭할 대상 자체가 없습니다 -> 매칭 실패로 판단.");
    return;
  }

  console.log("\n[결과 2, 3, 5, 6] CCTV 이름 / 좌표 / cctvformat / cctvurl 존재 여부 (전체 " + items.length + "건):");
  items.forEach((it, i) => {
    console.log(`  ${i + 1}. name=${pickField(it, "cctvname", "CCTVNAME")} ` +
      `x=${pickField(it, "coordx", "COORDX")} y=${pickField(it, "coordy", "COORDY")} ` +
      `format=${pickField(it, "cctvformat", "CCTVFORMAT")} ` +
      `url=${pickField(it, "cctvurl", "CCTVURL") ? "있음" : "없음"}`);
  });

  // 3) 좌표 매칭: ITS 각 항목 vs UTIC 303건
  let matchCount = 0;
  const matchedUtic = new Set();
  items.forEach((it) => {
    const x = parseFloat(pickField(it, "coordx", "COORDX"));
    const y = parseFloat(pickField(it, "coordy", "COORDY"));
    if (!Number.isFinite(x) || !Number.isFinite(y)) return;

    uticCameras.forEach((u) => {
      if (haversineApproxDeg(y, x, u.lat, u.lng) <= MATCH_THRESHOLD_DEG) {
        matchCount += 1;
        matchedUtic.add(u.cam_id);
      }
    });
  });

  console.log("\n========================================");
  console.log(`[매칭] UTIC 303건 중 좌표상 ${MATCH_THRESHOLD_DEG}도(약 150m) 이내로 겹치는 CCTV: ${matchedUtic.size}건`);
  console.log("========================================");

  // 4) L010263(이수역) 근접 여부 특별 확인 - 반환된 모든 CCTV와의 거리를 미터 단위로 전부 나열
  console.log("\n[결과 4] L010263(이수역, 37.4846/126.9824)과의 직선거리 (전체 결과 대상, 미터 단위):");
  if (target) {
    const distances = items
      .map((it) => {
        const x = parseFloat(pickField(it, "coordx", "COORDX"));
        const y = parseFloat(pickField(it, "coordy", "COORDY"));
        if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
        return {
          name: pickField(it, "cctvname", "CCTVNAME"),
          x,
          y,
          meters: haversineMeters(target.lat, target.lng, y, x),
          format: pickField(it, "cctvformat", "CCTVFORMAT"),
          hasUrl: !!pickField(it, "cctvurl", "CCTVURL"),
        };
      })
      .filter(Boolean)
      .sort((a, b) => a.meters - b.meters);

    if (distances.length === 0) {
      console.log("  => 비교할 좌표 데이터가 없습니다.");
    } else {
      distances.forEach((d, i) => {
        console.log(
          `  ${i + 1}. ${d.name} - 약 ${d.meters.toFixed(0)}m (format=${d.format}, url=${d.hasUrl ? "있음" : "없음"})`
        );
      });
      const nearest = distances[0];
      if (nearest.meters <= 150) {
        console.log(`\n  => 매칭 성공으로 판단: 가장 가까운 CCTV(${nearest.name})가 150m 이내(${nearest.meters.toFixed(0)}m)입니다.`);
      } else {
        console.log(`\n  => 매칭 실패로 판단: 가장 가까운 CCTV(${nearest.name})도 ${nearest.meters.toFixed(0)}m 떨어져 있어 동일 CCTV로 보기 어렵습니다.`);
        console.log("     (같은 서울 영역 안에 있다는 것만으로 동일 카메라라고 판단하지 않습니다)");
      }
    }
  }

  console.log("\n========================================");
  console.log("최종 결론");
  console.log("========================================");
  if (matchedUtic.size === 0) {
    console.log("UTIC 서울 CCTV 303건 중 ITS API와 좌표가 겹치는 카메라가 0건입니다.");
    console.log("=> ITS API와 UTIC 서울 CCTV는 서로 다른 카메라 집합으로 판단됩니다. 이 API는 사용하지 않는 것을 권장합니다.");
  } else {
    console.log(`UTIC 서울 CCTV 303건 중 ${matchedUtic.size}건이 ITS API 결과와 좌표상 겹칩니다.`);
    console.log("=> 부분적으로라도 매칭이 확인됐습니다. 다음 단계로 넘어갈지 판단이 필요합니다.");
  }
}

main();