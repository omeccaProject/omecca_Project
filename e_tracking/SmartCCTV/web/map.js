/* ==================================================================
   AI Smart CCTV · GIS 관제 시스템 - map.js
   ------------------------------------------------------------------
   구조 개요
   1) 설정 / 헬퍼 함수
   2) MapManager           - 지도 인스턴스, 베이스맵 전환, focus(zoom)
   3) PopupManager         - 추적 차량 상세 팝업 HTML 생성
   4) VideoManager         - 우측 실시간 CCTV 영상 패널 (mp4 재생 + 정보 오버레이)
   4B) VideoModalManager   - CCTV 영상 확대(Modal) - video-frame을 그대로 옮겨 재생 상태를 유지
   5) TrafficCameraManager - 공공데이터 무인교통단속카메라 (지도에 표시되는 유일한 카메라)
   5B) SearchManager       - 주소/장소명으로 CCTV를 검색하는 좌상단 검색 패널
   5C) VideoSourceRegistry - UTIC 카메라의 "영상 공급원" 레지스트리 (메타데이터와 분리)
   5D) UticCameraManager   - 서울 UTIC(도시교통정보센터) 실시간 CCTV (별도 데이터 소스)
   6) RouteManager         - AI 이벤트 발생 시에만 나타나는 차량 이동 경로(Line)
   7) VehicleManager       - AI 이벤트 발생 시에만 생성되는 추적 차량 마커
   8) UIManager            - 헤더 통계, 실시간 시계, 다크/라이트 테마
   9) ToastManager         - 발표용 "AI 이벤트 감지" 토스트 알림 (3초 후 자동 소멸)
   10) EventManager        - AI 이벤트의 유일한 진입점 (①~⑧ 순서로 자동 처리)
   11) AiEventListener     - Python(AI) 이벤트를 감지해 EventManager를 자동 호출
   12) 초기 실행

   ------------------------------------------------------------------
   이 시스템은 더 이상 고정된 데모용 AI CCTV(이수/사당/서초)나 상시 존재하는
   데모 차량을 사용하지 않는다. 지도에는 공공데이터 무인교통단속카메라만
   항상 표시되며, "차량"과 "이동 경로"는 AI 이상운전 이벤트가 발생했을 때만
   그 시점에 생성된다.

   ------------------------------------------------------------------
   향후 확장 방법 (Python OpenCV → event.json / WebSocket 연동 시)
   ------------------------------------------------------------------
   실시간 이벤트가 들어오는 지점에서 EventManager.triggerAiEvent() 하나만
   호출하면, 아래 과정이 전부 자동으로 처리된다.

     ① 차량 생성        ② 이동 경로(Line) 표시        ③ 이벤트 위치(카메라) 강조
     ④ 우측 영상 자동 전환  ⑤ AI 이벤트 패널 추가

     // record 는 공공데이터 카메라 원본 레코드 (위도/경도/설치장소 등을 포함)
     // trackId를 넘기면 EventManager가 활성 이벤트(중복 방지/자동 해제)를 관리한다
     eventManager.triggerAiEvent(record, {
       time: '18:25:12',
       trackId: '3',              // anomaly_detection.py의 track_id
       plate: '12가3456',          // 없으면 null (Track ID로 대체 표시됨)
       type: '이상운전 감지',
       reason: '지그재그 주행',
       confidence: null,          // 규칙 기반 판정은 수치형 신뢰도가 없을 수 있음
     });

   예) WebSocket 예시
     const socket = new WebSocket('ws://localhost:8000/events');
     socket.onmessage = (msg) => {
       const data = JSON.parse(msg.data); // { cam_id, track_id, plate, event_type, reason, confidence, time }
       const record = uticCameraManager.getRecordById(data.cam_id);
       if (record) {
         eventManager.triggerAiEvent(record, {
           time: data.time,
           trackId: data.track_id,
           plate: data.plate,
           type: data.event_type,
           reason: data.reason,
           confidence: data.confidence,
         });
       }
     };

   실시간 영상 스트림으로 바꾸려면 VideoManager는 이미 <video> 태그 기반이므로
   getVideoOverride()가 TEST_VIDEO_OVERRIDES 대신 카메라별 스트림 URL을 반환하도록만 바꾸면 된다.
================================================================== */

/* ==================================================================
   1) 설정 / 헬퍼 함수
================================================================== */

const CONFIG = {
  SEOUL_CENTER: { lat: 37.5665, lng: 126.978 }, // 서울시청 - 특정 데모 지점이 아닌 서울 전체를 보여주기 위한 중심점
  DEFAULT_ZOOM: 11,
  FOCUS_ZOOM: 17, // 카메라 선택 시 확대할 줌 레벨
  DEFAULT_BASEMAP: "dark",
  DEFAULT_THEME: "dark",
  // realtime_anomaly.py가 실제로 처리하는 실제 UTIC CCTV 4개 (이수역/사당역/경남아파트/까치고개).
  // 그 외 cam_id로 들어오는 UTIC 이벤트는 무시한다 (Forza 데모는 아래 DEMO_CAMERA_ID_MAP으로 별도 처리).
  ANOMALY_ENABLED_CAM_IDS: ["L010263", "L010117", "L010018", "L010055"],
  // Forza 데모 소스(A/B/C/D) → 그 지점의 위경도를 빌려올 실제 UTIC 카메라 cam_id.
  // (realtime_anomaly.py의 DEMO_SOURCES 주석과 동일한 근거: web/data/utic-cameras-seoul.json에서
  //  "보라매역/장승배기/상도/한강대교남단" 이름을 가진 실제 레코드를 찾아 좌표만 재사용한 것 -
  //  이 카메라들의 실시간 HLS 영상으로 전환하지는 않는다. EventManager.triggerDemoEvent() 참고.)
  DEMO_CAMERA_ID_MAP: {
    A: "L010111", // 보라매역
    B: "L010271", // 장승배기
    C: "L010128", // 상도
    D: "L010481", // 한강대교남단
  },
  // A→B→C→D 전체에서 "같은 차량"으로 취급하는 데모 전용 전역 ID. realtime_anomaly.py의
  // DEMO_VEHICLE_ID와 반드시 동일한 문자열이어야 한다 (export_forza_track_logs.py가
  // 만드는 track log의 episode에는 이 값이 들어있지 않으므로, 여기서 직접 지정한다).
  DEMO_VEHICLE_ID: "DEMO-DRUNK-001",
  // server/server.js가 떠 있는 origin. Forza mp4는 web/ 바깥(프로젝트 루트 /videos)에
  // 있어서 web/index.html이 어디서 서빙되든 상관없이 항상 이 서버가 정적으로 제공한다
  // (server.js의 app.use("/videos", express.static(...)) 참고). server.js 포트를
  // 바꿨다면 여기도 같이 바꿔야 한다.
  MAP_SERVER_ORIGIN: "http://localhost:4000",
  // ---- 웹사이트 CCTV 클릭 → Forza 영상 재생 + 사전 분석 오버레이 ----
  // key: 그 지점의 좌표를 빌려온 "실제" UTIC cam_id (DEMO_CAMERA_ID_MAP의 값과 동일).
  // 이 cam_id를 가진 마커를 클릭하면 실제 HLS 대신 이 Forza mp4가 재생되고,
  // export_forza_track_logs.py가 미리 만들어 둔 trackLogUrl(JSON)을 불러와
  // 영상 재생 시점에 맞는 박스를 그린다(VideoManager._attachBoxOverlay 참고).
  // videoSourceRegistry에 이 4개 cam_id의 실제 HLS가 등록되어 있지 않으므로
  // (web/data/utic-video-sources.json에는 L010263/L010117/L010018/L010055만 있음)
  // 실제 라이브 영상과 충돌하지 않는다.
  FORZA_DEMO_SOURCES: {
    L010111: { demoId: "A", videoUrl: "http://localhost:4000/videos/forza_A.mp4", trackLogUrl: "data/forza-track-log-L010111.json" },
    L010271: { demoId: "B", videoUrl: "http://localhost:4000/videos/forza_B.mp4", trackLogUrl: "data/forza-track-log-L010271.json" },
    L010128: { demoId: "C", videoUrl: "http://localhost:4000/videos/forza_C.mp4", trackLogUrl: "data/forza-track-log-L010128.json" },
    L010481: { demoId: "D", videoUrl: "http://localhost:4000/videos/forza_D.mp4", trackLogUrl: "data/forza-track-log-L010481.json" },
  },
  // 이상운전 이벤트 수신 후 "활성 상태"(이상 차량 강조 + 통계 반영)를 유지할 시간(ms).
  // Python이 "해제" 신호를 보내지 않으므로, 일정 시간 뒤 GIS가 스스로 강조를 해제한다.
  ANOMALY_ACTIVE_MS: 6000,
  // [신규] 사이트 시작 후 정상 관제로 보이는 시간(ms). 이 시간 동안은 Forza DEMO의 가상
  // 재생 시계 자체가 시작되지 않으므로(ForzaBackgroundAnalyzer._tick 참고) 아무 이벤트도
  // 발생할 수 없다 - JSON은 페이지 로딩 시 미리 fetch해 두지만(요구사항: "JSON 로딩"과
  // "이벤트 발생"은 별개), replay clock의 0초 시점 자체를 이 값만큼 늦춰서 "23.38초를
  // 하드코딩"하지 않고 "20초 지연 + track log의 실제 anomaly timestamp"로 계산되게 한다.
  FORZA_DEMO_START_DELAY_MS: 20000,
  // server/server.js(WebSocket)로 실시간 AI 이벤트를 받는 경로. 지금은 실제 UTIC CCTV 4개
  // (realtime_anomaly.py를 계속 띄워두는 경우)에만 쓰인다 - Forza 데모는 더 이상 이 경로를
  // 쓰지 않는다(사전 분석 + 클릭 재생 방식으로 전환됨. 위 FORZA_DEMO_SOURCES 참고).
  // 서버가 꺼져 있으면 AiWebSocketListener가 자동 재연결을 계속 시도할 뿐,
  // 지도의 나머지 기능(카메라 목록/검색/영상 재생 등)에는 영향이 없다.
  MAP_EVENTS_WS_URL: "ws://localhost:4000/events",
};

// 영상이 연결된 CCTV만 여기에 등록한다. (key: 무인교통단속카메라관리번호 cam_id)
// index.html이 web/ 폴더 안에 있고, 실제 mp4는 프로젝트 루트의 /videos 에 있으므로
// web/index.html 기준 상대경로인 "../videos/..."로 지정해야 한다.
//
// [비활성화됨] 실제 UTIC HLS 영상 연결이 확인되어(web/data/utic-video-sources.json),
// traffic.mp4/0805.mp4를 쓰던 테스트 영상 연결은 더 이상 사용하지 않는다.
// TrafficCameraManager 클래스 자체와 J7878/H4642 관련 다른 코드는 삭제하지 않고
// 그대로 남겨뒀다 (필요하면 이 객체에 다시 항목을 채우는 것만으로 복구 가능).
const TEST_VIDEO_OVERRIDES = {};

const BASEMAPS = {
  osm: {
    label: "일반지도",
    url: "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    options: { maxZoom: 19, attribution: "&copy; OpenStreetMap contributors" },
  },
  satellite: {
    label: "위성지도",
    url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    options: { maxZoom: 19, attribution: "Tiles &copy; Esri &mdash; Esri, Maxar, Earthstar Geographics" },
  },
  dark: {
    label: "다크맵",
    url: "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
    options: { maxZoom: 20, subdomains: "abcd", attribution: "&copy; OpenStreetMap contributors &copy; CARTO" },
  },
  light: {
    label: "라이트맵",
    url: "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
    options: { maxZoom: 20, subdomains: "abcd", attribution: "&copy; OpenStreetMap contributors &copy; CARTO" },
  },
};

// 문자열을 정수 해시로 변환 (이동 경로 모양을 카메라별로 다르게 만드는 데만 사용 - 영상 배정과는 무관)
function hashString(str) {
  let h = 0;
  for (let i = 0; i < str.length; i += 1) {
    h = (h << 5) - h + str.charCodeAt(i);
    h |= 0;
  }
  return h;
}

// cam_id가 TEST_VIDEO_OVERRIDES에 등록되어 있으면 해당 오버라이드 객체({videoUrl, purpose})를,
// 없으면 null을 반환한다. (순환 배정 없음 - cam_id 기준 고정 매핑만 사용)
function getVideoOverride(record) {
  const camId = String(record["무인교통단속카메라관리번호"] || "");
  return TEST_VIDEO_OVERRIDES[camId] || null;
}

// 공공데이터 원본 레코드를 화면(영상 패널/팝업/이벤트로그)에서 공통으로 쓰는 형태로 변환
function buildCameraViewModel(record) {
  const location = record["설치장소"] || "설치 위치 정보 없음";
  const override = getVideoOverride(record);

  return {
    id: record["무인교통단속카메라관리번호"],
    name: `${location} CCTV`,
    location,
    district: record["시군구명"] || "-",
    speedLimit: record["제한속도"] ? `${record["제한속도"]}km/h` : "-",
    sourceLabel: "공공데이터 단속카메라",
    lat: parseFloat(record["위도"]),
    lng: parseFloat(record["경도"]),
    videoUrl: override ? override.videoUrl : null,
    purpose: override ? override.purpose : null,
    record,
  };
}

// UTIC 카메라 메타데이터(utic-cameras-seoul.json) + 영상 공급원 레지스트리(videoSourceRegistry, 있으면)를
// VideoManager가 이해하는 공통 viewModel 형태로 합친다. 카메라 "위치 정보"와 "영상 공급원"이
// 완전히 분리된 데이터라는 게 핵심이다 - 영상 공급원이 없으면 videoUrl은 그냥 null이 되고,
// VideoManager는 기존 로직 그대로 "영상 연결 예정" 상태를 보여준다 (VideoManager 자체는 수정 불필요).
// 두 좌표(위경도) 사이의 실제 거리를 미터 단위로 계산한다 (Haversine 공식).
// RouteManager.getRoadSegment()가 돌려주는 도로 좌표열의 구간별 길이를 구해서,
// VehicleManager가 각 구간에 애니메이션 시간을 비례 배분하는 데 쓴다.
function haversineMeters([lat1, lng1], [lat2, lng2]) {
  const R = 6371000;
  const toRad = (d) => (d * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLng = toRad(lng2 - lng1);
  const a =
    Math.sin(dLat / 2) ** 2 + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(Math.min(1, a)));
}

// 두 좌표 사이의 진행 방위각(0~360도, 정북 기준 시계방향)을 계산한다.
// RouteManager.getRoadSegment()가 OSRM에 "대략 이 방향으로 가는 길을 찾아달라"는
// 힌트(bearings 파라미터)를 줄 때 사용한다 - 교차로 U턴 문제의 원인 중 하나가
// "출발/도착 방향을 고려하지 않아서 반대 방향 도로에 스냅되는 것"이었기 때문이다.
function computeBearingDeg([lat1, lng1], [lat2, lng2]) {
  const toRad = (d) => (d * Math.PI) / 180;
  const toDeg = (r) => (r * 180) / Math.PI;
  const y = Math.sin(toRad(lng2 - lng1)) * Math.cos(toRad(lat2));
  const x =
    Math.cos(toRad(lat1)) * Math.sin(toRad(lat2)) -
    Math.sin(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.cos(toRad(lng2 - lng1));
  return Math.round((toDeg(Math.atan2(y, x)) + 360) % 360);
}

/* ------------------------------------------------------------------
   stripStartUTurn() - 경로 시작점 부근의 "U턴(되돌아오는 루프)" 구간을 제거한다.
   -----------------------------------------------------------------
   [버그 수정: "A 시작점 U자 경로"] OSRM의 bearings 힌트(±60도)만으로는 출발점 바로
   옆 도로가 반대 차선/역방향 도로에 스냅되는 경우를 완전히 막지 못했다 - 예를 들어
   보라매역 A에서 "아래로 내려갔다가 다시 시작점 근처로 돌아온 뒤에야 B 방향으로
   출발하는" 유효한 도로 경로가 존재하면, bearings 힌트가 있어도 OSRM이 그 경로를
   고를 수 있다.

   여기서는 순수 기하학적으로 후처리한다: 경로 시작점 부근(최대 300m 이내)에서
   "시작점으로부터 충분히 멀어진 적이 있다가(leftStart), 다시 시작점 가까이로
   돌아오는" 지점을 찾는다 - 이게 전형적인 "내려갔다 올라오는 루프"의 좌표 패턴이다.
   그런 지점이 있으면 그 지점까지의 좌표를 통째로 건너뛰고 시작점에서 바로 그
   지점 이후로 잇는다. 정상적으로 곧장 멀어지기만 하는 경로는 "다시 가까워짐"이
   없으므로 이 로직에 걸리지 않는다.
------------------------------------------------------------------- */
function stripStartUTurn(pathPoints) {
  if (!pathPoints || pathPoints.length < 4) return pathPoints;

  const start = pathPoints[0];
  const SEARCH_LIMIT_METERS = 300; // 이 거리를 넘어서는 지점은 "시작점 U턴"으로 보지 않는다
  const LEFT_START_METERS = 80; // 이만큼 멀어진 적이 있어야 "그 뒤에 돌아옴"이 의미를 가진다
  const NEAR_START_METERS = 40; // 이 거리 이내로 돌아오면 "시작점 근처로 되돌아왔다"로 판단

  let cumDist = 0;
  let leftStart = false;
  let loopBackIndex = -1;

  for (let i = 1; i < pathPoints.length; i++) {
    cumDist += haversineMeters(pathPoints[i - 1], pathPoints[i]);
    if (cumDist > SEARCH_LIMIT_METERS) break;

    const distFromStart = haversineMeters(start, pathPoints[i]);
    if (distFromStart > LEFT_START_METERS) {
      leftStart = true;
    } else if (leftStart && distFromStart <= NEAR_START_METERS) {
      loopBackIndex = i; // 멀어졌다가 다시 시작점 근처로 돌아온 지점(더 뒤에 또 있으면 갱신)
    }
  }

  if (loopBackIndex > 0) {
    console.log(
      `[ROUTE] 시작점 부근 U턴(되돌아오는 루프) 감지 - 앞 좌표 ${loopBackIndex}개를 건너뛰고 바로 정방향 구간부터 잇습니다.`
    );
    return [start, ...pathPoints.slice(loopBackIndex + 1)];
  }

  return pathPoints;
}

function buildUticCameraViewModel(record, videoSourceRegistry) {
  const source = videoSourceRegistry ? videoSourceRegistry.getSource(record.cam_id) : null;

  const viewModel = {
    id: record.cam_id,
    name: `${record.name || "이름 정보 없음"} CCTV`,
    location: record.name || "이름 정보 없음",
    district: record.center_name || "-",
    speedLimit: "-", // UTIC 메타데이터에는 제한속도 정보가 없음
    sourceLabel: source && source.source_type ? source.source_type : "UTIC 실시간 CCTV",
    lat: record.lat,
    lng: record.lng,
    videoUrl: source ? source.video_url : null,
    videoFormat: source ? source.video_format : null,
    purpose: source ? "UTIC_LIVE" : null,
    record,
  };

  // ---- Forza 데모 오버라이드 ----
  // 이 cam_id가 CONFIG.FORZA_DEMO_SOURCES에 있으면(보라매역/장승배기/상도/한강대교남단),
  // 실제 HLS 대신 그 지점에 매핑된 Forza mp4로 재생 소스를 바꾼다. 위 4곳은
  // web/data/utic-video-sources.json에 실제 영상 공급원이 등록되어 있지 않으므로
  // (source === null) 여기서 덮어써도 실제 라이브 카메라와 절대 충돌하지 않는다.
  const demoSource = CONFIG.FORZA_DEMO_SOURCES[record.cam_id];
  if (demoSource) {
    viewModel.videoUrl = demoSource.videoUrl;
    viewModel.videoFormat = "MP4";
    viewModel.purpose = "FORZA_DEMO";
    viewModel.demoId = demoSource.demoId;
    viewModel.trackLogUrl = demoSource.trackLogUrl;
    viewModel.sourceLabel = "발표용 데모(Forza)";
  }

  return viewModel;
}

// AI 이벤트 발생 시 카메라 지점까지 진입하는 짧은 가상 이동 경로를 생성한다.
// (실 GPS 이력이 없는 데모이므로, 카메라 id를 시드로 매번 같은 모양의 경로가 나오도록 결정론적으로 생성)
function buildApproachPath(lat, lng, seed) {
  const angle = (Math.abs(hashString(String(seed))) % 360) * (Math.PI / 180);
  const dist = 0.006; // 대략 600~700m
  const start = [lat - Math.cos(angle) * dist, lng - Math.sin(angle) * dist];
  const mid = [lat - Math.cos(angle) * dist * 0.45, lng - Math.sin(angle) * dist * 0.45];
  return [start, mid, [lat, lng]];
}

/* ==================================================================
   2) MapManager - 지도 인스턴스 / 베이스맵 전환 / 카메라 focus
================================================================== */
class MapManager {
  constructor(containerId) {
    this.map = L.map(containerId, { zoomControl: true, attributionControl: true }).setView(
      [CONFIG.SEOUL_CENTER.lat, CONFIG.SEOUL_CENTER.lng],
      CONFIG.DEFAULT_ZOOM
    );

    this.baseLayers = {};
    Object.keys(BASEMAPS).forEach((key) => {
      const def = BASEMAPS[key];
      this.baseLayers[key] = L.tileLayer(def.url, def.options);
    });
    this.currentBaseKey = null;
    this._buttons = {};

    this._renderBaseMapControl();
    this.switchBaseMap(CONFIG.DEFAULT_BASEMAP);

    setTimeout(() => this.map.invalidateSize(), 100);
  }

  _renderBaseMapControl() {
    const self = this;
    const ControlClass = L.Control.extend({
      options: { position: "topright" },
      onAdd() {
        const container = L.DomUtil.create("div", "basemap-control");
        L.DomEvent.disableClickPropagation(container);

        Object.keys(BASEMAPS).forEach((key) => {
          const btn = L.DomUtil.create("button", "basemap-control__btn", container);
          btn.type = "button";
          btn.textContent = BASEMAPS[key].label;
          L.DomEvent.on(btn, "click", () => self.switchBaseMap(key));
          self._buttons[key] = btn;
        });

        return container;
      },
    });

    new ControlClass().addTo(this.map);
  }

  switchBaseMap(key) {
    if (!BASEMAPS[key] || key === this.currentBaseKey) return;
    if (this.currentBaseKey) this.map.removeLayer(this.baseLayers[this.currentBaseKey]);
    this.baseLayers[key].addTo(this.map);
    this.currentBaseKey = key;

    Object.keys(this._buttons).forEach((k) => {
      this._buttons[k].classList.toggle("is-active", k === key);
    });
  }

  focus(lat, lng, zoom = CONFIG.FOCUS_ZOOM) {
    this.map.flyTo([lat, lng], zoom, { duration: 0.6 });
  }

  getMap() {
    return this.map;
  }
}

/* ==================================================================
   3) PopupManager - 추적 차량 상세 팝업 HTML 생성
   -------------------------------------------------------------
   카메라 팝업은 TrafficCameraManager가 자체적으로 만들기 때문에,
   여기서는 AI 이벤트 발생 시에만 등장하는 "추적 차량" 팝업만 담당한다.
================================================== */
class PopupManager {
  buildVehiclePopup(state) {
    const statusClass = state.severity === "alert" ? "cctv-popup__value--status-alert" : "";
    const plateDisplay = state.plate || "-"; // 번호판 인식 결과가 없는 경우(예: 이상운전 AI 이벤트) 값을 지어내지 않는다

    const confidenceBlock =
      state.confidence != null
        ? `
          <span class="cctv-popup__label">AI 신뢰도</span>
          <span class="cctv-popup__value">${state.confidence}%</span>
          <div class="cctv-popup__confidence">
            <div class="cctv-popup__confidence-track">
              <div class="cctv-popup__confidence-fill" style="width:${state.confidence}%"></div>
            </div>
          </div>
        `
        : "";

    return `
      <div class="cctv-popup">
        <div class="cctv-popup__header">
          <div class="cctv-popup__title">
            <span class="cctv-popup__code">TRACK ${state.trackId}</span>
            <span class="cctv-popup__name">🚗 추적 차량</span>
          </div>
        </div>
        <div class="cctv-popup__body">
          <span class="cctv-popup__label">번호판</span>
          <span class="cctv-popup__value cctv-popup__value--plate">${plateDisplay}</span>

          <span class="cctv-popup__label">Track ID</span>
          <span class="cctv-popup__value">${state.trackId}</span>

          <span class="cctv-popup__label">현재 상태</span>
          <span class="cctv-popup__value ${statusClass}">${state.statusIcon} ${state.statusLabel}</span>

          <span class="cctv-popup__label">원인</span>
          <span class="cctv-popup__value">${state.reason}</span>

          <span class="cctv-popup__label">현재 위치</span>
          <span class="cctv-popup__value">${state.locationName}</span>

          ${confidenceBlock}

          <span class="cctv-popup__label">감지 시간</span>
          <span class="cctv-popup__value">${state.time}</span>

          <button type="button" class="popup-btn" onclick="window.__appSelectCamera && window.__appSelectCamera('${state.currentCameraId}')">
            📹 CCTV 영상 보기
          </button>
        </div>
      </div>
    `;
  }
}

/* ==================================================================
   4) VideoManager - 우측 실시간 CCTV 영상 패널
   -------------------------------------------------------------
   프로젝트 내부 /videos 폴더의 mp4 파일을 muted + loop + autoplay로 재생하고,
   영상 위에는 선택된 카메라 정보를 반투명 오버레이로 표시한다.

   purpose === "ANOMALY_DETECTION_TEST"인 카메라(H4642)를 선택하면,
   export_track_log.py가 사전에 분석해 둔 data/anomaly-track-log.json을 불러와
   영상이 재생되는 현재 시점(video.currentTime)에 맞는 차량 박스를 canvas에
   실시간으로 그린다. Python을 그때그때 실행할 필요 없이, 영상 자체가
   "재생되는 동안 분석 결과가 함께 보이는" 것처럼 동작한다.
================================================== */
class VideoManager {
  constructor() {
    this.frameEl = document.getElementById("video-frame");
    this.videoEl = document.getElementById("cctv-video");
    this.emptyEl = document.getElementById("video-empty");
    this.errorEl = document.getElementById("video-error");
    this.overlayEl = document.getElementById("video-overlay");
    this.titleEl = document.getElementById("video-overlay-title");
    this.metaEl = document.getElementById("video-overlay-meta");
    this.aiBadgeEl = document.getElementById("video-ai-badge");
    this.canvasEl = document.getElementById("video-overlay-canvas");
    this.canvasCtx = this.canvasEl.getContext("2d");
    this.currentId = null;
    this.currentCamId = null;
    this.hls = null; // hls.js 인스턴스 (HLS(.m3u8) 재생 시에만 생성, cam 전환 시 정리)

    // AI 박스 오버레이 상태
    this.trackLogCache = null; // 지금 활성화된(재생 중인) 카메라의 track log - _renderBoxOverlay/_checkAnomalyEpisodes가 참조
    this.trackLogCacheByCamId = new Map(); // camId -> track log JSON (한 번 fetch한 뒤로는 재사용 - H4642/Forza A~D 공용)
    this.boxOverlayActive = false;
    this.boxOverlayRafId = null;
    // "영상 1회 재생 = 하나의 분석 세션"을 표현하기 위한 상태.
    // sessionId는 오버레이가 붙는 카메라가 선택될 때마다(= _attachBoxOverlay가 새로 호출될 때마다) 1씩 증가한다.
    // processedEpisodeKeys는 "지금 세션에서 이미 이벤트를 발생시킨 episode"를 기억해서,
    // 같은 세션 안에서 영상이 loop로 반복 재생되어도 동일 episode가 중복으로 이벤트를 만들지 않게 막는다.
    // (다른 CCTV로 이동했다가 다시 같은 카메라를 선택하면 새로운 세션이 되어 Set이 초기화되고,
    //  이상운전 이벤트가 다시 발생할 수 있다 - 요구사항. 이 "세션당 한 번" 정책 덕분에
    //  같은 이상운전 에피소드가 반복적으로 이벤트를 만들어 이벤트 카드가 깜박이는 문제가 생기지 않는다.)
    this.sessionId = 0;
    this.processedEpisodeKeys = new Set();
    this._prevOverlayTime = null; // loop 감지(currentTime이 되돌아가는지 확인)용 직전 재생 시각
    // AI가 에피소드를 새로 지나갈 때마다 호출됨. init 블록에서 EventManager와 연결한다.
    // (episode, camId, sessionId) => void
    this.onAnomalyEpisode = null;

    this.videoEl.addEventListener("error", () => this._handleVideoError());
    this.videoEl.addEventListener("loadeddata", () => this._hideError());
  }

  // options.immediate = true 이면 fade 없이 즉시 전환 (초기 로드용)
  switchTo(viewModel, options = {}) {
    if (!viewModel || viewModel.id === this.currentId) return;
    const { immediate = false } = options;

    const apply = () => {
      this.currentId = viewModel.id;

      if (viewModel.videoUrl) {
        // 영상이 연결된 카메라 - video src를 설정하고 재생
        this.emptyEl.style.display = "none";
        this.overlayEl.style.display = "flex";
        this.titleEl.textContent = viewModel.location;
        // 영상 하단 메타 텍스트("제공기관 · 제한속도 · 출처") 줄은 요청에 따라 표시하지 않는다.
        this.metaEl.textContent = "";
        this.metaEl.style.display = "none";

        if (viewModel.purpose === "ANOMALY_DETECTION_TEST" || viewModel.purpose === "FORZA_DEMO") {
          console.log("[CCTV TEST VIDEO]");
          console.log("cam_id:", viewModel.id);
          console.log("location:", viewModel.location);
          console.log("video:", viewModel.videoUrl);
          console.log("purpose:", viewModel.purpose);
        }

        this.switchVideo(viewModel.videoUrl, viewModel.id);

        // 사전 분석 박스 오버레이: H4642 테스트 카메라(data/anomaly-track-log.json, cam_id 고정)와
        // Forza 데모 4개(카메라마다 다른 trackLogUrl) 둘 다 같은 메커니즘을 공유한다.
        if (viewModel.purpose === "ANOMALY_DETECTION_TEST") {
          this._attachBoxOverlay(viewModel.id, "data/anomaly-track-log.json");
        } else if (viewModel.purpose === "FORZA_DEMO" && viewModel.trackLogUrl) {
          this._attachBoxOverlay(viewModel.id, viewModel.trackLogUrl);
        } else {
          this._detachBoxOverlay();
        }
      } else {
        // 영상이 연결되지 않은 카메라 - video src를 건드리지 않고 placeholder만 표시
        this._clearVideo();
        this._detachBoxOverlay();
        this.overlayEl.style.display = "none";
        this.emptyEl.style.display = "flex";
      }

      this.frameEl.classList.remove("is-fading");
    };

    if (immediate) {
      apply();
      return;
    }

    // 0.3~0.5초 정도의 fade-out → 내용 교체 → fade-in
    this.frameEl.classList.add("is-fading");
    setTimeout(apply, 220);
  }

  // 저수준 영상 전환 함수. <video> 태그의 src만 교체하고 자동 재생한다.
  // (autoplay / muted / loop / playsinline은 index.html의 <video> 태그에 이미 설정되어 있음)
  // 다른 CCTV를 새로 연결할 때도 이 함수 하나만 호출하면 된다: videoManager.switchVideo('경로', 'cam_id')
  //
  // HLS(.m3u8)는 Safari를 제외한 대부분 브라우저(Chrome/Edge/Firefox)가 <video src="...">만으로는
  // 재생하지 못한다. 그래서 .m3u8 확장자일 때만 hls.js를 붙여서 재생하고, 그 외(mp4 등)는
  // 기존 방식(직접 src 지정) 그대로 사용한다. VideoManager의 나머지 로직/구조는 바꾸지 않았다.
  switchVideo(videoPath, camId = null) {
    this._hideError();
    this._destroyHls(); // 이전 카메라가 HLS를 쓰고 있었다면 정리
    this.currentCamId = camId;

    console.log("[CCTV VIDEO]");
    console.log("cam_id:", camId);
    console.log("video (경로 지정값):", videoPath);

    const isHls = /\.m3u8(\?.*)?$/i.test(videoPath);
    const nativeHlsSupported = this.videoEl.canPlayType("application/vnd.apple.mpegurl") !== "";

    if (isHls && !nativeHlsSupported) {
      if (typeof Hls === "undefined" || !Hls.isSupported()) {
        console.warn("[CCTV VIDEO] hls.js를 사용할 수 없어 HLS 영상을 재생할 수 없습니다:", { camId, videoPath });
        this._showError();
        return;
      }
      this.hls = new Hls();
      this.hls.on(Hls.Events.ERROR, (event, data) => {
        if (data && data.fatal) {
          console.warn("[CCTV VIDEO] hls.js 치명적 오류:", { camId, videoPath, type: data.type, details: data.details });
          this._showError();
        }
      });
      this.hls.loadSource(videoPath);
      this.hls.attachMedia(this.videoEl);
      console.log("video (재생 방식): hls.js");
    } else {
      // Safari(네이티브 HLS) 또는 mp4 등 일반 영상 - 기존 방식 그대로
      this.videoEl.src = videoPath;
      this.videoEl.load();
      console.log("video (재생 방식):", isHls ? "네이티브 HLS(Safari)" : "일반 <video> src");
    }

    // 실제로 브라우저가 해석한 최종 URL(videoEl.src는 절대경로로 정규화되어 반환됨)을 함께 출력
    console.log("video (최종 해석 URL):", this.videoEl.currentSrc || this.videoEl.src || "(hls.js가 관리 중)");

    // [요구사항 12] Forza 데모 카메라(A/B/C/D)를 볼 때는 처음부터 다시 재생하지 않고,
    // 백그라운드 ForzaDemoTimeline이 지금 실제로 도달해 있는 재생 위치에서부터 보여준다.
    // "가능하면"이라는 요구사항 문구에 맞춰 최선의 근사치로 처리한다: 화면에 보이는 이
    // <video>와 백그라운드 timeline의 <video>는 서로 다른(별개의) 엘리먼트이므로, 전환
    // 시점에 currentTime을 한 번 맞춰준 뒤에는 두 영상이 각자 독립적으로 재생된다(발표
    // 데모 용도로는 체감상 거의 차이가 없다 - 완전한 프레임 단위 동기화는 하지 않는다).
    if (CONFIG.FORZA_DEMO_SOURCES[camId] && window.forzaDemoTimeline) {
      const demoId = CONFIG.FORZA_DEMO_SOURCES[camId].demoId;
      const syncTime = window.forzaDemoTimeline.getSyncCurrentTime(demoId);
      const applySync = () => {
        if (syncTime > 0) {
          this.videoEl.currentTime = Math.min(syncTime, this.videoEl.duration || syncTime);
        }
      };
      if (this.videoEl.readyState >= 1) applySync();
      else this.videoEl.addEventListener("loadedmetadata", applySync, { once: true });
    }

    this.videoEl.play().catch((err) => {
      console.warn("[CCTV VIDEO] play() 실패:", { camId, src: this.videoEl.currentSrc || this.videoEl.src, err });
    });
  }

  // hls.js 인스턴스를 정리한다 (다른 카메라로 전환하거나 영상이 없는 상태로 갈 때 반드시 호출)
  _destroyHls() {
    if (this.hls) {
      this.hls.destroy();
      this.hls = null;
    }
  }

  // 영상이 없는 카메라로 전환될 때 재생 중이던 영상을 정지하고 src를 비운다
  _clearVideo() {
    this._hideError();
    this._destroyHls();
    this.currentCamId = null;
    this.videoEl.pause();
    this.videoEl.removeAttribute("src");
    this.videoEl.load();
  }

  // <video> error 이벤트 발생 시 실제 src와 MediaError 상세를 콘솔에 출력
  _handleVideoError() {
    const mediaError = this.videoEl.error;
    console.error("[CCTV VIDEO] 로딩 실패", {
      cam_id: this.currentCamId,
      "video.src": this.videoEl.src,
      "video.currentSrc": this.videoEl.currentSrc,
      errorCode: mediaError ? mediaError.code : null,
      errorMessage: mediaError ? mediaError.message : null,
    });
    this._showError();
  }

  _showError() {
    this.errorEl.style.display = "flex";
  }

  _hideError() {
    this.errorEl.style.display = "none";
  }

  /* ================================================================
     AI 박스 오버레이 (사전 분석 + 재생 시점 동기화)
     ----------------------------------------------------------------
     export_track_log.py가 만들어 둔 data/anomaly-track-log.json을 불러와서,
     video.currentTime에 해당하는 프레임의 차량 박스를 canvas에 그린다.
     "이상운전 에피소드" 시작 시각을 지나갈 때마다 onAnomalyEpisode 콜백을
     호출해서 이벤트 카드/토스트/통계가 함께 반응하도록 한다.
  ================================================================ */
  async _attachBoxOverlay(camId, trackLogUrl) {
    this._detachBoxOverlay(); // 이전 카메라의 오버레이 정리

    let log = this.trackLogCacheByCamId.get(camId);
    if (!log) {
      try {
        const res = await fetch(trackLogUrl, { cache: "no-store" });
        if (!res.ok) throw new Error(`status ${res.status}`);
        log = await res.json();
        this.trackLogCacheByCamId.set(camId, log);
      } catch (err) {
        console.warn(
          `[ANOMALY OVERLAY] ${trackLogUrl}을 불러오지 못했습니다. ` +
            "export_track_log.py(또는 export_forza_track_logs.py)를 먼저 실행했는지 확인해주세요. " +
            "(박스 오버레이 없이 영상만 재생됩니다)",
          err
        );
        return;
      }
    }

    // 아직 로딩 중이던 사이에 사용자가 다른 카메라로 넘어갔을 수 있으니 다시 확인
    if (this.currentCamId !== camId) return;
    if (log.cam_id !== camId) {
      console.warn(`[ANOMALY OVERLAY] 트랙 로그의 cam_id(${log.cam_id})가 현재 카메라(${camId})와 다릅니다.`);
      return;
    }

    this.trackLogCache = log; // 지금부터 _renderBoxOverlay/_checkAnomalyEpisodes가 참조하는 "현재 활성" 로그
    this.boxOverlayActive = true;
    // 새로운 분석 세션 시작: 이전 세션에서 처리한 episode 기록을 모두 초기화한다.
    this.sessionId += 1;
    this.processedEpisodeKeys.clear();
    this._prevOverlayTime = null;
    this.aiBadgeEl.style.display = "inline-flex";

    const loop = () => {
      this._renderBoxOverlay();
      this.boxOverlayRafId = requestAnimationFrame(loop);
    };
    this.boxOverlayRafId = requestAnimationFrame(loop);
  }

  _detachBoxOverlay() {
    if (this.boxOverlayRafId) cancelAnimationFrame(this.boxOverlayRafId);
    this.boxOverlayRafId = null;
    this.boxOverlayActive = false;
    // 카메라를 벗어나면(= 다른 CCTV 선택) 지금 세션은 종료된 것으로 간주한다.
    // processedEpisodeKeys는 다음 _attachBoxOverlay() 호출(= 새 세션 시작) 시점에 다시 초기화된다.
    this.aiBadgeEl.style.display = "none";
    this.canvasCtx.clearRect(0, 0, this.canvasEl.width, this.canvasEl.height);
  }

  _renderBoxOverlay() {
    const log = this.trackLogCache;
    if (!log || !this.boxOverlayActive) return;

    const rect = this.videoEl.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) return;
    if (!log.width || !log.height) return; // export_track_log.py를 아직 실행하지 않은 스텁 상태

    const dpr = window.devicePixelRatio || 1;
    const cssW = rect.width;
    const cssH = rect.height;
    const pixelW = Math.round(cssW * dpr);
    const pixelH = Math.round(cssH * dpr);
    if (this.canvasEl.width !== pixelW || this.canvasEl.height !== pixelH) {
      this.canvasEl.width = pixelW;
      this.canvasEl.height = pixelH;
    }

    const ctx = this.canvasCtx;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, cssW, cssH);

    // <video>는 object-fit:cover이므로, 실제로 화면에 보이는 영역(letterbox 제외)을 계산해야
    // 박스 좌표가 어긋나지 않는다.
    const videoRatio = log.width / log.height;
    const boxRatio = cssW / cssH;
    let drawW, drawH, offsetX, offsetY;
    if (boxRatio > videoRatio) {
      drawW = cssW;
      drawH = cssW / videoRatio;
      offsetX = 0;
      offsetY = (cssH - drawH) / 2;
    } else {
      drawH = cssH;
      drawW = cssH * videoRatio;
      offsetX = (cssW - drawW) / 2;
      offsetY = 0;
    }
    const scale = drawW / log.width;

    const t = this.videoEl.currentTime;
    const frame = this._findNearestFrame(log.frames, t);

    if (frame) {
      frame.boxes.forEach((b) => {
        const x = offsetX + b.x1 * scale;
        const y = offsetY + b.y1 * scale;
        const w = (b.x2 - b.x1) * scale;
        const h = (b.y2 - b.y1) * scale;

        ctx.lineWidth = b.alert ? 3 : 2;
        ctx.strokeStyle = b.alert ? "#ff3b3b" : "rgba(56, 189, 248, 0.6)";
        ctx.strokeRect(x, y, w, h);

        if (b.alert) {
          ctx.fillStyle = "#ff3b3b";
          ctx.font = "bold 13px sans-serif";
          ctx.fillText("이상 주행 감지", x, Math.max(y - 6, 12));
        }
      });
    }

    this._checkAnomalyEpisodes(t);
  }

  // 시간 기준 이진 탐색으로 t 이하 중 가장 가까운 프레임을 찾는다 (frames는 시간순 정렬 가정)
  _findNearestFrame(frames, t) {
    let lo = 0;
    let hi = frames.length - 1;
    let ans = null;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if (frames[mid].t <= t) {
        ans = frames[mid];
        lo = mid + 1;
      } else {
        hi = mid - 1;
      }
    }
    return ans;
  }

  // episode 고유 키: 같은 세션 안에서 이미 이벤트를 발생시킨 episode인지 판별하는 데 사용한다.
  // cam_id + track_id + episode 시작 시각(t)의 조합이면 anomaly-track-log.json 상에서 충분히 유일하다.
  _episodeKey(episode) {
    return `${this.currentCamId}_${episode.track_id}_${episode.t}`;
  }

  // 재생 시점이 "이상운전 에피소드 시작 시각"을 새로 지나갔으면 콜백을 호출한다.
  // ------------------------------------------------------------------
  // "영상 1회 재생 = 하나의 분석 세션" 정책:
  // - processedEpisodeKeys(Set)에 한 번 추가된 episode는 같은 세션이 끝날 때까지
  //   (= 다른 CCTV로 이동하거나 H4642를 다시 선택하기 전까지) 다시 이벤트를 만들지 않는다.
  // - 영상이 loop로 처음부터 반복 재생되어도 Set은 그대로 유지되므로 중복 이벤트가 발생하지 않는다.
  // - setTimeout 등 시간 기반 차단은 사용하지 않고, 오직 "이미 처리된 episode인가"만으로 판단한다.
  _checkAnomalyEpisodes(t) {
    // loop 감지: currentTime이 이전 프레임보다 뒤로 되돌아갔다면 영상이 처음부터 다시 재생된 것.
    // (실제 중복 방지는 processedEpisodeKeys가 담당하고, 이 로그는 세션 추적/디버깅용이다)
    if (this._prevOverlayTime != null && t < this._prevOverlayTime - 0.25) {
      console.log(
        `[ANOMALY OVERLAY] 영상 루프 감지 (cam_id=${this.currentCamId}, session=${this.sessionId}) - 동일 세션 내 이미 처리된 episode는 재생성되지 않습니다.`
      );
    }
    this._prevOverlayTime = t;

    const episodes = this.trackLogCache.episodes || [];
    episodes.forEach((episode) => {
      if (episode.t > t) return; // 아직 재생 시점이 도달하지 않은 episode

      const key = this._episodeKey(episode);
      if (this.processedEpisodeKeys.has(key)) return; // 이번 세션에서 이미 처리됨 - 중복 생성 방지

      this.processedEpisodeKeys.add(key);

      // [요구사항 1: 백그라운드 분석] Forza 데모 소스(A/B/C/D)는 이제 화면 표시 여부와
      // 무관하게 ForzaBackgroundAnalyzer가 항상 분석하고 있다. 여기(실제로 화면에
      // 보이고 있을 때만 실행되는 코드)에서도 onAnomalyEpisode를 부르면 같은 episode가
      // 두 경로로 중복 발화된다. 그래서 Forza 소스는 여기서 콜백 호출을 건너뛴다 -
      // 화면 위 박스 그리기 자체는 이 메서드가 아니라 _renderBoxOverlay()가 매 프레임
      // 별도로 처리하므로, 화면에 실제 박스가 그려지는 건 전혀 영향받지 않는다.
      if (CONFIG.FORZA_DEMO_SOURCES[this.currentCamId]) return;

      if (this.onAnomalyEpisode) this.onAnomalyEpisode(episode, this.currentCamId, this.sessionId);
    });
  }
}

/* ==================================================================
   4B) VideoModalManager - CCTV 영상 확대(Modal)
   -------------------------------------------------------------
   영상을 <video> 태그를 복제하지 않고, 기존 video-frame 노드(video + AI
   오버레이 캔버스 + LIVE/AI 배지)를 통째로 modal 안으로 옮겼다가 닫을 때
   원래 자리로 되돌려 놓는 방식이다. 노드를 그대로 재사용하기 때문에:
   - video.currentTime이 그대로 유지된다 (작은 화면 15초 → 확대해도 15초부터)
   - <video>가 다시 로드/재생되지 않으므로 재생 위치가 어긋나지 않는다
   - VideoManager의 requestAnimationFrame 루프(AI 박스 오버레이)가 그대로
     같은 canvas에 그리기 때문에 AI Bounding Box/빨간 박스도 끊김 없이 유지된다
================================================== */
class VideoModalManager {
  constructor(frameEl, titleGetter) {
    this.frameEl = frameEl;
    this.modalEl = document.getElementById("video-modal");
    this.modalBodyEl = document.getElementById("video-modal-body");
    this.modalTitleEl = document.getElementById("video-modal-title");
    this.expandBtnEl = document.getElementById("video-expand-btn");
    this.closeBtnEl = document.getElementById("video-modal-close");
    this.titleGetter = titleGetter;

    // video-frame을 원래 자리로 되돌리기 위해 원래 부모/다음 형제 노드를 기억해둔다
    this.originalParent = frameEl.parentElement;
    this.originalNextSibling = frameEl.nextSibling;
    this.isOpen = false;

    if (this.expandBtnEl) this.expandBtnEl.addEventListener("click", () => this.open());
    if (this.closeBtnEl) this.closeBtnEl.addEventListener("click", () => this.close());
    if (this.modalEl) {
      // 배경(어두운 영역) 클릭 시에도 닫히도록
      this.modalEl.addEventListener("click", (e) => {
        if (e.target === this.modalEl) this.close();
      });
    }
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && this.isOpen) this.close();
    });
  }

  open() {
    if (this.isOpen || !this.modalEl) return;
    this.isOpen = true;
    this.modalTitleEl.textContent = this.titleGetter ? this.titleGetter() : "-";
    this.modalBodyEl.appendChild(this.frameEl);
    this.frameEl.classList.add("video-panel__frame--modal");
    this.modalEl.classList.add("is-open");
    this.modalEl.style.display = "flex";
  }

  close() {
    if (!this.isOpen) return;
    this.isOpen = false;
    this.frameEl.classList.remove("video-panel__frame--modal");
    // video-frame을 원래 있던 위치(작은 CCTV 패널)로 정확히 되돌려 놓는다
    if (this.originalNextSibling && this.originalNextSibling.parentElement === this.originalParent) {
      this.originalParent.insertBefore(this.frameEl, this.originalNextSibling);
    } else {
      this.originalParent.appendChild(this.frameEl);
    }
    this.modalEl.classList.remove("is-open");
    this.modalEl.style.display = "none";
  }
}

/* ==================================================================
   5) TrafficCameraManager - 공공데이터 무인교통단속카메라
   -------------------------------------------------------------
   이제 지도에 상시 표시되는 카메라는 이것뿐이다(고정 AI CCTV 없음).
   selectRecord()가 "지도 Zoom + Popup Open + 선택 하이라이트 + 영상 전환"을
   한 번에 처리하는 허브 메서드이며, 마커 클릭 / 이벤트 카드 클릭 /
   AI 자동 감지가 모두 이 메서드를 공유한다.
================================================== */
class TrafficCameraManager {
  constructor(mapManager, videoManager) {
    this.mapManager = mapManager;
    this.map = mapManager.getMap();
    this.videoManager = videoManager;

    this.allRecords = [];
    this.markers = [];
    this.markerState = new WeakMap(); // marker -> { isSelected, isAlert }
    this.markerById = new Map(); // 관리번호 -> { marker, record }
    this.selectedMarker = null;
    this.alertMarker = null;

    this.clusterGroup =
      typeof L.markerClusterGroup === "function"
        ? L.markerClusterGroup({
            maxClusterRadius: 44,
            spiderfyOnMaxZoom: true,
            iconCreateFunction: (cluster) => this._createClusterIcon(cluster),
          })
        : L.layerGroup();

    this.clusterGroup.addTo(this.map);
  }

  // 딥네이비 원형 배지 + 선명한 카메라 글리프. 얇은 하늘색-화이트 외곽선과 Glow로
  // 위성지도 위에서도 눈에 띄도록 한다. isAlert면 붉은색으로 바뀌며 pulse가 붙는다.
  _createIcon(isSelected, isAlert) {
    const strokeWidth = isSelected ? 2.6 : 1.5;
    const classes = ["traffic-cam-marker"];
    if (isAlert) classes.push("traffic-cam-marker--alert");
    if (isSelected) classes.push("traffic-cam-marker--selected");

    const svg = `
      <svg viewBox="0 0 40 40" xmlns="http://www.w3.org/2000/svg">
        <circle cx="20" cy="20" r="17" fill="currentColor" opacity="0.16" />
        <circle cx="20" cy="20" r="13.5" fill="currentColor" stroke="#eaf6ff" stroke-width="${strokeWidth}" />
        <g fill="#eaf6ff">
          <rect x="13.4" y="15.2" width="9.6" height="3.6" rx="1.1" />
          <rect x="9.4" y="18.6" width="17" height="10.2" rx="2.5" />
          <rect x="22.6" y="21" width="6.8" height="5.4" rx="1.3" />
        </g>
        <circle cx="15.8" cy="23.7" r="2.8" fill="currentColor" />
        <circle cx="15.8" cy="23.7" r="1.2" fill="#eaf6ff" />
      </svg>
    `;

    return L.divIcon({
      className: "",
      html: `<div class="${classes.join(" ")}">${svg}</div>`,
      iconSize: [34, 34],
      iconAnchor: [17, 17],
      popupAnchor: [0, -15],
    });
  }

  _createClusterIcon(cluster) {
    return L.divIcon({
      className: "",
      html: `<div class="traffic-cam-cluster">${cluster.getChildCount()}</div>`,
      iconSize: [44, 44],
    });
  }

  _buildPopup(record) {
    const speed = record["제한속도"] ? `${record["제한속도"]} km/h` : "-";

    return `
      <div class="cctv-popup">
        <div class="cctv-popup__header">
          <div class="cctv-popup__title">
            <span class="cctv-popup__code">단속카메라(공공데이터)</span>
            <span class="cctv-popup__name">${record["설치장소"] || "설치장소 정보 없음"}</span>
          </div>
        </div>
        <div class="cctv-popup__body">
          <span class="cctv-popup__label">설치장소</span>
          <span class="cctv-popup__value">${record["설치장소"] || "-"}</span>

          <span class="cctv-popup__label">시군구</span>
          <span class="cctv-popup__value">${record["시군구명"] || "-"}</span>

          <span class="cctv-popup__label">제한속도</span>
          <span class="cctv-popup__value">${speed}</span>

          <span class="cctv-popup__label">단속구분</span>
          <span class="cctv-popup__value">${record["단속구분"] || "-"}</span>

          <span class="cctv-popup__label">보호구역구분</span>
          <span class="cctv-popup__value">${record["보호구역구분"] || "-"}</span>
        </div>
      </div>
    `;
  }

  async loadData(url) {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`공공데이터 로드 실패: ${res.status}`);
    const json = await res.json();
    this.allRecords = Array.isArray(json.records) ? json.records : [];
    return this.allRecords;
  }

  filterByCity(cityName) {
    const filtered = this.allRecords.filter((r) => r["시도명"] === cityName);
    this._render(filtered);
    return filtered;
  }

  filterByDistrict(districtName, cityName) {
    const filtered = this.allRecords.filter(
      (r) => r["시군구명"] === districtName && (!cityName || r["시도명"] === cityName)
    );
    this._render(filtered);
    return filtered;
  }

  getRecordById(managementId) {
    const entry = this.markerById.get(String(managementId));
    return entry ? entry.record : null;
  }

  getRecordCount() {
    return this.markers.length;
  }

  // CCTV 검색(SearchManager 전용): 현재 지도에 렌더링되어 있는(=markerById에 등록된) 카메라만 대상으로
  // 설치장소 / 시군구명 / 관리번호(cam_id) 문자열에 검색어가 포함되는지로 매칭한다.
  // 렌더링된 마커만 검색 대상으로 삼는 이유는, 검색 결과를 클릭했을 때 selectById()가
  // 항상 실제 지도 마커를 찾아 선택할 수 있도록 보장하기 위함이다.
  // 반환값: { results: 상위 limit개 레코드 배열, total: 전체 매칭 건수 }
  searchRecords(query, limit = 20) {
    const q = String(query || "").trim().toLowerCase();
    if (!q) return { results: [], total: 0 };

    const matched = [];
    this.markerById.forEach(({ record }) => {
      const location = String(record["설치장소"] || "").toLowerCase();
      const district = String(record["시군구명"] || "").toLowerCase();
      const camId = String(record["무인교통단속카메라관리번호"] || "").toLowerCase();

      if (location.includes(q) || district.includes(q) || camId.includes(q)) {
        matched.push(record);
      }
    });

    return { results: matched.slice(0, limit), total: matched.length };
  }

  _render(records) {
    this.clusterGroup.clearLayers();
    this.selectedMarker = null;
    this.alertMarker = null;
    this.markerById.clear();
    this.markers = [];

    records.forEach((record) => {
      const lat = parseFloat(record["위도"]);
      const lng = parseFloat(record["경도"]);
      if (Number.isNaN(lat) || Number.isNaN(lng)) return;

      const marker = L.marker([lat, lng], { icon: this._createIcon(false, false) });
      marker.bindPopup(this._buildPopup(record));
      this.markerState.set(marker, { isSelected: false, isAlert: false });
      marker.on("click", () => this.selectRecord(marker, record, { openPopup: true, zoom: true, switchVideo: true }));

      this.markers.push(marker);
      this.markerById.set(String(record["무인교통단속카메라관리번호"]), { marker, record });
    });

    if (typeof this.clusterGroup.addLayers === "function") {
      this.clusterGroup.addLayers(this.markers);
    } else {
      this.markers.forEach((m) => this.clusterGroup.addLayer(m));
    }

    // 최초 로드 시 첫 번째 카메라 영상을 기본으로 표시 (지도 이동/팝업 없이 영상만)
    if (records.length > 0) {
      this.videoManager.switchTo(buildCameraViewModel(records[0]), { immediate: true });
    }
  }

  _refreshIcon(marker) {
    const state = this.markerState.get(marker) || { isSelected: false, isAlert: false };
    marker.setIcon(this._createIcon(state.isSelected, state.isAlert));
  }

  _setSelectedMarker(marker) {
    if (this.selectedMarker && this.selectedMarker !== marker) {
      const prevState = this.markerState.get(this.selectedMarker);
      if (prevState) {
        prevState.isSelected = false;
        this._refreshIcon(this.selectedMarker);
      }
    }
    const state = this.markerState.get(marker);
    if (state) {
      state.isSelected = true;
      this._refreshIcon(marker);
    }
    this.selectedMarker = marker;
  }

  // AI 이벤트가 발생한(또는 해제된) 카메라를 빨간색으로 강조한다.
  setAlert(managementId, isAlert) {
    const entry = this.markerById.get(String(managementId));
    if (!entry) return;

    if (isAlert && this.alertMarker && this.alertMarker !== entry.marker) {
      const prevState = this.markerState.get(this.alertMarker);
      if (prevState) {
        prevState.isAlert = false;
        this._refreshIcon(this.alertMarker);
      }
    }

    const state = this.markerState.get(entry.marker);
    if (state) {
      state.isAlert = isAlert;
      this._refreshIcon(entry.marker);
    }
    this.alertMarker = isAlert ? entry.marker : this.alertMarker === entry.marker ? null : this.alertMarker;
  }

  // 카메라 선택 허브: 지도 Zoom / Popup Open / 선택 하이라이트 / 영상 전환을 함께 실행한다.
  selectRecord(marker, record, opts = {}) {
    const { openPopup = false, zoom = false, switchVideo = false } = opts;
    const vm = buildCameraViewModel(record);

    if (zoom) this.mapManager.focus(vm.lat, vm.lng, CONFIG.FOCUS_ZOOM);
    if (openPopup) marker.openPopup();
    this._setSelectedMarker(marker);
    if (switchVideo) this.videoManager.switchTo(vm);
  }

  // 관리번호로 카메라를 선택 (이벤트 패널 클릭, AI 자동 감지 등에서 사용).
  // 클러스터에 묶여 화면에 보이지 않는 마커도 클러스터를 펼쳐서 보여준다.
  selectById(managementId, opts = {}) {
    const entry = this.markerById.get(String(managementId));
    if (!entry) return null;

    const applySelect = () => this.selectRecord(entry.marker, entry.record, opts);
    if (typeof this.clusterGroup.zoomToShowLayer === "function") {
      this.clusterGroup.zoomToShowLayer(entry.marker, applySelect);
    } else {
      applySelect();
    }
    return entry.record;
  }
}

/* ==================================================================
   5B) SearchManager - CCTV 검색 (주소/장소명 → 목록 → 카메라 선택)
   -------------------------------------------------------------
   web/data/utic-cameras-seoul.json(UTIC 서울 CCTV 303건)을 검색 대상으로 쓴다.
   검색어는 UticCameraManager.searchRecords()가 매칭하며(CCTV명/관리번호/제공기관),
   결과 클릭 시 UticCameraManager.selectById()를 그대로 호출해
   "지도 확대 + 팝업 오픈 + 영상 전환"을 기존 로직 그대로 재사용한다.
   검색 결과에는 VideoSourceRegistry 조회 결과에 따라 실시간 연결 여부 배지를 표시한다.
================================================== */
class SearchManager {
  constructor(uticCameraManager, videoSourceRegistry, formEl, inputEl, resultsEl) {
    this.uticCameraManager = uticCameraManager;
    this.videoSourceRegistry = videoSourceRegistry;
    this.formEl = formEl;
    this.inputEl = inputEl;
    this.resultsEl = resultsEl;

    if (this.formEl) {
      this.formEl.addEventListener("submit", (e) => {
        e.preventDefault();
        this._runSearch(this.inputEl.value);
      });
    }
    if (this.inputEl) {
      // 입력할 때마다 실시간으로 결과를 갱신한다 (검색 버튼을 누르지 않아도 됨)
      this.inputEl.addEventListener("input", () => this._runSearch(this.inputEl.value));
    }
  }

  _runSearch(rawQuery) {
    const query = String(rawQuery || "").trim();

    if (!query) {
      this._renderHint("CCTV명, 관리번호, 제공기관명으로 검색할 수 있습니다");
      return;
    }

    const { results, total } = this.uticCameraManager.searchRecords(query, 20);

    if (total === 0) {
      this._renderHint(`"${this._escape(query)}" 검색 결과가 없습니다`);
      return;
    }

    this._renderResults(results, total);
  }

  _renderHint(message) {
    this.resultsEl.innerHTML = `<div class="cctv-search-panel__hint">${message}</div>`;
  }

  _renderResults(records, total) {
    const countHtml = `<div class="cctv-search-panel__count">검색 결과 <strong>${total.toLocaleString()}건</strong>${
      total > records.length ? ` · 상위 ${records.length}건 표시` : ""
    }</div>`;

    const itemsHtml = records
      .map((record) => {
        const camId = record.cam_id || "-";
        const name = record.name || "이름 정보 없음";
        const center = record.center_name || "-";
        const source = this.videoSourceRegistry ? this.videoSourceRegistry.getSource(record.cam_id) : null;
        const videoBadge = source
          ? `<span class="cctv-search-result__video-badge cctv-search-result__video-badge--live">● 실시간 연결${
              source.video_format ? ` (${source.video_format})` : ""
            }</span>`
          : `<span class="cctv-search-result__video-badge">○ 연결 예정</span>`;

        return `
          <button type="button" class="cctv-search-result" data-cam-id="${this._escape(camId)}">
            <span class="cctv-search-result__icon">📹</span>
            <span class="cctv-search-result__body">
              <span class="cctv-search-result__name">${this._escape(name)}</span>
              <span class="cctv-search-result__meta">${this._escape(String(camId))} · ${this._escape(center)}</span>
              ${videoBadge}
            </span>
          </button>
        `;
      })
      .join("");

    this.resultsEl.innerHTML = `${countHtml}<div class="cctv-search-panel__list">${itemsHtml}</div>`;

    this.resultsEl.querySelectorAll(".cctv-search-result").forEach((btnEl) => {
      btnEl.addEventListener("click", () => {
        const camId = btnEl.dataset.camId;
        this.uticCameraManager.selectById(camId, { openPopup: true, zoom: true, switchVideo: true });
      });
    });
  }

  // 검색어/장소명을 그대로 innerHTML에 꽂아 넣기 때문에 최소한의 XSS 방지용 이스케이프를 적용한다
  _escape(str) {
    const div = document.createElement("div");
    div.textContent = String(str);
    return div.innerHTML;
  }
}

/* ==================================================================
   5C) VideoSourceRegistry - UTIC 카메라의 "영상 공급원" 레지스트리
   -------------------------------------------------------------
   UTIC 담당자 공식 답변: UTIC CCTV 개방데이터는 "단순 목록/메타데이터"이며,
   실제 영상 스트림은 각 CCTV를 운영하는 기관/지자체가 개별적으로 제공한다.
   즉 "카메라가 어디 있는가"(utic-cameras-seoul.json)와 "그 카메라의 영상을
   어디서 재생할 수 있는가"(이 레지스트리, web/data/utic-video-sources.json)는
   서로 완전히 다른 데이터라서 분리해서 관리한다.

   지금은 실제로 확보된 영상 URL이 하나도 없으므로 sources가 비어있는 채로
   시작하며, 이는 정상이다. 나중에 특정 CCTV의 실제 스트림 URL을 확보하면
   web/data/utic-video-sources.json에 항목 하나만 추가하면 되고, 코드
   수정 없이 그 CCTV를 클릭하는 즉시 영상이 재생되도록 이미 연결되어 있다
   (UticCameraManager.selectRecord() 참고).
================================================== */
class VideoSourceRegistry {
  constructor() {
    this.sourcesByCamId = new Map(); // cam_id -> { cam_id, video_url, video_format, source_type }
  }

  async loadData(url) {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`영상 공급원 데이터 로드 실패: ${res.status}`);
    const json = await res.json();
    const list = Array.isArray(json.sources) ? json.sources : [];

    this.sourcesByCamId.clear();
    list.forEach((s) => {
      if (s && s.cam_id) this.sourcesByCamId.set(String(s.cam_id), s);
    });

    return list;
  }

  // cam_id에 등록된 영상 공급원이 있으면 반환, 없으면 null (아직 대부분 null인 게 정상)
  getSource(camId) {
    return this.sourcesByCamId.get(String(camId)) || null;
  }

  getCount() {
    return this.sourcesByCamId.size;
  }
}

/* ==================================================================
   5D) UticCameraManager - 서울 UTIC(도시교통정보센터) 실시간 CCTV
   -------------------------------------------------------------
   web/data/utic-cameras-seoul.json (OpenDataCCTV.xlsx에서 서울교통정보센터
   제공 CCTV만 추출한 별도 데이터)을 표시하는, TrafficCameraManager와는
   완전히 독립된 마커 레이어다. 기존 TrafficCameraManager/공공데이터
   단속카메라 4,255건과는 다른 데이터 소스이며, 필드 구조도 다르다
   (예: cam_id, name, center_name, lat, lng - 한글 필드명이 아님).

   지도 표시(줌/이동/팝업/선택 하이라이트)에 더해, VideoSourceRegistry에
   해당 cam_id의 영상 공급원이 등록되어 있으면 우측 영상 패널로도 자동
   연결한다. 등록되어 있지 않으면(현재 대부분의 경우) 팝업에 "연결 예정"만
   표시하고 영상 패널은 건드리지 않는다.
================================================== */
class UticCameraManager {
  constructor(mapManager, videoManager, videoSourceRegistry) {
    this.mapManager = mapManager;
    this.map = mapManager.getMap();
    this.videoManager = videoManager; // 없어도(undefined) 동작하도록 아래에서 항상 존재 확인 후 사용
    this.videoSourceRegistry = videoSourceRegistry;

    this.allRecords = [];
    this.markers = [];
    this.markerState = new WeakMap(); // marker -> { isSelected }
    this.markerById = new Map(); // cam_id -> { marker, record }
    this.selectedMarker = null;
    this.alertMarker = null;

    this.clusterGroup =
      typeof L.markerClusterGroup === "function"
        ? L.markerClusterGroup({
            maxClusterRadius: 40,
            spiderfyOnMaxZoom: true,
            iconCreateFunction: (cluster) => this._createClusterIcon(cluster),
          })
        : L.layerGroup();

    // 카메라가 선택(클릭/검색/이벤트 카드 클릭 등 - selectRecord()가 호출되는 모든 경로 공통)될
    // 때마다 호출되는 훅. [버그 수정] 예전에는 이 훅이 Forza 데모의 이동 경로를
    // 결정했지만(클릭 순서 기반), 이제 경로는 오직 실제 AI 감지(EventManager.triggerDemoEvent)로만
    // 결정된다 - init 블록에서 이 훅은 빈 함수로 연결되어 있다.
    this.onCameraSelected = null;

    this.clusterGroup.addTo(this.map);
  }

  // TrafficCameraManager의 단속카메라 아이콘과 형태(카메라 글리프)는 맞추되,
  // 색상을 다르게 해서 "공공데이터 단속카메라"와 "UTIC 실시간 CCTV"를 한눈에 구분한다.
  // isAlert(AI 이상탐지 강조)는 TrafficCameraManager와 동일한 개념으로, EventManager가
  // 필요할 때(예: 향후 실제 UTIC 영상 기반 이상탐지 연동 시) setAlert()를 통해 켠다.
  _createIcon(isSelected, isAlert) {
    const strokeWidth = isSelected ? 2.6 : 1.5;
    const classes = ["utic-cam-marker"];
    if (isAlert) classes.push("utic-cam-marker--alert");
    if (isSelected) classes.push("utic-cam-marker--selected");

    const svg = `
      <svg viewBox="0 0 40 40" xmlns="http://www.w3.org/2000/svg">
        <circle cx="20" cy="20" r="17" fill="currentColor" opacity="0.16" />
        <circle cx="20" cy="20" r="13.5" fill="currentColor" stroke="#eaffef" stroke-width="${strokeWidth}" />
        <g fill="#eaffef">
          <rect x="13.4" y="15.2" width="9.6" height="3.6" rx="1.1" />
          <rect x="9.4" y="18.6" width="17" height="10.2" rx="2.5" />
          <rect x="22.6" y="21" width="6.8" height="5.4" rx="1.3" />
        </g>
        <circle cx="15.8" cy="23.7" r="2.8" fill="currentColor" />
        <circle cx="15.8" cy="23.7" r="1.2" fill="#eaffef" />
      </svg>
    `;

    return L.divIcon({
      className: "",
      html: `<div class="${classes.join(" ")}">${svg}</div>`,
      iconSize: [32, 32],
      iconAnchor: [16, 16],
      popupAnchor: [0, -14],
    });
  }

  _createClusterIcon(cluster) {
    return L.divIcon({
      className: "",
      html: `<div class="utic-cam-cluster">${cluster.getChildCount()}</div>`,
      iconSize: [42, 42],
    });
  }

  // 영상 공급원 등록 여부에 따라 "실시간 연결(HLS)"/"연결 예정"을 동적으로 표시한다.
  _buildPopup(record) {
    // 반드시 cam_id(관리번호) 기준으로 조회한다 (이름/설치장소 문자열 비교 아님)
    const source = this.videoSourceRegistry ? this.videoSourceRegistry.getSource(record.cam_id) : null;
    const videoStatusRow = source
      ? `<span class="cctv-popup__label">영상 상태</span>
         <span class="cctv-popup__value cctv-popup__value--status-normal">● 실시간 연결</span>`
      : `<span class="cctv-popup__label">영상 상태</span>
         <span class="cctv-popup__value">○ 연결 예정</span>`;
    const formatRow = source && source.video_format
      ? `<span class="cctv-popup__label">스트림 형식</span>
         <span class="cctv-popup__value">${source.video_format}</span>`
      : "";

    return `
      <div class="cctv-popup">
        <div class="cctv-popup__header">
          <div class="cctv-popup__title">
            <span class="cctv-popup__code">UTIC 실시간 CCTV</span>
            <span class="cctv-popup__name">${record.name || "이름 정보 없음"}</span>
          </div>
        </div>
        <div class="cctv-popup__body">
          <span class="cctv-popup__label">관리번호</span>
          <span class="cctv-popup__value">${record.cam_id || "-"}</span>

          <span class="cctv-popup__label">제공기관</span>
          <span class="cctv-popup__value">${record.center_name || "-"}</span>

          ${videoStatusRow}
          ${formatRow}
        </div>
      </div>
    `;
  }

  async loadData(url) {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`UTIC CCTV 데이터 로드 실패: ${res.status}`);
    const json = await res.json();
    this.allRecords = Array.isArray(json.cameras) ? json.cameras : [];
    return this.allRecords;
  }

  render(records = this.allRecords) {
    this.clusterGroup.clearLayers();
    this.selectedMarker = null;
    this.markerById.clear();
    this.markers = [];

    records.forEach((record) => {
      const lat = Number(record.lat);
      const lng = Number(record.lng);
      if (!Number.isFinite(lat) || !Number.isFinite(lng)) return;

      const marker = L.marker([lat, lng], { icon: this._createIcon(false, false) });
      marker.bindPopup(this._buildPopup(record));
      this.markerState.set(marker, { isSelected: false, isAlert: false });
      marker.on("click", () =>
        this.selectById(record.cam_id, { openPopup: true, zoom: true, switchVideo: true })
      );

      this.markers.push(marker);
      this.markerById.set(String(record.cam_id), { marker, record });
    });

    if (typeof this.clusterGroup.addLayers === "function") {
      this.clusterGroup.addLayers(this.markers);
    } else {
      this.markers.forEach((m) => this.clusterGroup.addLayer(m));
    }
  }

  getRecordById(camId) {
    const entry = this.markerById.get(String(camId));
    return entry ? entry.record : null;
  }

  getRecordCount() {
    return this.markers.length;
  }

  // 검색 패널(SearchManager)에서 사용한다. CCTV명 / 관리번호 / 제공기관명으로 매칭한다.
  searchRecords(query, limit = 20) {
    const q = String(query || "").trim().toLowerCase();
    if (!q) return { results: [], total: 0 };

    const matched = [];
    this.markerById.forEach(({ record }) => {
      const name = String(record.name || "").toLowerCase();
      const center = String(record.center_name || "").toLowerCase();
      const camId = String(record.cam_id || "").toLowerCase();
      if (name.includes(q) || center.includes(q) || camId.includes(q)) {
        matched.push(record);
      }
    });

    return { results: matched.slice(0, limit), total: matched.length };
  }

  _refreshIcon(marker) {
    const state = this.markerState.get(marker) || { isSelected: false, isAlert: false };
    marker.setIcon(this._createIcon(state.isSelected, state.isAlert));
  }

  _setSelectedMarker(marker) {
    if (this.selectedMarker && this.selectedMarker !== marker) {
      const prevState = this.markerState.get(this.selectedMarker);
      if (prevState) {
        prevState.isSelected = false;
        this._refreshIcon(this.selectedMarker);
      }
    }
    const state = this.markerState.get(marker);
    if (state) {
      state.isSelected = true;
      this._refreshIcon(marker);
    }
    this.selectedMarker = marker;
  }

  // AI 이상탐지가 특정 카메라를 강조해야 할 때 EventManager가 호출한다.
  // TrafficCameraManager.setAlert()와 동일한 인터페이스라서, EventManager는
  // "지금 어떤 카메라 매니저를 쓰는지" 신경 쓰지 않고 그대로 재사용할 수 있다.
  setAlert(camId, isAlert) {
    const entry = this.markerById.get(String(camId));
    if (!entry) return;

    if (isAlert && this.alertMarker && this.alertMarker !== entry.marker) {
      const prevState = this.markerState.get(this.alertMarker);
      if (prevState) {
        prevState.isAlert = false;
        this._refreshIcon(this.alertMarker);
      }
    }

    const state = this.markerState.get(entry.marker);
    if (state) {
      state.isAlert = isAlert;
      this._refreshIcon(entry.marker);
    }
    this.alertMarker = isAlert ? entry.marker : this.alertMarker === entry.marker ? null : this.alertMarker;
  }

  // 카메라 선택 허브: 지도 Zoom / Popup Open / 선택 하이라이트 / 영상 전환(공급원이 있으면)을 함께 실행한다.
  selectRecord(marker, record, opts = {}) {
    const { openPopup = false, zoom = false, switchVideo = false } = opts;

    if (zoom) this.mapManager.focus(record.lat, record.lng, CONFIG.FOCUS_ZOOM);
    if (openPopup) marker.openPopup();
    this._setSelectedMarker(marker);

    if (switchVideo && this.videoManager) {
      const vm = buildUticCameraViewModel(record, this.videoSourceRegistry);
      this.videoManager.switchTo(vm); // videoUrl이 null이면 VideoManager가 알아서 "연결 예정" 상태를 보여준다
    }

    if (this.onCameraSelected) this.onCameraSelected(record);
  }

  // 관리번호로 카메라를 선택 (지도 Zoom + Popup Open + 선택 하이라이트).
  // 클러스터에 묶여 있으면 클러스터를 펼쳐서 보여준다.
  selectById(camId, opts = {}) {
    const entry = this.markerById.get(String(camId));
    if (!entry) return null;

    const applySelect = () => this.selectRecord(entry.marker, entry.record, opts);

    if (typeof this.clusterGroup.zoomToShowLayer === "function") {
      this.clusterGroup.zoomToShowLayer(entry.marker, applySelect);
    } else {
      applySelect();
    }
    return entry.record;
  }
}

/* ==================================================================
   6) RouteManager - 차량 이동 경로(Line)
   -------------------------------------------------------------
   평상시에는 화면을 깔끔하게 유지하기 위해 아무것도 그리지 않고,
   AI 이상 주행 이벤트가 발생했을 때만 showPath()로 이동 이력을 표시한다.
================================================== */
class RouteManager {
  constructor(map) {
    this.map = map;
    this.polyline = null;
    this.decorator = null;
    this.visible = false;
  }

  showPath(latlngs) {
    this.hide();

    const routeColor =
      getComputedStyle(document.documentElement).getPropertyValue("--accent-alert").trim() || "#ef4444";

    this.polyline = L.polyline(latlngs, {
      color: routeColor,
      weight: 5,
      opacity: 0.85,
      dashArray: "1 10",
      lineCap: "round",
    }).addTo(this.map);

    if (typeof L.polylineDecorator === "function") {
      this.decorator = L.polylineDecorator(this.polyline, {
        patterns: [
          {
            offset: "8%",
            repeat: "16%",
            symbol: L.Symbol.arrowHead({
              pixelSize: 11,
              polygon: true,
              pathOptions: { color: routeColor, fillOpacity: 0.9, weight: 0 },
            }),
          },
        ],
      }).addTo(this.map);
    }

    this.visible = true;
  }

  hide() {
    if (this.polyline) {
      this.map.removeLayer(this.polyline);
      this.polyline = null;
    }
    if (this.decorator) {
      this.map.removeLayer(this.decorator);
      this.decorator = null;
    }
    this.visible = false;
  }

  /* ----------------------------------------------------------------
     실시간 누적 trajectory (Forza A→B→C→D 전역 데모 차량 전용)
     -----------------------------------------------------------------
     showPath()/hide()는 "카메라 지점까지의 가상 진입 경로"를 매번 통째로
     다시 그리는 용도(실제 CCTV 이벤트)라서, 여러 지점을 지나며 점점 길어지는
     실제 이동 경로를 표현하기에는 맞지 않는다. 그래서 별도의 polyline을
     하나 더 두고, addTrajectoryPoint()가 호출될 때마다 좌표를 배열에 추가만
     하고 그 배열 전체로 setLatLngs()해서 "선이 점점 생성되는" 효과를 낸다.
     이 polyline은 this.polyline(위 showPath용)과 완전히 독립적이므로,
     실제 CCTV 이벤트의 진입 경로 표시와 서로 지우지 않는다.
  ==================================================================== */
  addTrajectoryPoint(latlng) {
    if (!this.trajectoryPoints) this.trajectoryPoints = [];

    const last = this.trajectoryPoints[this.trajectoryPoints.length - 1];
    if (last && last[0] === latlng[0] && last[1] === latlng[1]) return; // 완전히 같은 좌표는 건너뜀 (중복 점 방지)
    this.trajectoryPoints.push(latlng);

    if (this.trajectoryPoints.length < 2) return; // 점 1개로는 선을 그릴 수 없다 - 마커만으로 충분

    const routeColor =
      getComputedStyle(document.documentElement).getPropertyValue("--accent-alert").trim() || "#ef4444";

    if (!this.trajectoryPolyline) {
      this.trajectoryPolyline = L.polyline(this.trajectoryPoints, {
        color: routeColor,
        weight: 4,
        opacity: 0.85,
        lineCap: "round",
        lineJoin: "round",
      }).addTo(this.map);
    } else {
      this.trajectoryPolyline.setLatLngs(this.trajectoryPoints);
    }
  }

  // 발표 리허설을 다시 시작할 때(예: A영상부터 재생) 이전 데모 세션의 경로를 지운다.
  clearTrajectory() {
    if (this.trajectoryPolyline) {
      this.map.removeLayer(this.trajectoryPolyline);
      this.trajectoryPolyline = null;
    }
    this.trajectoryPoints = [];
  }

  /* ----------------------------------------------------------------
     getRoadSegment() - 두 지점 사이의 "실제 도로를 따라가는" 좌표열을 반환한다.
     -----------------------------------------------------------------
     이 프로젝트에는 자체 도로망 데이터가 없으므로, 새로 만들지 않고
     공개 OSRM 데모 서버(오픈소스 라우팅 엔진, router.project-osrm.org)에
     차량 경로를 물어봐서 그 결과 좌표열을 그대로 쓴다. 기존 지도
     시스템(Leaflet 등)을 다른 걸로 바꾸는 게 아니라, "두 좌표 사이의
     직선"이었던 부분을 "두 좌표 사이의 도로 모양 좌표열"로 바꿔치기만
     하는 것이다 - addTrajectoryPoint()로 넘겨주는 방식은 그대로.

     같은 두 지점 사이는 같은 도로 모양이 나오므로 camKey로 캐싱해서
     같은 구간을 여러 번 요청하지 않는다. 실패하면(네트워크 문제, 공개
     데모 서버 요청 제한 등) 두 점을 잇는 직선 2점으로 조용히 대체한다 -
     발표 도중 이 요청 하나 때문에 데모 전체가 멈추면 안 되기 때문이다.

     [U턴 버그 수정] OSRM은 좌표만 주면 "그 지점에서 가장 가까운 도로"에
     스냅하는데, 이때 진행 방향을 전혀 몰라서 간혹 반대 방향(역주행) 차선이나
     반대편 도로에 스냅된 뒤 되돌아오는 경로를 만들어서 교차로 근처에서
     U턴처럼 보이는 현상이 있었다. OSRM의 bearings 파라미터로 "출발점은
     대략 이 방향으로 나가고, 도착점은 대략 이 방향으로 들어온다"는 힌트를
     줘서(두 지점을 잇는 직선 방위각 기준 ±60도 허용) 반대 방향 도로에
     스냅되는 것을 방지한다. 실제 도로가 그 방향과 좀 달라도 ±60도 여유를
     충분히 뒀기 때문에 정상적인 경로 탐색 자체를 막지는 않는다.
  ==================================================================== */
  async getRoadSegment(fromLatLng, toLatLng) {
    if (!this._roadSegmentCache) this._roadSegmentCache = new Map();

    const key = `${fromLatLng[0].toFixed(6)},${fromLatLng[1].toFixed(6)}->${toLatLng[0].toFixed(6)},${toLatLng[1].toFixed(6)}`;
    if (this._roadSegmentCache.has(key)) return this._roadSegmentCache.get(key);

    const straightLine = [fromLatLng, toLatLng];
    const bearing = computeBearingDeg(fromLatLng, toLatLng);
    const BEARING_TOLERANCE_DEG = 60; // 실제 도로 방향이 직선 방위각과 다소 달라도 유효한 경로를 찾을 수 있도록 여유를 둔다
    const url =
      `https://router.project-osrm.org/route/v1/driving/` +
      `${fromLatLng[1]},${fromLatLng[0]};${toLatLng[1]},${toLatLng[0]}` +
      `?overview=full&geometries=geojson` +
      `&bearings=${bearing},${BEARING_TOLERANCE_DEG};${bearing},${BEARING_TOLERANCE_DEG}`;

    try {
      const res = await fetch(url);
      if (!res.ok) throw new Error(`OSRM 응답 오류: status ${res.status}`);
      const data = await res.json();
      const coords = data && data.routes && data.routes[0] && data.routes[0].geometry && data.routes[0].geometry.coordinates;
      if (!coords || coords.length < 2) throw new Error("OSRM 응답에 경로 좌표가 없습니다.");

      // GeoJSON은 [lng, lat] 순서 - Leaflet은 [lat, lng] 순서라 여기서 뒤집어준다.
      const rawPath = coords.map(([lng, lat]) => [lat, lng]);
      // [버그 수정: "A 시작점 U자 경로"] bearings 힌트를 통과했더라도 남아있을 수 있는
      // 시작점 부근 U턴 구간을 기하학적으로 한 번 더 걸러낸다 (stripStartUTurn 주석 참고).
      const path = stripStartUTurn(rawPath);
      this._roadSegmentCache.set(key, path);
      return path;
    } catch (err) {
      console.warn("[ROUTE] 도로 경로를 가져오지 못해 직선으로 대체합니다:", err.message || err);
      this._roadSegmentCache.set(key, straightLine); // 실패도 캐싱 - 같은 구간에서 매번 재시도해 발표를 지연시키지 않도록
      return straightLine;
    }
  }
}

/* ==================================================================
   7) VehicleManager - AI 이벤트 발생 시에만 생성되는 추적 차량
   -------------------------------------------------------------
   페이지 로드 시에는 차량이 전혀 존재하지 않는다. spawnAtEvent()가
   호출될 때 비로소 마커가 생성(또는 이미 있으면 이동)된다.
================================================== */
class VehicleManager {
  constructor(mapManager, popupManager) {
    this.mapManager = mapManager;
    this.popupManager = popupManager;
    this.marker = null;
    this.state = null;
    this.isAlertActive = false;
  }

  _createIcon(isAlertActive) {
    const classes = ["vehicle-marker"];
    if (isAlertActive) classes.push("vehicle-marker--alert");
    return L.divIcon({
      className: "",
      html: `<div class="${classes.join(" ")}">🚗</div>`,
      iconSize: [30, 30],
      iconAnchor: [15, 15],
    });
  }

  // eventData.trackId가 있으면 그대로 사용(AI가 부여한 실제 Track ID),
  // 없으면(예: 수동 테스트) 임시 ID를 만든다.
  // eventData.lat/lng이 있으면 그 좌표를 사용하고, 없으면 카메라 좌표를 사용한다.
  // (주의: anomaly_detection.py의 좌표는 현재 영상 프레임 픽셀 좌표이지 위경도가 아니므로
  //  실제 지도 좌표로는 카메라의 실제 설치 좌표를 사용하는 것이 맞다)
  spawnAtEvent(cameraViewModel, eventData) {
    const trackId = eventData.trackId != null ? String(eventData.trackId) : `#${Math.floor(100 + Math.random() * 900)}`;
    const lat = eventData.lat != null ? eventData.lat : cameraViewModel.lat;
    const lng = eventData.lng != null ? eventData.lng : cameraViewModel.lng;

    this.state = {
      plate: eventData.plate || null, // 없으면 팝업에서 '-'로 표시 (값을 지어내지 않음)
      trackId,
      statusIcon: "🚨",
      statusLabel: eventData.type,
      severity: "alert",
      reason: eventData.reason || "-",
      confidence: eventData.confidence != null ? eventData.confidence : null,
      time: eventData.time,
      currentCameraId: cameraViewModel.id,
      locationName: cameraViewModel.name,
    };
    this.isAlertActive = true;

    if (!this.marker) {
      this.marker = L.marker([lat, lng], { icon: this._createIcon(true), zIndexOffset: 600 }).addTo(
        this.mapManager.getMap()
      );
      this.marker.bindPopup(this.popupManager.buildVehiclePopup(this.state), { closeButton: true });
    } else {
      this.marker.setLatLng([lat, lng]);
      this.marker.setIcon(this._createIcon(true));
      this.marker.setPopupContent(this.popupManager.buildVehiclePopup(this.state));
    }
  }

  // 활성 이상운전 이벤트가 만료되었을 때(EventManager가 호출) pulse만 끄고 마커는 유지한다
  clearAlertState() {
    if (!this.marker || !this.isAlertActive) return;
    this.isAlertActive = false;
    this.marker.setIcon(this._createIcon(false));
  }

  /* ----------------------------------------------------------------
     travelAlongRoad() - Forza 데모(전역 차량 A→B→C→D)의 "이동" 전담 메서드.
     -----------------------------------------------------------------
     [버그 수정] 예전에는 EventManager.advanceDemoRoute()가 "사용자가 CCTV를
     클릭했을 때"만 호출했다 - 이상운전 감지 여부와 무관하게 움직였다. 이제는
     EventManager.triggerDemoEvent()가 "실제로 AI가 이 지점에서 차량을 감지했고,
     그 지점이 이전에 확인된 지점보다 순서상 앞일 때"만 호출한다 - 즉 이동/경로
     확장이 실제 감지 결과를 따라간다.

     travelTo()(직선 2점 보간)와 달리, routeManager.getRoadSegment()가
     돌려주는 "도로를 따라가는 좌표열 전체"를 순서대로 따라가며 애니메이션한다.
     각 구간(두 좌표 사이)의 실제 거리 비율만큼 애니메이션 시간을 배분해서,
     좌표 간격이 촘촘한 구간(커브 등)에서 차량이 부자연스럽게 빨리
     지나가지 않도록 한다.
  ==================================================================== */
  async travelAlongRoad(cameraViewModel, routeManager) {
    const targetLat = cameraViewModel.lat;
    const targetLng = cameraViewModel.lng;

    this.state = {
      plate: null,
      trackId: CONFIG.DEMO_VEHICLE_ID,
      statusIcon: this.isAlertActive ? "🚨" : "🚗",
      statusLabel: this.isAlertActive ? "이상운전 감지" : "이동 중",
      severity: this.isAlertActive ? "alert" : "info",
      reason: this.state ? this.state.reason : "-",
      confidence: null,
      time: new Date().toLocaleTimeString("ko-KR", { hour12: false }),
      currentCameraId: cameraViewModel.id,
      locationName: cameraViewModel.name,
    };

    // 최초 생성(A 클릭 시점): 애니메이션 없이 바로 그 자리에 만들고, trajectory의 첫 점만 찍는다.
    if (!this.marker) {
      this.marker = L.marker([targetLat, targetLng], {
        icon: this._createIcon(this.isAlertActive),
        zIndexOffset: 600,
      }).addTo(this.mapManager.getMap());
      this.marker.bindPopup(this.popupManager.buildVehiclePopup(this.state), { closeButton: true });
      routeManager.addTrajectoryPoint([targetLat, targetLng]);
      return;
    }

    const start = this.marker.getLatLng();
    if (start.lat === targetLat && start.lng === targetLng) {
      this.marker.setPopupContent(this.popupManager.buildVehiclePopup(this.state));
      return; // 이미 그 지점에 있음 - 이동할 필요 없음
    }

    if (this._animFrameId) cancelAnimationFrame(this._animFrameId);

    let pathPoints;
    try {
      pathPoints = await routeManager.getRoadSegment([start.lat, start.lng], [targetLat, targetLng]);
    } catch (err) {
      console.warn("[VEHICLE] 도로 경로를 가져오지 못해 직선으로 대체합니다.", err);
      pathPoints = [[start.lat, start.lng], [targetLat, targetLng]];
    }

    await this._animateAlongPath(pathPoints, routeManager);
  }

  // pathPoints: [[lat,lng], [lat,lng], ...] - 도로 모양을 따라가는 좌표열 (getRoadSegment의 반환값)
  // [버그 수정: "A→B→C→D가 한 번에 순간이동/겹쳐 보이는 문제"] 예전에는 이 메서드가 Promise를
  // 반환하지 않아서, travelAlongRoad()를 여러 번 연달아 await해도 실제로는 애니메이션이 끝나기
  // 전에 곧바로 다음 호출이 시작되어(각 호출 맨 위의 cancelAnimationFrame이 이전 애니메이션을
  // 끊어버림) 중간 구간(B 등)이 화면에 거의 보이지도 않고 건너뛰어지는 것처럼 보였다. 이제
  // "이 구간 애니메이션이 실제로 끝났을 때"만 resolve되는 Promise를 반환해서, 호출부(예:
  // EventManager의 다중 홉 이동)가 A→B 애니메이션이 완전히 끝난 뒤에야 B→C를 시작하도록 만든다.
  _animateAlongPath(pathPoints, routeManager) {
    return new Promise((resolve) => {
      if (!pathPoints || pathPoints.length === 0) {
        resolve();
        return;
      }
      if (pathPoints.length === 1) {
        this.marker.setLatLng(pathPoints[0]);
        routeManager.addTrajectoryPoint(pathPoints[0]);
        this.marker.setPopupContent(this.popupManager.buildVehiclePopup(this.state));
        resolve();
        return;
      }

    const segLengths = [];
    let totalLen = 0;
    for (let i = 1; i < pathPoints.length; i++) {
      const d = haversineMeters(pathPoints[i - 1], pathPoints[i]);
      segLengths.push(d);
      totalLen += d;
    }
    if (totalLen <= 0) totalLen = 1;

    const TOTAL_DURATION_MS = 2700; // [속도 1.5배 감속] 기존 1800ms -> 2700ms(=1800*1.5). 전체 구간(A→B 등) 이동에 걸리는 시간 - 도로가 길든 짧든 항상 동일하게 맞춘다
    let segIdx = 0;
    let lastPointElapsedTotal = 0;
    const overallStart = performance.now();

    const runSegment = () => {
      if (segIdx >= segLengths.length) {
        this.marker.setIcon(this._createIcon(this.isAlertActive));
        this.marker.setPopupContent(this.popupManager.buildVehiclePopup(this.state));
        this._animFrameId = null;
        resolve(); // 이 구간(예: B→C) 애니메이션이 실제로 끝났음을 호출부에 알린다
        return;
      }

      const from = pathPoints[segIdx];
      const to = pathPoints[segIdx + 1];
      const segDuration = Math.max(20, (segLengths[segIdx] / totalLen) * TOTAL_DURATION_MS);
      const segStart = performance.now();

      const step = (now) => {
        const t = Math.min(1, (now - segStart) / segDuration);
        const lat = from[0] + (to[0] - from[0]) * t;
        const lng = from[1] + (to[1] - from[1]) * t;
        this.marker.setLatLng([lat, lng]);

        // 매 프레임 추가하면 점이 지나치게 많아지므로 ~100ms 간격으로만 trajectory에 반영한다
        const elapsedTotal = now - overallStart;
        if (elapsedTotal - lastPointElapsedTotal > 100 || t === 1) {
          routeManager.addTrajectoryPoint([lat, lng]);
          lastPointElapsedTotal = elapsedTotal;
        }

        if (t < 1) {
          this._animFrameId = requestAnimationFrame(step);
        } else {
          segIdx += 1;
          runSegment();
        }
      };
      this._animFrameId = requestAnimationFrame(step);
    };

      runSegment();
    });
  }

  // 이상운전 알람이 발생했을 때(EventManager.triggerDemoEvent) 차량을 움직이지 않고
  // pulse 아이콘/팝업 상태만 갱신한다. 지금 위치에 마커가 없으면 아무것도 하지 않는다
  // (아직 A조차 클릭 안 한 상태에서 알람이 먼저 올 일은 없지만, 방어적으로 처리).
  setAlertStyle(isAlertActive, eventData) {
    this.isAlertActive = isAlertActive;
    if (!this.marker) return;
    if (this.state) {
      this.state = {
        ...this.state,
        statusIcon: isAlertActive ? "🚨" : "🚗",
        statusLabel: isAlertActive ? eventData.type : "이동 중",
        severity: isAlertActive ? "alert" : "info",
        reason: isAlertActive ? eventData.reason || "-" : this.state.reason,
        time: eventData.time || this.state.time,
      };
      this.marker.setPopupContent(this.popupManager.buildVehiclePopup(this.state));
    }
    this.marker.setIcon(this._createIcon(isAlertActive));
  }

  // 활성 이상운전 이벤트가 만료되었을 때(EventManager가 호출) pulse만 끄고 마커는 유지한다
  clearAlertState() {
    if (!this.marker || !this.isAlertActive) return;
    this.setAlertStyle(false, { type: "이동 중", reason: this.state ? this.state.reason : "-" });
  }

  /* ----------------------------------------------------------------
     setPositionForDemo() - [신규] 영상 duration 기반 이동 전담 메서드.
     -----------------------------------------------------------------
     travelAlongRoad()(도로 경로를 fetch하고 고정된 시간(TOTAL_DURATION_MS) 동안
     자체 애니메이션하는 방식)와 달리, 이 메서드는 "지금 이 좌표로 마커를 즉시
     옮기기만" 한다 - 실제 애니메이션 효과는 EventManager.updateDemoStageProgress가
     Forza 영상의 timeupdate 이벤트마다(=영상 재생 그 자체의 실시간 흐름) 이 메서드를
     계속 호출해주는 것으로 자연스럽게 만들어진다. 즉 "영상이 재생되는 시간 = 차량이
     이동하는 시간"이라는 요구사항을 구현하기 위한 저수준 함수다. OSRM 호출이나 자체
     rAF 루프가 전혀 없다 - 그건 EventManager 쪽에서 경로를 한 번만 계산해 캐싱한다.
  ==================================================================== */
  setPositionForDemo(latlng, cameraViewModelForContext) {
    const [lat, lng] = latlng;
    this.state = {
      plate: null,
      trackId: CONFIG.DEMO_VEHICLE_ID,
      statusIcon: this.isAlertActive ? "🚨" : "🚗",
      statusLabel: this.isAlertActive ? "이상운전 감지" : "이동 중",
      severity: this.isAlertActive ? "alert" : "info",
      reason: this.state ? this.state.reason : "-",
      confidence: null,
      time: new Date().toLocaleTimeString("ko-KR", { hour12: false }),
      currentCameraId: cameraViewModelForContext.id,
      locationName: cameraViewModelForContext.name,
    };

    if (!this.marker) {
      this.marker = L.marker([lat, lng], { icon: this._createIcon(this.isAlertActive), zIndexOffset: 600 }).addTo(
        this.mapManager.getMap()
      );
      this.marker.bindPopup(this.popupManager.buildVehiclePopup(this.state), { closeButton: true });
    } else {
      this.marker.setLatLng([lat, lng]);
      this.marker.setPopupContent(this.popupManager.buildVehiclePopup(this.state));
    }
  }

  // 데모 리허설 리셋용 - 마커 자체를 지도에서 제거하고 처음 상태로 되돌린다.
  reset() {
    if (this._animFrameId) cancelAnimationFrame(this._animFrameId);
    this._animFrameId = null;
    if (this.marker) {
      this.mapManager.getMap().removeLayer(this.marker);
      this.marker = null;
    }
    this.state = null;
    this.isAlertActive = false;
  }
}

/* ==================================================================
   8) UIManager - 헤더 통계 / 실시간 시계 / 다크·라이트 테마
================================================== */
class UIManager {
  constructor(themeButtonEl, themeIconEl, themeLabelEl, clockEl, statusEl) {
    this.statusEl = statusEl;
    this.clockEl = clockEl;
    this.lastUpdateTime = "-";

    this.root = document.documentElement;
    this.theme = CONFIG.DEFAULT_THEME;
    this._themeIconEl = themeIconEl;
    this._themeLabelEl = themeLabelEl;
    themeButtonEl.addEventListener("click", () => this._toggleTheme());
    this._applyTheme();

    this._tickClock();
    setInterval(() => this._tickClock(), 1000);
  }

  setLastUpdate(time) {
    this.lastUpdateTime = time || this._nowString();
  }

  updateHeaderStats({ cameraCount = 0, trackedVehicleCount = 0, alertVehicleCount = 0, alertDetectionCount = 0 } = {}) {
    this.statusEl.innerHTML = `
      <span class="status-chip status-chip--alert-count">
        <span class="status-chip__icon">🚨</span>
        이상 감지 <strong>${alertDetectionCount}</strong>
      </span>
      <span class="status-chip">
        <span class="status-chip__icon">📹</span>
        연결 CCTV <strong>${cameraCount.toLocaleString()}대</strong>
      </span>
      <span class="status-chip">
        <span class="status-chip__icon">🚗</span>
        추적 차량 <strong>${trackedVehicleCount}대</strong>
      </span>
      <span class="status-chip status-chip--alert-count">
        <span class="status-chip__icon">⚠️</span>
        이상 차량 <strong>${alertVehicleCount}대</strong>
      </span>
    `;
  }

  _toggleTheme() {
    this.theme = this.theme === "dark" ? "light" : "dark";
    this._applyTheme();
  }

  _applyTheme() {
    this.root.setAttribute("data-theme", this.theme);
    this._themeIconEl.textContent = this.theme === "dark" ? "🌙" : "☀️";
    this._themeLabelEl.textContent = this.theme === "dark" ? "DARK" : "LIGHT";
  }

  _tickClock() {
    const now = new Date();
    const hh = String(now.getHours()).padStart(2, "0");
    const mm = String(now.getMinutes()).padStart(2, "0");
    const ss = String(now.getSeconds()).padStart(2, "0");
    this.clockEl.textContent = `${hh}:${mm}:${ss}`;
  }

  _nowString() {
    const now = new Date();
    const hh = String(now.getHours()).padStart(2, "0");
    const mm = String(now.getMinutes()).padStart(2, "0");
    const ss = String(now.getSeconds()).padStart(2, "0");
    return `${hh}:${mm}:${ss}`;
  }
}

/* ==================================================================
   9) ToastManager - 발표용 AI 이벤트 토스트 알림
   -------------------------------------------------------------
   AI 이벤트가 발생하면 지도 중앙 상단에 "🚨 AI 이벤트 감지" 알림을 띄우고
   3초 뒤 자동으로 사라진다. 여러 건이 연속으로 들어와도 위아래로 쌓인다.
================================================== */
class ToastManager {
  constructor(containerEl) {
    this.containerEl = containerEl;
  }

  show(cameraViewModel, eventData) {
    if (!this.containerEl) return;

    const el = document.createElement("div");
    el.className = "ai-toast";
    el.innerHTML = `
      <div class="ai-toast__title">🚨 AI 이벤트 감지</div>
      <div class="ai-toast__location">${cameraViewModel.location} 부근</div>
      <div class="ai-toast__plate">차량번호 : ${eventData.plate}</div>
    `;

    this.containerEl.appendChild(el);
    setTimeout(() => el.remove(), 3000);
  }
}

/* ==================================================================
   9B) ForzaBackgroundAnalyzer - Forza A/B/C/D를 화면 표시 여부와 무관하게
   항상 백그라운드에서 분석한다.
   -------------------------------------------------------------
   [요구사항 1] 예전에는 VideoManager._attachBoxOverlay가 "지금 실제로 화면에
   보이고 있는 영상"에 대해서만 사전 분석된 episode를 재생 시점 기준으로
   흘려보냈다. 즉 관제자가 C를 보고 있으면 A/B/D는 전혀 분석되지 않는 것과
   같았다. 이 클래스는 4개의 사전 분석 track log(export_forza_track_logs.py가
   만든 forza-track-log-*.json)를 전부 미리 불러온 뒤, 소스마다 독립적인
   "가상 재생 시계"를 둔다. 이 시계는 실제 <video> 재생 여부와 무관하게
   performance.now() 기준으로 흐르고, 영상 길이(duration)를 넘으면 처음으로
   되돌아가는(loop) 것까지 흉내낸다. 그래서 화면에 뭐가 보이든 4개 모두의
   episode가 정확한 타이밍에 발화된다.

   실제 화면에 그 영상이 보일 때 나오는 "박스 그리기"(VideoManager._renderBoxOverlay)와는
   완전히 별개다 - 이 클래스는 오직 "언제 이상운전으로 판단됐는가"만 감지해서
   콜백(onEpisode)을 부를 뿐, 화면에 아무것도 그리지 않는다.
================================================== */
class ForzaBackgroundAnalyzer {
  constructor(demoCameraIdMap, forzaDemoSources) {
    this.demoCameraIdMap = demoCameraIdMap; // CONFIG.DEMO_CAMERA_ID_MAP: {A: 'L010111', ...}
    this.forzaDemoSources = forzaDemoSources; // CONFIG.FORZA_DEMO_SOURCES
    this.sources = new Map(); // camId -> { trackLog, durationSec, firedCount, startTime, _prevVirtualT }
    this.onEpisode = null; // (camId, episode) => void - init 블록에서 연결
    this._intervalId = null;
  }

  async start() {
    const camIds = Object.values(this.demoCameraIdMap);

    await Promise.all(
      camIds.map(async (camId) => {
        const source = this.forzaDemoSources[camId];
        if (!source) return;
        try {
          const res = await fetch(source.trackLogUrl, { cache: "no-store" });
          if (!res.ok) throw new Error(`status ${res.status}`);
          const trackLog = await res.json();
          const durationSec =
            trackLog.fps && trackLog.frame_count ? trackLog.frame_count / trackLog.fps : 30;

          this.sources.set(camId, {
            trackLog,
            durationSec,
            firedCount: 0,
            // [요구사항 1/3: 20초 정상 관제] replay clock의 "0초 시점"을 지금이 아니라
            // 지금+FORZA_DEMO_START_DELAY_MS로 잡는다. _tick()이 이 시각 이전에는 아예
            // 아무것도 하지 않으므로, JSON을 이미 다 읽어 메모리에 들고 있어도 20초 동안은
            // 어떤 episode도 발화되지 않는다(요구사항 2: "JSON을 읽었다" ≠ "이벤트 발생").
            // 23.38초를 직접 박아넣지 않고 "20초 지연 + 실제 anomaly timestamp(예: A의
            // 3.375초)"가 자연스럽게 더해지도록 하는 것이 핵심이다.
            startTime: performance.now() + CONFIG.FORZA_DEMO_START_DELAY_MS,
            _prevVirtualT: null,
          });
          console.log(
            `[FORZA BG] ${camId} 백그라운드 분석 시작 (episode ${trackLog.episodes.length}건, 길이 ${durationSec.toFixed(1)}s)`
          );
        } catch (err) {
          console.warn(`[FORZA BG] ${camId} track log 로드 실패 - 이 소스는 백그라운드 분석에서 제외됩니다:`, err);
        }
      })
    );

    this._intervalId = setInterval(() => this._tick(), 250);
  }

  _tick() {
    const now = performance.now();
    this.sources.forEach((state, camId) => {
      // [요구사항 1] 아직 20초 대기(정상 관제) 구간이면 이 소스의 replay clock은 시작되지도
      // 않은 것으로 취급한다 - virtualT 계산도, episode 발화도 전혀 하지 않는다.
      if (now < state.startTime) return;

      const elapsedSec = (now - state.startTime) / 1000;
      const virtualT = state.durationSec > 0 ? elapsedSec % state.durationSec : elapsedSec;

      // loop 감지: 가상 시계가 이전 tick보다 줄어들었으면 한 바퀴 돈 것 - firedCount를
      // 리셋해서 다음 바퀴에도 같은 episode들이 (실제 영상 loop와 동일하게) 다시 발화되게 한다.
      if (state._prevVirtualT != null && virtualT < state._prevVirtualT - 0.25) {
        state.firedCount = 0;
      }
      state._prevVirtualT = virtualT;

      const episodes = state.trackLog.episodes || [];
      let count = 0;
      while (count < episodes.length && episodes[count].t <= virtualT) count += 1;

      if (count > state.firedCount) {
        for (let i = state.firedCount; i < count; i += 1) {
          if (this.onEpisode) this.onEpisode(camId, episodes[i]);
        }
      }
      state.firedCount = count;
    });
  }

  stop() {
    if (this._intervalId) clearInterval(this._intervalId);
    this._intervalId = null;
  }
}

/* ==================================================================
   9C) ForzaDemoTimeline - [신규] 영상 duration 기반 DEMO timeline
   -------------------------------------------------------------
   [구조 변경] 예전(ForzaBackgroundAnalyzer)에는 A/B/C/D 4개의 "가상 시계"가
   전부 실제 시간(performance.now()) 기준으로 병렬로 돌았고, 차량 이동은 각
   지점의 track log에 적힌 anomaly timestamp에 anomaly가 "감지"될 때만
   일어났다. 이번 요구사항은 다르다: "A 영상의 실제 재생 시간 = A→B 이동
   시간"이다 - 즉 이동 시간의 기준이 JSON의 anomaly 시각이 아니라 mp4 파일
   자체의 실제 duration이어야 한다.

   그래서 이 클래스는 화면에는 보이지 않는 <video> 엘리먼트 하나를 만들어
   forza_A.mp4 → forza_B.mp4 → forza_C.mp4 → forza_D.mp4를 순서대로(자동으로)
   재생한다. 사용자가 실제로 어떤 CCTV를 보고 있는지와 완전히 무관하게 항상
   진행된다(요구사항 4/10/12: currentSelectedCamera와 분리). video.duration/
   currentTime/timeupdate/ended 이벤트만으로 동작하고, setTimeout으로 영상
   길이를 하드코딩하지 않는다(요구사항 1/14) - 영상 길이가 바뀌면 코드 수정 없이
   자동으로 반영된다.

   anomaly 감지(요구사항 11: "A 영상 기준 약 3.38초에 최초 이상운전")도 이제
   이 클래스가 currentTime 기준으로 직접 처리한다 - track log의 episodes[].t는
   원래 "그 영상의 몇 초 지점"인지를 나타내는 값이라 video.currentTime과
   자연스럽게 같은 시간축이다.
================================================== */
/* ==================================================================
   9C) ForzaDemoTimeline - 영상 duration 기반 DEMO timeline (재생 비의존형)
   -------------------------------------------------------------
   [버그 수정 - 이 버전에서 변경됨] 처음에는 화면에 보이지 않는(display:none)
   <video>를 실제로 계속 재생시켜서 그 video의 timeupdate/ended 이벤트로
   stage 전환을 트리거했다. 그런데 display:none인 <video>는 브라우저(특히
   Safari 계열, 최신 Chrome 일부 정책 포함)가 실제 디코딩/재생을 계속 보장해
   주지 않는 경우가 있어서, play()는 성공한 것처럼 보여도 timeupdate/ended가
   전혀 발생하지 않거나 중간에 멈추는 문제가 있었다 - 그래서 A stage에서
   더 이상 진행이 안 되는 것처럼 보인 것으로 추정된다.

   그래서 "실제로 계속 재생되는 영상"에 의존하는 구조를 걷어냈다. 이제는:
   1) 4개 영상의 duration만 각각 한 번 읽어온다(재생하지 않고 메타데이터만
      읽는 <video preload="metadata"> probe - 실제 재생 여부와 무관하게
      안정적으로 동작한다).
   2) 그 duration 값을 그대로 "이 stage에 걸리는 시간"으로 써서, 순수
      performance.now() 기반 가상 시계 + setTimeout(duration*1000)으로
      stage를 자동 전환한다. video.ended 이벤트에는 더 이상 의존하지 않는다.

   여전히 "A 영상의 실제 재생 시간 = A→B 이동 시간"이라는 핵심 요구사항은
   그대로 지킨다 - 다만 "실제 재생하면서 지켜보는" 대신 "실제 길이를 한 번
   읽어서 그 길이만큼 타이머를 돌리는" 방식으로 더 안정적으로 구현했다.
================================================== */
class ForzaDemoTimeline {
  constructor(demoCameraIdMap, forzaDemoSources) {
    this.demoCameraIdMap = demoCameraIdMap; // CONFIG.DEMO_CAMERA_ID_MAP: {A:'L010111', ...}
    this.forzaDemoSources = forzaDemoSources; // CONFIG.FORZA_DEMO_SOURCES
    this.stageOrder = ["A", "B", "C", "D"];
    this.currentStageIndex = -1; // -1 = 아직 DEMO 시작 전(20초 대기 중)
    this._stageAnomalyFiredIndex = 0;
    this._anomalyEpisodesCache = new Map(); // demoId -> episodes[]
    this._stageDurations = new Map(); // demoId -> 실제로 확인된 영상 길이(초) - VideoManager 동기화용
    this._stageStartAt = null; // performance.now() 시점 - 지금 stage가 시작된 실제 시각(가상 시계 기준점)
    this._tickIntervalId = null;
    this._advanceTimeoutId = null;
    this._finished = false;

    // 콜백 (init 블록에서 EventManager와 VideoManager에 연결)
    this.onStageStart = null; // (demoId, realCamId) => void
    this.onProgress = null; // (demoId, progress[0..1], currentTime, duration) => void
    this.onStageEnd = null; // (demoId, realCamId) => void - 다음 stage로 넘어가기 직전
    this.onAnomaly = null; // (demoId, realCamId, episode) => void
    this.onFinished = null; // () => void - D까지 전부 끝남
  }

  _currentDemoId() {
    return this.stageOrder[this.currentStageIndex] || null;
  }

  // <video preload="metadata">로 실제 재생 없이 duration만 읽어온다. 화면에 붙이지 않고
  // 즉시 버리므로 display:none 관련 재생 중단 문제와 무관하다.
  _probeDuration(videoUrl) {
    return new Promise((resolve, reject) => {
      const probe = document.createElement("video");
      probe.preload = "metadata";
      probe.muted = true;

      const cleanup = () => {
        probe.removeEventListener("loadedmetadata", onLoaded);
        probe.removeEventListener("error", onError);
        probe.src = "";
      };
      const onLoaded = () => {
        const duration = probe.duration;
        cleanup();
        if (!isFinite(duration) || duration <= 0) reject(new Error(`유효하지 않은 duration(${duration})`));
        else resolve(duration);
      };
      const onError = () => {
        const err = probe.error;
        cleanup();
        reject(err || new Error("video 메타데이터 로딩 실패"));
      };

      probe.addEventListener("loadedmetadata", onLoaded, { once: true });
      probe.addEventListener("error", onError, { once: true });
      probe.src = videoUrl;
      probe.load();
    });
  }

  // 사이트 시작 후 CONFIG.FORZA_DEMO_START_DELAY_MS(20초)만큼 기다렸다가 시작한다.
  // (요구사항: "20초 delay"와 "영상 duration"은 완전히 분리된 값)
  start() {
    setTimeout(() => this._begin(), CONFIG.FORZA_DEMO_START_DELAY_MS);
  }

  // A/B/C/D 4개 영상의 실제 길이를 전부 미리 읽어온 뒤 A부터 시작한다.
  async _begin() {
    for (const demoId of this.stageOrder) {
      if (this._stageDurations.has(demoId)) continue;
      const realCamId = this.demoCameraIdMap[demoId];
      const source = this.forzaDemoSources[realCamId];
      if (!source) {
        console.error(`[DEMO ${demoId}] CONFIG.FORZA_DEMO_SOURCES에 ${realCamId} 항목이 없습니다.`);
        continue;
      }
      try {
        const duration = await this._probeDuration(source.videoUrl);
        this._stageDurations.set(demoId, duration);
        console.log(`[DEMO ${demoId}] 실제 영상 길이 확인: ${duration.toFixed(2)}s - 이 시간이 그대로 ${demoId}→다음 지점 이동 시간이 됩니다.`);
      } catch (err) {
        // [요구사항: 오류 처리] duration을 못 읽으면 이 stage는 진행하지 않고 콘솔에만 남긴다.
        console.error(`[DEMO ${demoId}] video duration 확인 실패 - 이 stage는 타이밍을 계산할 수 없습니다.`, err);
      }
    }
    this._advanceToStage(0);
  }

  async _advanceToStage(index) {
    if (index >= this.stageOrder.length) {
      this._finished = true;
      console.log("[DEMO] A~D 이동이 모두 끝났습니다 - DEMO 종료.");
      if (this.onFinished) this.onFinished();
      return;
    }

    const demoId = this.stageOrder[index];
    const duration = this._stageDurations.get(demoId);
    if (!duration) {
      console.error(`[DEMO ${demoId}] duration을 확인하지 못해 이 stage로 진행하지 않습니다(DEMO가 여기서 멈춥니다).`);
      return;
    }

    this.currentStageIndex = index;
    const realCamId = this.demoCameraIdMap[demoId];
    const source = this.forzaDemoSources[realCamId];

    // 이 stage의 anomaly episode(track log)를 미리 fetch해 둔다 - "JSON 로딩"과 "이벤트
    // 발생"은 여기서도 분리되어 있다: fetch는 여기서 하지만, 알림은 아래 _tick()이 실제
    // 가상 재생 시각이 그 timestamp를 지날 때만 만든다.
    if (!this._anomalyEpisodesCache.has(demoId) && source && source.trackLogUrl) {
      try {
        const res = await fetch(source.trackLogUrl, { cache: "no-store" });
        const trackLog = await res.json();
        this._anomalyEpisodesCache.set(demoId, trackLog.episodes || []);
      } catch (err) {
        console.warn(`[DEMO ${demoId}] track log 로드 실패 - 이 stage는 anomaly 감지 없이 진행합니다.`, err);
        this._anomalyEpisodesCache.set(demoId, []);
      }
    }
    this._stageAnomalyFiredIndex = 0;
    this._stageStartAt = performance.now();

    if (this.onStageStart) this.onStageStart(demoId, realCamId);

    if (this._tickIntervalId) clearInterval(this._tickIntervalId);
    this._tickIntervalId = setInterval(() => this._tick(), 100);

    // [요구사항: video.ended 자동전환 제거] 더 이상 실제 영상 재생/ended 이벤트에
    // 의존하지 않는다. duration을 이미 알고 있으므로, 그 시간이 지나면 곧바로 다음
    // stage로 넘어간다 - "영상 길이만큼 시간이 흐르면 자동 전환"이라는 결과는 동일하게
    // 유지하면서, 실제 재생 성공 여부(디코딩/자동재생 정책 등)에 기대지 않는다.
    if (this._advanceTimeoutId) clearTimeout(this._advanceTimeoutId);
    this._advanceTimeoutId = setTimeout(() => this._finishStage(), duration * 1000);
  }

  _tick() {
    const demoId = this._currentDemoId();
    if (!demoId) return;
    const duration = this._stageDurations.get(demoId);
    if (!duration) return;

    const currentTime = Math.min(duration, (performance.now() - this._stageStartAt) / 1000);
    const progress = Math.min(1, Math.max(0, currentTime / duration));
    const realCamId = this.demoCameraIdMap[demoId];

    // anomaly 체크: 이 stage의 episodes 중 currentTime을 지난 것들을 순서대로 발화한다.
    // (요구사항: A는 약 3.38초에서 최초 발화 - JSON을 "읽은 시점"이 아니라 가상 재생
    // 시각 기준.) B/C/D에도 episode가 있을 수 있지만, EventManager의 게이트가 "A에서만
    // 새 알림을 연다"를 강제하므로 여기서는 그냥 전달만 하면 된다.
    const episodes = this._anomalyEpisodesCache.get(demoId) || [];
    while (
      this._stageAnomalyFiredIndex < episodes.length &&
      episodes[this._stageAnomalyFiredIndex].t <= currentTime
    ) {
      const episode = episodes[this._stageAnomalyFiredIndex];
      this._stageAnomalyFiredIndex += 1;
      if (this.onAnomaly) this.onAnomaly(demoId, realCamId, episode);
    }

    if (this.onProgress) this.onProgress(demoId, progress, currentTime, duration);
  }

  // duration만큼의 시간이 흘렀을 때(setTimeout) 호출된다. 이 함수 하나가 (1) 차량을
  // 다음 CCTV의 정확한 좌표로 스냅하고 (2) 곧바로 다음 stage로 넘어가는 것까지 같은
  // 흐름 안에서 처리한다 - "시간 경과"와 "차량 도착"이 분리된 두 트리거가 아니라
  // 하나의 타이머 콜백이다.
  _finishStage() {
    if (this._tickIntervalId) {
      clearInterval(this._tickIntervalId);
      this._tickIntervalId = null;
    }
    const demoId = this._currentDemoId();
    const realCamId = this.demoCameraIdMap[demoId];
    if (this.onStageEnd) this.onStageEnd(demoId, realCamId);
    this._advanceToStage(this.currentStageIndex + 1);
  }

  // [요구사항] 사용자가 currentSelectedCamera를 이 데모 지점으로 바꿨을 때, "처음부터"가
  // 아니라 "지금 DEMO timeline이 실제로 있는 지점"부터 보여주기 위한 값을 계산해서 준다.
  // - 아직 시작 안 한 미래 stage: 0초부터
  // - 이미 지나간 stage: 그 stage의 마지막(=duration) 시점
  // - 지금 진행 중인 stage: 가상 시계 기준 현재 경과 시간
  getSyncCurrentTime(demoId) {
    const idx = this.stageOrder.indexOf(demoId);
    if (idx < 0) return 0;
    if (idx < this.currentStageIndex) return this._stageDurations.get(demoId) || 0;
    if (idx === this.currentStageIndex) {
      const duration = this._stageDurations.get(demoId) || 0;
      if (!this._stageStartAt) return 0;
      return Math.min(duration, (performance.now() - this._stageStartAt) / 1000);
    }
    return 0;
  }

  // 콘솔에서 발표 리허설을 다시 시작할 때 호출 (EventManager.resetDemoSession이 함께 호출).
  reset() {
    if (this._tickIntervalId) clearInterval(this._tickIntervalId);
    if (this._advanceTimeoutId) clearTimeout(this._advanceTimeoutId);
    this._tickIntervalId = null;
    this._advanceTimeoutId = null;
    this.currentStageIndex = -1;
    this._stageStartAt = null;
    this._finished = false;
    this._anomalyEpisodesCache.clear();
    // duration은 다시 읽을 필요 없으므로(영상 파일 자체는 안 바뀜) 그대로 재사용한다.
    this.start();
  }
}

/* ==================================================================
   10) EventManager - AI 이벤트의 유일한 진입점
   -------------------------------------------------------------
   triggerAiEvent() 하나가 다음 순서를 그대로 실행한다.
   ① 이벤트 카드 생성 ② 지도 FlyTo ③ CCTV 자동 선택 ④ Popup 자동 Open
   ⑤ 영상 자동 전환 ⑥ 차량 Marker 생성 ⑦ 이동 경로 생성 ⑧ 상단 통계 증가
   (+ 발표용 토스트 알림)

   통계는 두 가지를 구분해서 관리한다.
   - alertDetectionCount("이상 감지"): 누적 총 감지 횟수. 절대 감소하지 않는다.
   - alertVehicleCount("이상 차량"): 지금 활성 상태인 이상운전 차량 수(track_id 기준).
     Python이 별도의 "해제" 신호를 보내지 않으므로, 이벤트 수신 후
     CONFIG.ANOMALY_ACTIVE_MS 동안 활성으로 간주하고 시간이 지나면 자동으로 해제한다.
     같은 track_id의 이벤트가 다시 들어오면 타이머가 연장된다.
================================================== */
class EventManager {
  // cameraManager: setAlert/selectById/getRecordCount 인터페이스를 구현한 매니저.
  // 지금은 uticCameraManager가 전달된다(과거에는 trafficCameraManager였음). UticCameraManager가
  // 같은 인터페이스를 구현하고 있어서 이 클래스 내부 로직은 바꿀 필요가 없었다.
  constructor(cameraManager, vehicleManager, uiManager, routeManager, toastManager, videoSourceRegistry) {
    this.cameraManager = cameraManager;
    this.vehicleManager = vehicleManager;
    this.uiManager = uiManager;
    this.routeManager = routeManager;
    this.toastManager = toastManager;
    this.videoSourceRegistry = videoSourceRegistry;

    this.log = []; // 최신이 배열 맨 앞에 오도록 unshift 사용
    this.alertDetectionCount = 0; // 누적 "사건(episode)" 수 - 프레임/재감지 단위가 아니라 NONE→ACTIVE 전이 횟수
    this.trackedVehicleCount = 0; // 지금까지 차량 마커가 한 번이라도 생성됐는지 (0 또는 1)
    this.activeTracks = new Map(); // track_id -> { camId, timerId } - 지금 활성 상태인 이상운전 차량들

    // ---- 요구사항 2/14: currentSelectedCamera / vehicleCurrentCamera 분리 ----
    // currentSelectedCamera: 사용자가 "지금 보고 있는" CCTV (클릭/검색/알림 클릭으로만 바뀜)
    // vehicleCurrentCamera : DEMO 차량이 "지금 실제로 있는" CCTV
    // 이 둘은 절대 서로의 값을 대신 바꾸지 않는다 - 클릭이 차량을 움직이지 않고,
    // DEMO 진행이 화면을 강제로 바꾸지 않는다. currentSelectedCamera는 uticCameraManager.onCameraSelected에서,
    // vehicleCurrentCamera는 이 클래스의 completeDemoStageMovement()에서만 갱신된다.
    this.currentSelectedCamera = null;

    // [구조 변경] 예전에는 vehicleCurrentCamera/demoSequenceIndex가 "이상운전 Episode" 객체
    // 안에 있었다 - 즉 알림(A anomaly)이 떠야만 차량이 움직일 수 있는 구조였다. 이제는 영상
    // duration 기반으로 차량이 사이트 시작+20초 시점(A 영상 시작)부터 곧바로 움직이기
    // 시작하고, 알림은 그 movement 도중 "우연히" A 영상 3.38초 지점을 지날 때 별도로 뜨는
    // 것이므로 - 이동 상태와 알림 상태를 완전히 분리된 필드로 관리한다.
    this.vehicleCurrentCamera = null; // DEMO 차량이 지금 실제로 있는 CCTV(real cam_id). null = 아직 DEMO 시작 전
    this.demoSequenceIndex = -1; // A=0,B=1,C=2,D=3 - 지금까지 확인된 가장 앞선 지점의 순번
    this._demoMovement = null; // 지금 진행 중인 구간(A→B 등)의 도로 경로 캐시 - beginDemoStageMovement() 참고

    // ---- Forza 데모 전용 "알림(이벤트 카드)" 상태 ----
    // [버그 수정] 예전엔 6초 무재감지 시 RESOLVED로 풀렸다가 다시 감지되면 새 카드를 또
    // 만들 수 있었다 - A 영상 안에서도 anomaly가 3.38초/12.4초/23.1초 세 번 나오는데, 그
    // 간격이 6초보다 벌어질 수 있어 "A에서도 카드가 2개 생기는" 위험이 있었다. 이제는
    // globalVehicleId 하나당 "이 데모 세션에서 알림을 이미 만들었는가"만 본다 - 한 번
    // 만들어지면 페이지를 새로고침하기 전까지 다시 만들어지지 않는다(요구사항: "최초
    // 이벤트는 보라매역에서 단 1개만").
    // key: globalVehicleId, value: { firstDetectedAt, firstDetectedCamera(=anomalyEvent.location,
    //                                절대 다시 바뀌지 않음), logEntry }
    this.demoEpisodes = new Map();

    // A→B→C→D의 진행 방향을 판단하기 위한 순서표.
    this.demoOrder = ["A", "B", "C", "D"];

    this.listEl = document.getElementById("event-list");
    this.emptyEl = document.getElementById("event-empty");
    this.countEl = document.getElementById("event-count");
  }

  // ---- 실시간 연동의 유일한 진입점 ----
  // record: UTIC 카메라 원본 레코드 (cam_id/name/lat/lng/center_name 필드를 담은 객체)
  // eventData.trackId가 있으면 활성 이벤트 관리(중복 방지/자동 해제)에 사용된다.
  triggerAiEvent(record, eventData) {
    const cameraViewModel = buildUticCameraViewModel(record, this.videoSourceRegistry);
    const normalized = Object.assign({ icon: "🚨", severity: "alert" }, eventData);
    const trackKey = eventData.trackId != null ? String(eventData.trackId) : null;

    // 발표용 토스트 알림 (🚨 AI 이벤트 감지 / 위치 / 차량번호) - 3초 후 자동 소멸
    if (this.toastManager) this.toastManager.show(cameraViewModel, normalized);

    // ① 이벤트 카드 생성
    this.log.unshift({ camera: cameraViewModel, event: normalized });
    this.renderPanel();

    // ② 지도 FlyTo + ③ CCTV 자동 선택 + ④ Popup 자동 Open + ⑤ 영상 자동 전환
    // (이미 같은 카메라가 선택/재생 중이면 VideoManager가 알아서 아무것도 건드리지 않는다 = 영상 끊김 없음)
    this.cameraManager.setAlert(cameraViewModel.id, true);
    this.cameraManager.selectById(cameraViewModel.id, { openPopup: true, zoom: true, switchVideo: true });

    // ⑥ 차량 Marker 생성 (빨간 pulse로 강조)
    this.vehicleManager.spawnAtEvent(cameraViewModel, eventData);
    this.trackedVehicleCount = 1;

    // ⑦ 이동 경로(Line) 생성
    this.routeManager.showPath(buildApproachPath(cameraViewModel.lat, cameraViewModel.lng, cameraViewModel.id));

    // ⑧ 상단 통계: 누적 감지는 항상 +1, "활성 차량"은 track_id 기준으로 관리
    this.alertDetectionCount += 1;
    this._markTrackActive(trackKey, cameraViewModel.id);

    this.uiManager.setLastUpdate(eventData.time);
    this.updateStats();
  }

  /* ----------------------------------------------------------------
     [비활성화됨] advanceDemoRoute() - 예전에는 "사용자가 CCTV를 클릭하는
     순서"로 차량 이동/경로를 결정했다. 이게 정확히 버그였다 - 이동 경로가
     실제 이상운전 감지 여부와 무관하게 클릭만으로 결정되고 있었다.
     이제 경로 확장은 triggerDemoEvent() 안에서, 실제로 AI가 그 지점에서
     차량을 감지했을 때만 이루어진다. 이 메서드는 콘솔 수동 테스트용으로만
     남겨뒀고, 초기화부(uticCameraManager.onCameraSelected)에서 더 이상
     자동으로 호출하지 않는다.
  ==================================================================== */
  advanceDemoRoute(demoRealCamId) {
    console.warn(
      "[DEMO] advanceDemoRoute()는 더 이상 자동으로 호출되지 않습니다. " +
        "이동 경로는 이제 triggerDemoEvent()가 실제 감지 시점에만 확장합니다."
    );
  }

  // ---- Forza 데모의 "이상운전 알람 + 경로 확장" 전담 진입점 ----
  // [버그 수정 1: 이벤트 중복] global_vehicle_id 기준 NONE/ACTIVE/RESOLVED 상태머신으로
  // 관리한다. NONE(또는 RESOLVED) → ACTIVE로 "처음" 전이할 때만 이벤트 카드/토스트를
  // 새로 만든다. 이미 ACTIVE인 동안 같은 차량이 계속(또는 같은 지점에서 반복) 감지돼도
  // 새 카드를 만들지 않고, 지점이 바뀐 경우에만 기존 카드의 위치 정보를 갱신한다.
  //
  // [버그 수정 3: 경로 연결] 이동 경로(travelAlongRoad)는 여기, 즉 "실제로 이 지점에서
  // 차량이 감지된 순간"에만 확장한다. A→B→C→D 순서표(this.demoOrder)로 "이번에 감지된
  // 지점이 지금까지 이 Episode에서 확인된 마지막 지점보다 순서상 앞으로 갔는지"만
  // 확인해서, 앞으로 간 경우에만 도로 기반 경로를 이어 붙인다. 뒤로 가는 재감지(예:
  // D 도달 후 다시 A에서 감지)는 카드/알람 상태는 갱신하되 경로는 절대 늘리지 않는다
  // (요구사항: "D→A 자동 연결 금지").
  //
  // [화면 강제 전환 방지] zoom:false, switchVideo:false, openPopup:false로 호출한다 -
  // 사용자가 다른 CCTV를 보고 있어도 화면을 강제로 바꾸지 않고 알림만 표시한다.
  // 사용자가 이벤트 카드를 "클릭"했을 때만(renderPanel의 클릭 핸들러) 실제로 해당
  // CCTV로 화면이 이동한다.
  //
  // demoRealCamId: 이 데모 지점의 좌표를 빌려온 실제 UTIC cam_id
  //                (CONFIG.DEMO_CAMERA_ID_MAP / FORZA_DEMO_SOURCES 참고).
  //
  // [구조 변경: 영상 duration 기반 재설계] 예전에는 이 함수가 "알림 카드 생성"과
  // "차량 이동/Polyline 확장"을 동시에 담당했다 - anomaly가 감지된 지점으로 차량이
  // "점프"하는 구조였다. 이제 차량 이동은 ForzaDemoTimeline이 각 영상의 실제 재생
  // 진행률(currentTime/duration)에 맞춰 별도로(beginDemoStageMovement/
  // updateDemoStageProgress/completeDemoStageMovement) 처리하므로, 이 함수는 순수하게
  // "이상운전 알림(이벤트 카드)"만 담당한다.
  triggerDemoEvent(demoRealCamId, eventData) {
    const record = this.cameraManager.getRecordById(demoRealCamId);
    if (!record) {
      console.warn(`triggerDemoEvent: cam_id(${demoRealCamId})를 UTIC CCTV 목록에서 찾을 수 없습니다.`);
      return;
    }
    const cameraViewModel = buildUticCameraViewModel(record, this.videoSourceRegistry);
    const normalized = Object.assign({ icon: "🎮", severity: "alert" }, eventData);
    const globalVehicleId = eventData.globalVehicleId;

    if (!globalVehicleId) {
      console.warn("triggerDemoEvent: globalVehicleId가 없어 알림을 관리할 수 없습니다 - 무시합니다.", eventData);
      return;
    }

    // [버그 수정: "A 안에서도 카드가 2개 생기는 문제"] 예전에는 "6초 동안 재감지가
    // 없으면 RESOLVED로 풀렸다가 다시 감지되면 새 카드"였다. 그런데 A 영상 자체의
    // anomaly가 3.38초/12.4초/23.1초처럼 6초보다 넓게 벌어져 있어서, A 안에서도
    // 두 번째 카드가 또 생길 위험이 있었다. 이제는 "이 데모 세션에서 이 차량으로
    // 알림을 이미 만든 적이 있는가"만 본다 - 한 번 만들어지면 페이지를 새로고침하기
    // 전까지 절대 다시 만들어지지 않는다.
    const isNewEpisode = !this.demoEpisodes.has(globalVehicleId);

    // [버그 수정: "D가 먼저 뜨는 문제"] 새 알림(사건)은 오직 데모 시작 지점(this.demoOrder[0],
    // 즉 A)에서만 열 수 있다 - 다른 지점(B/C/D)의 anomaly는 같은 차량이 이미 A에서 발견된
    // 뒤 이동 중에 다시 잡힌 것일 뿐, 새로운 사건이 아니기 때문이다.
    if (isNewEpisode && cameraViewModel.demoId && cameraViewModel.demoId !== this.demoOrder[0]) {
      console.log(
        `[DEMO] ${cameraViewModel.demoId} 지점에서 감지되었지만 아직 ${this.demoOrder[0]}(시작 지점)에서 알림이 생성되지 않아 무시합니다.`
      );
      return;
    }

    if (!isNewEpisode) {
      // 이미 알림을 만든 적이 있다 - 카드/토스트/누적 감지 수 어느 것도 다시 건드리지
      // 않는다(요구사항: "B/C/D에서 anomaly가 있어도 새 이벤트 생성 ❌"). 다만 "지금
      // 활성 상태인 이상운전 차량" 통계 타이머만 갱신한다.
      this._markTrackActive(globalVehicleId, cameraViewModel.id);
      this.updateStats();
      return;
    }

    // ---- 최초(이자 유일한) 이상운전 알림 카드를 생성한다 ----
    if (this.toastManager) this.toastManager.show(cameraViewModel, normalized);

    const logEntry = { camera: cameraViewModel, event: normalized };
    this.log.unshift(logEntry);

    // firstDetectedCamera = anomalyEvent.location - 카드가 생성된 이후에는 차량이
    // B/C/D로 이동해도 이 값은 절대 다시 바뀌지 않는다(요구사항 8).
    this.demoEpisodes.set(globalVehicleId, {
      firstDetectedAt: eventData.time,
      firstDetectedCamera: demoRealCamId,
      logEntry,
    });

    this.alertDetectionCount += 1; // "사건" 단위로 누적 - 이 데모에서 정확히 1번만 증가한다

    // [상태 분리] 카메라 마커의 "이상운전 강조(빨간 pulse)"만 켠다. cameraManager.selectById(...)는
    // 절대 호출하지 않는다 - selectRecord() 내부가 openPopup/zoom/switchVideo와 무관하게 항상
    // "선택된 카메라"로 표시(_setSelectedMarker)해버려서, currentSelectedCamera(사용자가 보는 화면)를
    // AI가 감지한 카메라로 몰래 바꿔버리는 부작용이 있었다. setAlert()는 그런 부작용이 없다.
    this.cameraManager.setAlert(cameraViewModel.id, true);
    this.vehicleManager.setAlertStyle(true, eventData);
    this.trackedVehicleCount = this.vehicleManager.marker ? 1 : this.trackedVehicleCount;

    this._markTrackActive(globalVehicleId, cameraViewModel.id);

    this.uiManager.setLastUpdate(eventData.time);
    this.updateStats();
    this.renderPanel();
  }

  /* ==================================================================
     [신규] 영상 duration 기반 DEMO 차량 이동
     -------------------------------------------------------------
     ForzaDemoTimeline이 각 stage(A/B/C/D)의 실제 <video> 재생 상태를 다음 3개
     콜백으로 알려주면, 여기서 그 진행률을 "도로 기반 경로 위의 위치"로 변환해서
     차량 마커/Polyline에 반영한다. 알림(triggerDemoEvent)과는 완전히 분리되어
     있다 - 알림이 아직 안 떴어도(예: A 영상 0~3.38초 구간) 차량은 이미 A→B로
     이동을 시작한다(요구사항 17의 예시와 동일).
  ==================================================================== */

  // stage(demoId)의 영상이 막 시작될 때 호출된다. 다음 지점까지의 도로 경로를
  // "한 번만" 미리 계산해서 캐싱해 둔다 - 매 timeupdate마다 다시 계산하지 않는다.
  // D처럼 "다음 지점"이 없는 마지막 stage에서는 이동 자체가 없다(요구사항 6).
  beginDemoStageMovement(demoId, realCamId) {
    const stageIdx = this.demoOrder.indexOf(demoId);
    const nextIdx = stageIdx + 1;
    if (nextIdx >= this.demoOrder.length) {
      // D 단계 - 더 이상 갈 곳이 없다. 차량은 이미 D에 있어야 하고(이전 stage가
      // 도착시켜 놓음), 여기서는 아무 이동도 준비하지 않는다.
      this._demoMovement = null;
      return;
    }

    const nextDemoId = this.demoOrder[nextIdx];
    const fromRecord = this.cameraManager.getRecordById(realCamId);
    const toRecord = this.cameraManager.getRecordById(CONFIG.DEMO_CAMERA_ID_MAP[nextDemoId]);
    if (!fromRecord || !toRecord) {
      console.warn(`beginDemoStageMovement: ${demoId}→${nextDemoId} 구간의 카메라 레코드를 찾을 수 없습니다.`);
      this._demoMovement = null;
      return;
    }
    const fromVM = buildUticCameraViewModel(fromRecord, this.videoSourceRegistry);
    const toVM = buildUticCameraViewModel(toRecord, this.videoSourceRegistry);

    const movement = { fromVM, toVM, pathPoints: null, segLengths: null, totalLen: 1, ready: false };
    this._demoMovement = movement;

    // 기존 도로 기반 Polyline 로직(getRoadSegment - U턴 방지용 stripStartUTurn 포함)을
    // 그대로 재사용한다. 요구사항 9/12: "각 구간 독립 계산", "U턴 방지 로직 유지".
    this.routeManager.getRoadSegment([fromVM.lat, fromVM.lng], [toVM.lat, toVM.lng]).then((pathPoints) => {
      if (this._demoMovement !== movement) return; // 그 사이 다음 stage로 넘어갔으면 무시(경쟁 상태 방지)
      const segLengths = [];
      let totalLen = 0;
      for (let i = 1; i < pathPoints.length; i++) {
        const d = haversineMeters(pathPoints[i - 1], pathPoints[i]);
        segLengths.push(d);
        totalLen += d;
      }
      movement.pathPoints = pathPoints;
      movement.segLengths = segLengths;
      movement.totalLen = totalLen || 1;
      movement.ready = true;
    });
  }

  // ForzaDemoTimeline의 매 timeupdate마다 호출된다. progress(0~1)는 "지금 재생 중인
  // stage 영상의 currentTime/duration"과 정확히 같은 값이다(요구사항 2/7: "영상
  // currentTime을 기준으로 차량 위치와 Polyline progress를 계산").
  updateDemoStageProgress(demoId, progress) {
    const movement = this._demoMovement;
    if (!movement || !movement.ready) return; // 아직 도로 경로 fetch 중 - 다음 timeupdate에서 다시 시도됨

    const targetDist = progress * movement.totalLen;
    let acc = 0;
    let point = movement.pathPoints[0];
    for (let i = 0; i < movement.segLengths.length; i++) {
      const segLen = movement.segLengths[i];
      if (acc + segLen >= targetDist || i === movement.segLengths.length - 1) {
        const segT = segLen > 0 ? Math.min(1, Math.max(0, (targetDist - acc) / segLen)) : 0;
        const a = movement.pathPoints[i];
        const b = movement.pathPoints[i + 1];
        point = [a[0] + (b[0] - a[0]) * segT, a[1] + (b[1] - a[1]) * segT];
        break;
      }
      acc += segLen;
    }

    // 차량 마커를 "즉시"(별도 애니메이션 없이) 이 위치로 옮긴다 - 애니메이션 자체는
    // 영상이 재생되는 실시간 흐름 그 자체가 만들어준다(timeupdate가 계속 불려서
    // 자연스럽게 부드럽게 움직인다). Polyline도 이 진행률만큼만 점진적으로 그려진다
    // (요구사항 8: "한 번에 그리지 말 것").
    this.vehicleManager.setPositionForDemo(point, movement.toVM);
    this.routeManager.addTrajectoryPoint(point);
    this.trackedVehicleCount = this.vehicleManager.marker ? 1 : this.trackedVehicleCount;
  }

  // stage(demoId)의 duration만큼 시간이 흐른 순간(ForzaDemoTimeline._finishStage)에
  // 호출된다. 이 함수 자체가 "이동 시간 경과"와 "차량의 다음 CCTV 도착"을 하나로 묶는
  // 지점이다 - 별개의 두 트리거가 각자 따로 판단해서 어쩌다 같은 타이밍이 되는 구조가
  // 아니라, 타이머 콜백 단 하나가 (1) 차량을 다음 CCTV의 정확한 좌표로 스냅시키고
  // (2) DEMO 상태(vehicleCurrentCamera/demoSequenceIndex/trajectorySegments)를
  // 확정하고 (3) 그 직후(_finishStage가 이어서 호출하는 _advanceToStage) 다음 stage로
  // 넘어가게 만드는 유일한 원인이다. (예전에는 실제 <video>의 timeupdate/ended
  // 이벤트에 의존했는데, display:none 영상은 브라우저에 따라 재생이 보장되지 않아
  // 이벤트 자체가 안 나오는 문제가 있어서 - 실제 재생에 의존하지 않는 타이머 방식으로
  // 바꿨다.)
  //
  // [버그 수정] updateDemoStageProgress()는 100ms마다 progress(경과시간/duration)
  // 비율로 마커를 옮기지만, 마지막 tick이 정확히 progress=1.0에 맞아떨어진다는 보장은
  // 없다(0.97~0.99 정도에서 멈추고 그다음이 곧바로 stage 종료인 경우가 흔하다). 그래서
  // "이동 시간이 끝났는데 차량은 아직 목적지 코앞에 서 있는" 미세한 불일치가 생길 수
  // 있었다. 여기서 progress=1 지점의 좌표(=movement.pathPoints의 마지막 점, 즉 toVM
  // 좌표)로 명시적으로 스냅해서, "이동 종료 = 차량 도착"이 항상 정확히 같은 순간에
  // 성립하도록 만든다.
  completeDemoStageMovement(demoId, realCamId) {
    const movement = this._demoMovement; // null로 지우기 전에 먼저 참조를 잡아둔다

    const nextIdx = this.demoOrder.indexOf(demoId) + 1;
    if (nextIdx < this.demoOrder.length) {
      const nextDemoId = this.demoOrder[nextIdx];
      const nextRealCamId = CONFIG.DEMO_CAMERA_ID_MAP[nextDemoId];

      // ---- (1) 차량을 다음 CCTV의 "정확한" 좌표로 스냅한다 ----
      if (movement && movement.toVM) {
        this.vehicleManager.setPositionForDemo([movement.toVM.lat, movement.toVM.lng], movement.toVM);
        // Polyline도 실제 도로 경로의 마지막 점까지 정확히 채워서 마무리한다(progress가
        // 1.0에 못 미친 채로 끝나서 마지막 구간이 살짝 비어 보이는 것을 방지).
        if (movement.pathPoints && movement.pathPoints.length) {
          this.routeManager.addTrajectoryPoint(movement.pathPoints[movement.pathPoints.length - 1]);
        }
        this.trackedVehicleCount = this.vehicleManager.marker ? 1 : this.trackedVehicleCount;
      } else {
        console.warn(
          `completeDemoStageMovement: ${demoId}→${nextDemoId} 구간의 도로 경로가 아직 준비되지 않아 정확한 좌표로 스냅하지 못했습니다(마지막 progress 위치 그대로 유지).`
        );
      }

      // ---- (2) DEMO 상태를 확정한다 ----
      this.vehicleCurrentCamera = nextRealCamId;
      this.demoSequenceIndex = nextIdx;

      if (!this.trajectorySegments) this.trajectorySegments = [];
      this.trajectorySegments.push({ from: realCamId, to: nextRealCamId, globalVehicleId: CONFIG.DEMO_VEHICLE_ID });
    }
    // D(마지막 stage)는 nextIdx가 범위를 벗어나므로 여기서 아무것도 바꾸지 않는다 -
    // vehicleCurrentCamera는 C→D 전환 때 이미 D로 확정되어 있고, 그 상태 그대로
    // 고정된다(요구사항 6: "D 도착 후 차량 고정", "D→A/B/C 이동 금지").
    this._demoMovement = null;
    this.renderPanel();

    // ---- (3) 다음 영상 전환은 이 함수를 호출한 ForzaDemoTimeline._handleEnded()가
    // 바로 이어서 _advanceToStage()를 호출하는 것으로 처리된다 - 즉 "차량이 정확한
    // 좌표에 도착함을 확정"한 바로 다음 줄에서 다음 영상 로딩이 시작되므로, 두 이벤트가
    // 시간상 분리되지 않는다.
  }

  // 발표 리허설을 처음부터 다시 시작할 때 콘솔에서 호출할 수 있도록 노출한다(window.resetDemoTrajectory).
  resetDemoSession() {
    this.routeManager.clearTrajectory();
    this.vehicleManager.reset();
    this.activeTracks.forEach((entry) => clearTimeout(entry.timerId));
    this.activeTracks.clear();
    this.trackedVehicleCount = 0;
    this.demoEpisodes.clear(); // 알림 상태를 지워서 A부터 새 사건으로 다시 시작할 수 있게 한다
    this.trajectorySegments = []; // 확정된 구간 기록도 함께 초기화
    this.vehicleCurrentCamera = null;
    this.demoSequenceIndex = -1;
    this._demoMovement = null;
    this.updateStats();
    if (window.forzaDemoTimeline) window.forzaDemoTimeline.reset();
  }
  // 이미 활성 상태였다면(같은 차량이 계속 이상운전 중) 타이머만 연장한다 - 중복으로 세지 않는다.
  _markTrackActive(trackKey, camId) {
    if (!trackKey) return; // track_id가 없는 이벤트(수동 테스트 등)는 활성 카운트에 반영하지 않는다

    const existing = this.activeTracks.get(trackKey);
    if (existing) clearTimeout(existing.timerId);

    const timerId = setTimeout(() => this._expireTrack(trackKey), CONFIG.ANOMALY_ACTIVE_MS);
    this.activeTracks.set(trackKey, { camId, timerId });
  }

  // 활성 시간이 만료된 track_id를 해제한다. 더 이상 활성 차량이 없으면
  // 카메라 강조와 차량 pulse도 함께 해제한다.
  // [참고] 예전에는 여기서 demoEpisodes의 status를 ACTIVE→RESOLVED로 돌려서 "다시 감지되면
  // 새 카드"가 되게 했다. 지금은 알림이 "이 데모 세션에서 딱 1번"만 나는 구조로 바뀌어서
  // (triggerDemoEvent 참고) 그 상태 전이가 더 이상 필요 없다 - 여기서는 순수하게 "이상 차량"
  // 통계(activeTracks)만 정리한다.
  _expireTrack(trackKey) {
    const entry = this.activeTracks.get(trackKey);
    if (!entry) return;
    this.activeTracks.delete(trackKey);

    const stillActiveForSameCam = [...this.activeTracks.values()].some((v) => v.camId === entry.camId);
    if (!stillActiveForSameCam) {
      this.cameraManager.setAlert(entry.camId, false);
      this.vehicleManager.clearAlertState();
    }

    this.updateStats();
  }

  updateStats() {
    this.uiManager.updateHeaderStats({
      cameraCount: this.cameraManager.getRecordCount(),
      trackedVehicleCount: this.trackedVehicleCount,
      alertVehicleCount: this.activeTracks.size,
      alertDetectionCount: this.alertDetectionCount,
    });
  }

  renderPanel() {
    this.countEl.textContent = this.log.length;

    if (this.log.length === 0) {
      this.emptyEl.style.display = "block";
      return;
    }
    this.emptyEl.style.display = "none";

    const cardsHtml = this.log
      .map(({ camera, event }, index) => {
        const severityClass = event.severity ? `event-card--${event.severity}` : "";
        const confidenceRow =
          event.confidence != null
            ? `<span class="event-card__label">신뢰도</span><span class="event-card__value">${Math.round(
                event.confidence <= 1 ? event.confidence * 100 : event.confidence
              )}%</span>`
            : "";
        const plateOrTrack = event.plate
          ? `<span class="event-card__label">차량번호</span><span class="event-card__value event-card__value--plate">${event.plate}</span>`
          : `<span class="event-card__label">Track ID</span><span class="event-card__value event-card__value--plate">${
              event.trackId != null ? event.trackId : "-"
            }</span>`;

        return `
          <div class="event-card ${severityClass}" data-log-index="${index}">
            <div class="event-card__top">
              <span class="event-card__time">${event.time}</span>
              <span class="event-card__type">${event.icon || ""} ${event.type}</span>
            </div>
            <div class="event-card__grid">
              ${plateOrTrack}

              <span class="event-card__label">위치</span>
              <span class="event-card__value">${camera.location}</span>

              ${confidenceRow}
            </div>
          </div>
        `;
      })
      .join("");

    this.listEl.innerHTML = `<div id="event-empty" class="event-empty" style="display:none"></div>${cardsHtml}`;
    this.emptyEl = document.getElementById("event-empty");

    // 이벤트 클릭 → 지도 FlyTo + 카메라 선택 + 영상 전환 + Popup (요구사항 9번)
    this.listEl.querySelectorAll(".event-card").forEach((cardEl) => {
      cardEl.addEventListener("click", () => {
        const index = parseInt(cardEl.dataset.logIndex, 10);
        const entry = this.log[index];
        if (!entry) return;
        this.cameraManager.selectById(entry.camera.id, { openPopup: true, zoom: true, switchVideo: true });
      });
    });
  }
}


/* ==================================================================
   11) AiEventListener - Python(AI) → 웹 자동 반응 연결부
   -------------------------------------------------------------
   data/event.json 을 주기적으로 폴링해서 seq 값이 바뀌면 새 이벤트로 간주하고
   콜백을 실행한다. anomaly_detection.py의 gis_event_handler()가 이 파일을
   아래 형식으로 갱신한다.

     {
       "seq": 1,
       "cam_id": "H4642",
       "location_name": "이수어린이집 앞",
       "event_type": "ANOMALY_DRIVING",
       "track_id": "3",
       "plate": "12가3456",
       "reason": "지그재그 주행",
       "time": "18:25:12",
       "confidence": null
     }

   confidence는 규칙 기반(Weaving) 판정이라 수치형 신뢰도가 없을 수 있다 (null 허용).
   이번 단계에서는 CONFIG.ANOMALY_ENABLED_CAM_IDS에 없는 cam_id는 무시한다.

   WebSocket으로 받는 경우에는 이 클래스 대신 아래처럼 바로 연결하면 된다.

     const socket = new WebSocket("ws://localhost:8000/events");
     socket.onmessage = (msg) => {
       const data = JSON.parse(msg.data);
       const record = uticCameraManager.getRecordById(data.cam_id);
       if (record) eventManager.triggerAiEvent(record, data);
     };
================================================================== */
class AiEventListener {
  constructor(url, intervalMs, onEvent) {
    this.url = url;
    this.intervalMs = intervalMs;
    this.onEvent = onEvent;
    this.lastSeq = null;
    this._warned = false;
  }

  start() {
    this._poll();
    this.timer = setInterval(() => this._poll(), this.intervalMs);
  }

  async _poll() {
    try {
      const res = await fetch(this.url, { cache: "no-store" });
      if (!res.ok) return;
      const data = await res.json();
      if (!data || typeof data.seq !== "number") return;

      if (this.lastSeq === null) {
        // 최초 로드 시점의 seq는 "과거 값"으로만 기록하고 이벤트를 재생하지 않는다
        // (페이지를 새로고침할 때마다 마지막 이벤트가 반복 재생되는 것을 방지)
        this.lastSeq = data.seq;
        return;
      }

      if (data.seq !== this.lastSeq) {
        this.lastSeq = data.seq;
        if (data.seq > 0) this.onEvent(data);
      }
    } catch (err) {
      // event.json이 아직 없거나 네트워크 문제 - 콘솔을 어지럽히지 않도록 1회만 경고
      if (!this._warned) {
        console.warn("AI 이벤트 폴링 대기 중 (data/event.json 을 찾을 수 없습니다).", err);
        this._warned = true;
      }
    }
  }
}

/* ==================================================================
   11B) AiWebSocketListener - realtime_anomaly.py → server/server.js →
   여기로 실시간 연결하는 실제 통로.
   -------------------------------------------------------------
   server/routes/mapEvents.js가 ws://localhost:4000/events 로 broadcast하는
   이벤트를 그대로 받는다. 페이로드 형식은 realtime_anomaly.py의
   map_event_handler()가 만드는 것과 동일하다 (source_type/source_id/
   global_vehicle_id/latitude/longitude/anomaly/... - 파일 상단 주석 참고).

   연결이 끊기면(서버 재시작, 아직 서버를 안 켠 경우 등) 자동으로 재연결을
   계속 시도한다 - 페이지를 새로고침할 필요가 없다.
================================================== */
class AiWebSocketListener {
  constructor(url, onEvent, onStatusChange) {
    this.url = url;
    this.onEvent = onEvent;
    this.onStatusChange = onStatusChange;
    this.socket = null;
    this._retryMs = 3000;
    this._closedByUser = false;
    this._warned = false;
  }

  start() {
    this._closedByUser = false;
    this._connect();
  }

  _connect() {
    let socket;
    try {
      socket = new WebSocket(this.url);
    } catch (err) {
      this._warnOnce("AI 이벤트 WebSocket 생성 실패", err);
      this._scheduleReconnect();
      return;
    }
    this.socket = socket;

    socket.onopen = () => {
      console.log(`[AI EVENTS] WebSocket 연결됨: ${this.url}`);
      this._warned = false; // 재연결 성공 시 다음 끊김에서 다시 경고할 수 있도록 초기화
      if (this.onStatusChange) this.onStatusChange(true);
    };

    socket.onmessage = (msg) => {
      let data;
      try {
        data = JSON.parse(msg.data);
      } catch (err) {
        console.warn("[AI EVENTS] JSON 파싱 실패:", err, msg.data);
        return;
      }
      this.onEvent(data);
    };

    socket.onclose = () => {
      if (this.onStatusChange) this.onStatusChange(false);
      if (!this._closedByUser) this._scheduleReconnect();
    };

    socket.onerror = () => {
      // onclose가 뒤이어 호출되므로 재연결 스케줄링은 onclose에서만 처리한다.
      this._warnOnce(`AI 이벤트 서버(${this.url})에 연결할 수 없습니다 - server/server.js가 실행 중인지 확인하세요.`);
    };
  }

  _warnOnce(message, err) {
    if (this._warned) return;
    this._warned = true;
    if (err) console.warn(message, err);
    else console.warn(message);
  }

  _scheduleReconnect() {
    setTimeout(() => {
      if (!this._closedByUser) this._connect();
    }, this._retryMs);
  }

  stop() {
    this._closedByUser = true;
    if (this.socket) this.socket.close();
  }
}

/* ==================================================================
   12) 초기 실행
   -------------------------------------------------------------
   페이지 로드 시점에는 UTIC CCTV 마커 외에 아무것도 표시되지 않는다.
   차량 / 이동 경로 / 이벤트 카드 / 상단 통계는 전부 0(없음)에서 시작하며,
   AiWebSocketListener(실시간, 주 경로) 또는 AiEventListener(data/event.json
   폴링, 예비 경로 - WebSocket 서버가 꺼져 있어도 GIS 자체는 계속 동작하게
   하기 위해 그대로 남겨뒀다)가 이벤트를 감지했을 때만 eventManager의
   triggerAiEvent()/triggerDemoEvent()가 호출되어 화면이 자동으로 반응한다.

   [참고] TrafficCameraManager(공공데이터 단속카메라 4,255건)와 그 테스트 영상
   연결(TEST_VIDEO_OVERRIDES)은 실제 UTIC HLS 연결이 확인되면서 더 이상
   초기화하지 않는다. 클래스 정의 자체는 코드에 그대로 남겨뒀다(필요하면
   나중에 다시 활성화할 수 있다). 지도/검색/헤더 통계/AI 이벤트는 전부
   UticCameraManager(서울 UTIC CCTV 303건)를 기준으로 동작한다.
================================================================== */
document.addEventListener("DOMContentLoaded", () => {
  const mapManager = new MapManager("map");
  const popupManager = new PopupManager();
  const videoManager = new VideoManager();
  const routeManager = new RouteManager(mapManager.getMap());
  const vehicleManager = new VehicleManager(mapManager, popupManager);
  const videoSourceRegistry = new VideoSourceRegistry(); // UTIC 카메라 영상 공급원 (메타데이터와 분리)
  const uticCameraManager = new UticCameraManager(mapManager, videoManager, videoSourceRegistry); // 서울 UTIC 실시간 CCTV (지도에 표시되는 유일한 카메라)
  const toastManager = new ToastManager(document.getElementById("ai-toast-container"));

  // CCTV 영상 확대(Modal) - 제목은 항상 현재 영상 오버레이에 표시된 카메라명을 그대로 가져온다
  const videoModalManager = new VideoModalManager(
    document.getElementById("video-frame"),
    () => document.getElementById("video-overlay-title").textContent
  );

  // CCTV 검색 (CCTV명/관리번호/제공기관 → 목록 → 카메라 선택), UTIC 303건 대상
  const searchManager = new SearchManager(
    uticCameraManager,
    videoSourceRegistry,
    document.getElementById("cctv-search-form"),
    document.getElementById("cctv-search-input"),
    document.getElementById("cctv-search-results")
  );

  const uiManager = new UIManager(
    document.getElementById("theme-toggle"),
    document.getElementById("theme-toggle-icon"),
    document.getElementById("theme-toggle-label"),
    document.getElementById("live-clock"),
    document.getElementById("status-summary")
  );
  // 초기 화면: 이상 감지 0 / 연결 CCTV 0 / 추적 차량 0 / 이상 차량 0
  uiManager.updateHeaderStats({ cameraCount: 0, trackedVehicleCount: 0, alertVehicleCount: 0, alertDetectionCount: 0 });

  const eventManager = new EventManager(
    uticCameraManager,
    vehicleManager,
    uiManager,
    routeManager,
    toastManager,
    videoSourceRegistry
  );

  // [요구사항 2/14] currentSelectedCamera(사용자가 지금 보고 있는 CCTV)만 갱신한다.
  // vehicleCurrentCamera(차량이 실제 발견된 위치)는 여기서 절대 건드리지 않는다 -
  // "CCTV 클릭 ≠ 차량 이동"을 코드로 강제하는 지점이다.
  uticCameraManager.onCameraSelected = (record) => {
    eventManager.currentSelectedCamera = record.cam_id;
  };

  // 영상이 "이상운전 에피소드 시작 시각"을 지나갈 때마다 자동으로 호출된다.
  // (export_track_log.py가 사전 분석해 둔 episodes 배열 기준 - Python을 그때그때 켜둘 필요 없음.
  //  "영상 1회 재생 = 하나의 분석 세션" 정책 덕분에 같은 에피소드가 반복 호출되지 않는다.)
  //
  // [요구사항 1] Forza 데모(A/B/C/D)는 더 이상 여기서 처리하지 않는다 - 화면에 실제로
  // 보이고 있을 때만 도는 코드이기 때문이다. 아래 ForzaBackgroundAnalyzer가 화면 표시
  // 여부와 무관하게 4개 모두를 항상 분석하고, 그쪽에서 triggerDemoEvent를 호출한다.
  // (VideoManager._checkAnomalyEpisodes에도 Forza 소스는 건너뛰는 가드가 이미 있다.)
  videoManager.onAnomalyEpisode = (episode, camId) => {
    if (!CONFIG.ANOMALY_ENABLED_CAM_IDS.includes(camId)) return;
    const record = uticCameraManager.getRecordById(camId);
    if (!record) return;

    const now = new Date();
    const time = [now.getHours(), now.getMinutes(), now.getSeconds()]
      .map((n) => String(n).padStart(2, "0"))
      .join(":");

    eventManager.triggerAiEvent(record, {
      time,
      trackId: episode.track_id,
      plate: episode.plate || null,
      type: "이상운전 감지",
      reason: episode.reason,
      confidence: null, // 규칙 기반 판정 - 수치형 신뢰도 없음
    });
  };

  // [구조 변경: 영상 duration 기반 재설계] 예전에는 ForzaBackgroundAnalyzer가
  // A/B/C/D 4개의 "가상 시계"를 실시간(performance.now()) 기준으로 병렬로 돌리며
  // 차량 이동까지 함께 결정했다. 이번 요구사항("A 영상의 실제 재생 시간 = A→B
  // 이동 시간")에 맞춰 ForzaDemoTimeline으로 교체한다 - ForzaBackgroundAnalyzer
  // 클래스 자체는 코드에 그대로 남겨뒀다(필요하면 되돌릴 수 있음). 더 이상
  // 생성/시작하지 않으므로 이제 아무 동작도 하지 않는다.
  const forzaDemoTimeline = new ForzaDemoTimeline(CONFIG.DEMO_CAMERA_ID_MAP, CONFIG.FORZA_DEMO_SOURCES);

  // stage 영상이 시작될 때: 다음 지점까지의 도로 경로를 미리 계산해 둔다(D는 이동 없음).
  forzaDemoTimeline.onStageStart = (demoId, realCamId) => {
    console.log(`[DEMO] ${demoId}(${realCamId}) stage 시작`);
    eventManager.beginDemoStageMovement(demoId, realCamId);
  };

  // 영상이 재생되는 매 순간(timeupdate): 그 진행률만큼 차량/Polyline을 갱신한다.
  // (요구사항 2/7: "video.currentTime/duration 기준으로 차량 위치와 Polyline progress 계산")
  forzaDemoTimeline.onProgress = (demoId, progress) => {
    eventManager.updateDemoStageProgress(demoId, progress);
  };

  // 영상이 끝나면: "다음 지점에 정식 도착"으로 확정한다 (요구사항 3/4/5: 자동 전환).
  forzaDemoTimeline.onStageEnd = (demoId, realCamId) => {
    console.log(`[DEMO] ${demoId}(${realCamId}) stage 종료 - 다음 stage로 자동 전환`);
    eventManager.completeDemoStageMovement(demoId, realCamId);
  };

  // A 영상(현재는 A만 새 알림을 열 수 있도록 EventManager가 게이트한다) 재생 중
  // 실제 currentTime이 anomaly timestamp(약 3.38초)를 지날 때 호출된다.
  forzaDemoTimeline.onAnomaly = (demoId, realCamId, episode) => {
    const now = new Date();
    const time = [now.getHours(), now.getMinutes(), now.getSeconds()]
      .map((n) => String(n).padStart(2, "0"))
      .join(":");

    eventManager.triggerDemoEvent(realCamId, {
      time,
      trackId: episode.track_id,
      globalVehicleId: CONFIG.DEMO_VEHICLE_ID,
      plate: episode.plate || null,
      type: "이상운전 감지 (발표용 데모)",
      reason: episode.reason,
      confidence: null, // 규칙 기반 판정 - 수치형 신뢰도 없음
    });
  };

  forzaDemoTimeline.onFinished = () => {
    console.log("[DEMO] 발표용 Forza DEMO 시나리오가 모두 끝났습니다. 차량은 D(한강대교남단)에 고정된 상태로 유지됩니다.");
  };

  forzaDemoTimeline.start();
  window.forzaDemoTimeline = forzaDemoTimeline;

  // 차량 팝업의 "📹 CCTV 영상 보기" 버튼에서 호출할 수 있도록 전역에 노출
  window.__appSelectCamera = (cameraId) => {
    uticCameraManager.selectById(cameraId, { openPopup: true, zoom: true, switchVideo: true });
  };

  // 서울 UTIC CCTV 303건 로드 + 영상 공급원 로드를 "둘 다 끝난 뒤에" render()한다.
  // [중요 버그 수정] 예전에는 카메라 데이터가 로드되는 즉시 render()를 호출했는데,
  // render() 안에서 marker.bindPopup()이 그 시점의 videoSourceRegistry 상태를 기준으로
  // 팝업 HTML을 미리 만들어서 굳혀버린다(정적 문자열). 이때 videoSourceRegistry가
  // 아직 로드되기 전이면(두 fetch가 병렬로 실행되므로 순서가 보장되지 않음) 실제로는
  // 영상이 연결된 카메라도 팝업에 "연결 예정"으로 영원히 고정되는 문제가 있었다.
  // 그래서 두 로드를 Promise.all로 함께 기다린 뒤에만 render()를 호출하도록 순서를 바꿨다.
  const uticCamerasLoaded = uticCameraManager.loadData("data/utic-cameras-seoul.json");
  const videoSourcesLoaded = videoSourceRegistry
    .loadData("data/utic-video-sources.json")
    .then((list) => console.log(`[UTIC VIDEO SOURCE] 등록된 영상 공급원 ${list.length}건`))
    .catch((err) => {
      console.warn("UTIC 영상 공급원 데이터 로드 실패 (영상 없이 계속 진행):", err);
      return []; // 실패해도 카메라 렌더링 자체는 계속 진행되도록 Promise.all이 거부되지 않게 한다
    });

  Promise.all([uticCamerasLoaded, videoSourcesLoaded])
    .then(([records]) => {
      // 이 시점에는 videoSourceRegistry가 이미 로드를 마쳤으므로, render()가 만드는
      // 모든 팝업이 정확한 영상 연결 상태(실시간 연결 vs 연결 예정)를 반영한다.
      uticCameraManager.render(records);
      console.log(`[UTIC CCTV] 서울 실시간 CCTV ${records.length}건 표시`);

      // 연결 CCTV 수(303) + 영상 공급원 배지가 정확히 반영된 뒤 헤더를 갱신한다
      eventManager.updateStats();

      // ---- Python(AI) 이벤트 자동 감지 시작 ----
      const aiEventListener = new AiEventListener("data/event.json", 3000, (data) => {
        const camId = data.cam_id;

        if (!CONFIG.ANOMALY_ENABLED_CAM_IDS.includes(camId)) {
          console.warn(`event.json: 이번 단계에서 허용되지 않은 cam_id(${camId}) - 무시합니다.`);
          return;
        }

        const record = uticCameraManager.getRecordById(camId);
        if (!record) {
          console.warn(`event.json: 알 수 없는 cam_id(${camId}) - UTIC CCTV 목록에서 찾을 수 없습니다.`);
          return;
        }

        eventManager.triggerAiEvent(record, {
          time: data.time,
        plate: data.plate || null, // 없으면 팝업/카드에서 Track ID로 대체 표시
        type: data.event_type === "ANOMALY_DRIVING" ? "이상운전 감지" : data.event_type,
        reason: data.reason,
        confidence: data.confidence != null ? data.confidence : null, // 규칙 기반 판정은 값이 없을 수 있음
        trackId: data.track_id,
      });
    });
    aiEventListener.start();
    window.aiEventListener = aiEventListener;

    // ---- Python(AI) 이벤트 자동 감지 시작 (실시간, 주 경로) ----
    // realtime_anomaly.py의 event_aggregator 프로세스가 server/server.js로 POST하면,
    // server.js가 ws://localhost:4000/events에 연결된 모든 클라이언트에게 즉시 broadcast한다.
    // source_type에 따라 실제 CCTV(UTIC)/Forza 데모(DEMO) 이벤트를 분기 처리한다.
    const aiWsListener = new AiWebSocketListener(CONFIG.MAP_EVENTS_WS_URL, (data) => {
      if (!data || !data.source_type) return;

      const time =
        data.time_str ||
        new Date((data.timestamp || Date.now() / 1000) * 1000).toLocaleTimeString("ko-KR", { hour12: false });
      const type = data.event_type === "ABNORMAL_DRIVING" ? "이상운전 감지" : data.event_type || "이상운전 감지";
      const reason = data.reason || "지그재그 주행";
      const confidence = data.confidence != null ? data.confidence : null;
      const plate = data.plate || null;

      if (data.source_type === "DEMO") {
        const demoRealCamId = CONFIG.DEMO_CAMERA_ID_MAP[data.source_id];
        if (!demoRealCamId) {
          console.warn(`WebSocket: 알 수 없는 데모 source_id(${data.source_id}) - 무시합니다.`);
          return;
        }
        eventManager.triggerDemoEvent(demoRealCamId, {
          time,
          trackId: data.track_id,
          globalVehicleId: data.global_vehicle_id,
          plate,
          type: `${type} (발표용 데모)`,
          reason,
          confidence,
        });
        return;
      }

      // source_type === "UTIC" (실제 CCTV)
      if (!CONFIG.ANOMALY_ENABLED_CAM_IDS.includes(data.source_id)) {
        console.warn(`WebSocket: 허용되지 않은 cam_id(${data.source_id}) - 무시합니다.`);
        return;
      }
      const record = uticCameraManager.getRecordById(data.source_id);
      if (!record) {
        console.warn(`WebSocket: 알 수 없는 cam_id(${data.source_id}) - UTIC CCTV 목록에서 찾을 수 없습니다.`);
        return;
      }
      eventManager.triggerAiEvent(record, {
        time,
        trackId: data.track_id,
        plate,
        type,
        reason,
        confidence,
      });
    });
    aiWsListener.start();
    window.aiWsListener = aiWsListener;

    // 발표 리허설을 처음부터 다시 시작할 때 콘솔에서 호출: resetDemoTrajectory()
    window.resetDemoTrajectory = () => eventManager.resetDemoSession();
  })
    .catch((err) => console.error("UTIC CCTV 초기화 실패:", err));

  // 실시간 연동 시 콘솔/외부 스크립트에서 바로 쓸 수 있도록 전역에 노출
  window.mapManager = mapManager;
  window.uticCameraManager = uticCameraManager;
  window.videoSourceRegistry = videoSourceRegistry;
  window.videoManager = videoManager;
  window.vehicleManager = vehicleManager;
  window.eventManager = eventManager;
  window.routeManager = routeManager;
  window.videoModalManager = videoModalManager;
  window.searchManager = searchManager;
});