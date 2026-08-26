const CONFIG = {
  SEOUL_CENTER: { lat: 37.5665, lng: 126.978 },
  DEFAULT_ZOOM: 11,
  FOCUS_ZOOM: 17,
  DEFAULT_BASEMAP: "osm",
  DEFAULT_THEME: "dark",
  ANOMALY_ENABLED_CAM_IDS: ["L010263", "L010117", "L010018", "L010055"],
  DEMO_CAMERA_ID_MAP: {
    A: "L010111",
    B: "L010271",
    C: "L010128",
    D: "L010481",
  },
  DEMO_VEHICLE_ID: "DEMO-DRUNK-001",
  MAP_SERVER_ORIGIN: "http://localhost:4000",
  FORZA_DEMO_SOURCES: {
    L010111: { demoId: "A", videoUrl: "http://localhost:4000/videos/음주운전1.mp4" },
    L010271: { demoId: "B", videoUrl: "http://localhost:4000/videos/음주운전2.mp4" },
    L010128: { demoId: "C", videoUrl: "http://localhost:4000/videos/음주운전3.mp4" },
    L010481: { demoId: "D", videoUrl: "http://localhost:4000/videos/음주운전4.mp4" },
    L010043: { demoId: "KICK", videoUrl: "http://localhost:4000/videos/kickboard_h264.mp4", trackLogUrl: "data/debris-track-log-L010043.json" },
    L010146: { demoId: "BOX",  videoUrl: "http://localhost:4000/videos/box_h264.mp4",       trackLogUrl: "data/debris-track-log-L010146.json" },
    L010140: { demoId: "CONE", videoUrl: "http://localhost:4000/videos/cone_h264.mp4",      trackLogUrl: "data/debris-track-log-L010140.json" },
  },
  ANOMALY_ACTIVE_MS: 6000,
  // [수정: "지도에 옛날 발표용 데모(DEMO-DRUNK-001) 알림 팝업이 계속 뜸"] 이 발표용
  // Forza 데모(20초 뒤 자동 시작, A~D 카메라를 돌며 가짜 음주운전 이벤트를 계속 생성)는
  // 더 이상 필요 없어서 껐다. true로 바꾸면 예전처럼 다시 켤 수 있다 - 관련 코드
  // (ForzaDemoTimeline 등)는 그대로 남겨뒀다.
  ENABLE_FORZA_DEMO: false,
  FORZA_DEMO_START_DELAY_MS: 20000,
  MAP_EVENTS_WS_URL: "ws://localhost:4000/events",
  MAP_EVENTS_POST_URL: "http://localhost:4000/api/map/events",
  MAP_CAPTURES_POST_URL: "http://localhost:4000/api/map/captures",
  CAPTURE_AFTER_DELAY_MS: 1500,
  REAL_JOURNEY_STOMP_URL: "http://localhost:8080/ws",
};

const TEST_VIDEO_OVERRIDES = {};

// [버그 수정] window.__appGoToJourneyStartCctv가 typeof "undefined"였던 원인:
// 이전엔 이 정의가 document.addEventListener("DOMContentLoaded", ...) 콜백
// 안, 다른 초기화 코드(uticCameraManager 생성/로딩 등) 사이에 있었다. 그 앞의
// 어떤 초기화든 하나라도 예외를 던지면 그 뒤에 있던 이 정의는 영영 실행되지
// 않는다 - 그래서 브라우저 콘솔에서 typeof가 undefined로 나왔다.
//
// 이 함수는 CONFIG와 window.dispatchEvent만 있으면 되고 DOM이 완전히 준비될
// 필요도, 다른 매니저 인스턴스가 먼저 만들어질 필요도 없다. 그래서 파일이
// 파싱되는 즉시(스크립트 최상단에서, 다른 어떤 초기화보다도 먼저) 정의되도록
// 옮겼다 - 이제 DOMContentLoaded 콜백 안에서 무슨 일이 일어나든 이 함수 자체는
// 항상 존재한다.
//
// Real Journey 차량 상세 팝업의 "📹 CCTV 바로가기" 버튼에서 호출한다
// (buildRealJourneyPopupHtml 참고). 실제 CCTV 선택 UI는 map.js 안에 없고
// 대시보드(DashboardCctvPanel.jsx)의 <select value={selectedCamId}>다 -
// map.js와 그 대시보드는 서로 다른 window 컨텍스트라 함수를 직접 호출할 수
// 없으므로, 표준 CustomEvent만 dispatch한다. 실제로 select 값을 바꾸고 기존
// onChange 로직(LiveHlsVideoWithDetections 등)을 태우는 건 DashboardCctvPanel.jsx의
// "cctv:select" 리스너 쪽 책임이다(이미 콘솔 직접 테스트로 정상 동작 확인됨).
// 여기서는 mapManager/RealVehicleMarker/Journey Polyline/차량 위치 무엇도
// 건드리지 않는다 - 이벤트를 하나 던질 뿐이다.
// [버그 수정: "CCTV 바로가기를 눌러도 항상 같은 카메라(A)로만 감"]
// 예전엔 인자를 안 받고 CONFIG.DEMO_CAMERA_ID_MAP.A(발표용 데모 카메라)를 무조건
// 썼다 - 그래서 실제 이상운전 차량이 어느 카메라에 있든 "CCTV 바로가기"를 누르면
// 항상 데모 카메라 A로만 이동했다. 이제 buildRealJourneyPopupHtml에서 이 함수를
// 호출할 때 그 팝업이 속한 실제 payload.currentCamId를 그대로 넘겨받아서 쓴다.
// camId가 없는 경우(옛 팝업 HTML이 캐시돼 있는 등)에만 데모 카메라로 폴백한다.
window.__appGoToJourneyStartCctv = (camId) => {
  const startCamId = camId || CONFIG.DEMO_CAMERA_ID_MAP.A;

  console.log(
    "[CCTV] Real Journey CCTV 바로가기 요청:",
    startCamId
  );

  window.parent.postMessage(
    {
      type: "cctv:select",
      camId: startCamId,
    },
    "http://localhost:5173"
  );
};


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

function hashString(str) {
  let h = 0;
  for (let i = 0; i < str.length; i += 1) {
    h = (h << 5) - h + str.charCodeAt(i);
    h |= 0;
  }
  return h;
}

function getVideoOverride(record) {
  const camId = String(record["무인교통단속카메라관리번호"] || "");
  return TEST_VIDEO_OVERRIDES[camId] || null;
}

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

function haversineMeters([lat1, lng1], [lat2, lng2]) {
  const R = 6371000;
  const toRad = (d) => (d * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLng = toRad(lng2 - lng1);
  const a =
    Math.sin(dLat / 2) ** 2 + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(Math.min(1, a)));
}

function computeBearingDeg([lat1, lng1], [lat2, lng2]) {
  const toRad = (d) => (d * Math.PI) / 180;
  const toDeg = (r) => (r * 180) / Math.PI;
  const y = Math.sin(toRad(lng2 - lng1)) * Math.cos(toRad(lat2));
  const x =
    Math.cos(toRad(lat1)) * Math.sin(toRad(lat2)) -
    Math.sin(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.cos(toRad(lng2 - lng1));
  return Math.round((toDeg(Math.atan2(y, x)) + 360) % 360);
}

// [신규: 사각지대 재등장 연출] 위도/경도 + 방위각(도) + 거리(m)로부터 도착 지점을
// 계산한다(구면 삼각법, computeBearingDeg의 역연산에 해당). 사각지대를 빠져나온
// 지점에서 "어느 방향이든 폴리라인이 조금 더 그려지게" 하기 위해, 재등장 직전
// 진행 방향으로 짧게 뻗어나가는 가상의 도착점을 만드는 데 쓴다.
function destinationPoint([lat, lng], bearingDeg, distanceMeters) {
  const R = 6371000;
  const toRad = (d) => (d * Math.PI) / 180;
  const toDeg = (r) => (r * 180) / Math.PI;
  const bearing = toRad(bearingDeg);
  const lat1 = toRad(lat);
  const lng1 = toRad(lng);
  const angDist = distanceMeters / R;

  const lat2 = Math.asin(
    Math.sin(lat1) * Math.cos(angDist) +
      Math.cos(lat1) * Math.sin(angDist) * Math.cos(bearing)
  );
  const lng2 =
    lng1 +
    Math.atan2(
      Math.sin(bearing) * Math.sin(angDist) * Math.cos(lat1),
      Math.cos(angDist) - Math.sin(lat1) * Math.sin(lat2)
    );

  return [toDeg(lat2), ((toDeg(lng2) + 540) % 360) - 180];
}

function stripStartUTurn(pathPoints) {
  if (!pathPoints || pathPoints.length < 4) return pathPoints;

  const start = pathPoints[0];
  const SEARCH_LIMIT_METERS = 300;
  const LEFT_START_METERS = 80;
  const NEAR_START_METERS = 40;

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
      loopBackIndex = i;
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
    speedLimit: "-",
    sourceLabel: source && source.source_type ? source.source_type : "UTIC 실시간 CCTV",
    lat: record.lat,
    lng: record.lng,
    videoUrl: source ? source.video_url : null,
    videoFormat: source ? source.video_format : null,
    purpose: source ? "UTIC_LIVE" : null,
    record,
  };

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

function buildApproachPath(lat, lng, seed) {
  const angle = (Math.abs(hashString(String(seed))) % 360) * (Math.PI / 180);
  const dist = 0.006;
  const start = [lat - Math.cos(angle) * dist, lng - Math.sin(angle) * dist];
  const mid = [lat - Math.cos(angle) * dist * 0.45, lng - Math.sin(angle) * dist * 0.45];
  return [start, mid, [lat, lng]];
}

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

    this._followPaused = false;
    this.map.on("dragstart", () => this.pauseFollow());

    this._renderBaseMapControl();
    this.switchBaseMap(CONFIG.DEFAULT_BASEMAP);

    setTimeout(() => this.map.invalidateSize(), 100);
    setTimeout(() => this.map.invalidateSize(), 500);
    setTimeout(() => this.map.invalidateSize(), 1200);
    window.addEventListener("resize", () => this.map.invalidateSize());
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

  panFollow(lat, lng) {
    if (this._followPaused) return;
    this.map.panTo([lat, lng], { animate: false });
  }

  pauseFollow() {
    this._followPaused = true;
  }

  resumeFollow() {
    this._followPaused = false;
  }

  getMap() {
    return this.map;
  }
}

class PopupManager {
  buildVehiclePopup(state) {
    const statusClass = state.severity === "alert" ? "cctv-popup__value--status-alert" : "";
    const plateDisplay = state.plate || "-";

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
    this.hls = null;

    this.trackLogCache = null;
    this.trackLogCacheByCamId = new Map();
    this.boxOverlayActive = false;
    this.boxOverlayRafId = null;
    this.sessionId = 0;
    this.processedEpisodeKeys = new Set();
    this._prevOverlayTime = null;
    this.onAnomalyEpisode = null;

    this.videoEl.addEventListener("error", () => this._handleVideoError());
    this.videoEl.addEventListener("loadeddata", () => this._hideError());
  }

  switchTo(viewModel, options = {}) {
    const { immediate = false, force = false } = options;
    if (!viewModel || (viewModel.id === this.currentId && !force)) return;

    const apply = () => {
      this.currentId = viewModel.id;

      if (viewModel.videoUrl) {
        this.emptyEl.style.display = "none";
        this.overlayEl.style.display = "flex";
        this.titleEl.textContent = viewModel.location;
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

        if (viewModel.purpose === "ANOMALY_DETECTION_TEST") {
          this._attachBoxOverlay(viewModel.id, "data/anomaly-track-log.json");
        } else if (viewModel.purpose === "FORZA_DEMO" && viewModel.trackLogUrl) {
          this._attachBoxOverlay(viewModel.id, viewModel.trackLogUrl);
        } else {
          this._detachBoxOverlay();
        }
      } else {
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

    this.frameEl.classList.add("is-fading");
    setTimeout(apply, 220);
  }

  switchVideo(videoPath, camId = null) {
    this._hideError();
    this._destroyHls();
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
      this.videoEl.src = videoPath;
      this.videoEl.load();
      console.log("video (재생 방식):", isHls ? "네이티브 HLS(Safari)" : "일반 <video> src");
    }

    console.log("video (최종 해석 URL):", this.videoEl.currentSrc || this.videoEl.src || "(hls.js가 관리 중)");

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

  _destroyHls() {
    if (this.hls) {
      this.hls.destroy();
      this.hls = null;
    }
  }

  _clearVideo() {
    this._hideError();
    this._destroyHls();
    this.currentCamId = null;
    this.videoEl.pause();
    this.videoEl.removeAttribute("src");
    this.videoEl.load();
  }

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

  async _attachBoxOverlay(camId, trackLogUrl) {
    this._detachBoxOverlay();

    let log = this.trackLogCacheByCamId.get(camId);
    if (!log) {
      try {
        const res = await fetch(trackLogUrl, { cache: "no-store" });
        if (!res.ok) throw new Error(`status ${res.status}`);
        log = await res.json();
        this.trackLogCacheByCamId.set(camId, log);
      } catch (err) {
        console.warn(
          `[ANOMALY OVERLAY] ${trackLogUrl}을 불러오지 못했습니다.`,
          err
        );
        return;
      }
    }

    if (this.currentCamId !== camId) return;
    if (log.cam_id !== camId) {
      console.warn(`[ANOMALY OVERLAY] 트랙 로그의 cam_id(${log.cam_id})가 현재 카메라(${camId})와 다릅니다.`);
      return;
    }

    this.trackLogCache = log;
    this.boxOverlayActive = true;
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
    this.aiBadgeEl.style.display = "none";
    this.canvasCtx.clearRect(0, 0, this.canvasEl.width, this.canvasEl.height);
  }

  _renderBoxOverlay() {
    const log = this.trackLogCache;
    if (!log || !this.boxOverlayActive) return;

    const rect = this.videoEl.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) return;
    if (!log.width || !log.height) return;

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

  _episodeKey(episode) {
    return `${this.currentCamId}_${episode.track_id}_${episode.t}`;
  }

  _checkAnomalyEpisodes(t) {
    if (this._prevOverlayTime != null && t < this._prevOverlayTime - 0.25) {
      console.log(
        `[ANOMALY OVERLAY] 영상 루프 감지 (cam_id=${this.currentCamId}, session=${this.sessionId})`
      );
    }
    this._prevOverlayTime = t;

    const episodes = this.trackLogCache.episodes || [];
    episodes.forEach((episode) => {
      if (episode.t > t) return;

      const key = this._episodeKey(episode);
      if (this.processedEpisodeKeys.has(key)) return;

      this.processedEpisodeKeys.add(key);

      if (CONFIG.FORZA_DEMO_SOURCES[this.currentCamId]) return;

      if (this.onAnomalyEpisode) this.onAnomalyEpisode(episode, this.currentCamId, this.sessionId);
    });
  }
}

class VideoModalManager {
  constructor(frameEl, titleGetter) {
    this.frameEl = frameEl;
    this.modalEl = document.getElementById("video-modal");
    this.modalBodyEl = document.getElementById("video-modal-body");
    this.modalTitleEl = document.getElementById("video-modal-title");
    this.expandBtnEl = document.getElementById("video-expand-btn");
    this.closeBtnEl = document.getElementById("video-modal-close");
    this.titleGetter = titleGetter;

    this.originalParent = frameEl.parentElement;
    this.originalNextSibling = frameEl.nextSibling;
    this.isOpen = false;

    if (this.expandBtnEl) this.expandBtnEl.addEventListener("click", () => this.open());
    if (this.closeBtnEl) this.closeBtnEl.addEventListener("click", () => this.close());
    if (this.modalEl) {
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
    if (this.originalNextSibling && this.originalNextSibling.parentElement === this.originalParent) {
      this.originalParent.insertBefore(this.frameEl, this.originalNextSibling);
    } else {
      this.originalParent.appendChild(this.frameEl);
    }
    this.modalEl.classList.remove("is-open");
    this.modalEl.style.display = "none";
  }
}

class TrafficCameraManager {
  constructor(mapManager, videoManager) {
    this.mapManager = mapManager;
    this.map = mapManager.getMap();
    this.videoManager = videoManager;

    this.allRecords = [];
    this.markers = [];
    this.markerState = new WeakMap();
    this.markerById = new Map();
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

  selectRecord(marker, record, opts = {}) {
    const { openPopup = false, zoom = false, switchVideo = false, force = false } = opts;
    const vm = buildCameraViewModel(record);

    if (zoom) this.mapManager.focus(vm.lat, vm.lng, CONFIG.FOCUS_ZOOM);
    if (openPopup) marker.openPopup();
    this._setSelectedMarker(marker);
    if (switchVideo) this.videoManager.switchTo(vm, { force });
  }

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

  _escape(str) {
    const div = document.createElement("div");
    div.textContent = String(str);
    return div.innerHTML;
  }
}

class VideoSourceRegistry {
  constructor() {
    this.sourcesByCamId = new Map();
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

  getSource(camId) {
    return this.sourcesByCamId.get(String(camId)) || null;
  }

  getCount() {
    return this.sourcesByCamId.size;
  }
}

class UticCameraManager {
  constructor(mapManager, videoManager, videoSourceRegistry) {
    this.mapManager = mapManager;
    this.map = mapManager.getMap();
    this.videoManager = videoManager;
    this.videoSourceRegistry = videoSourceRegistry;

    this.allRecords = [];
    this.markers = [];
    this.markerState = new WeakMap();
    this.markerById = new Map();
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

    this.onCameraSelected = null;

    this.clusterGroup.addTo(this.map);
  }

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

  _buildPopup(record) {
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

  selectRecord(marker, record, opts = {}) {
    const { openPopup = false, zoom = false, switchVideo = false, force = false } = opts;

    if (zoom) this.mapManager.focus(record.lat, record.lng, CONFIG.FOCUS_ZOOM);
    if (openPopup) marker.openPopup();
    this._setSelectedMarker(marker);

    if (switchVideo && this.videoManager) {
      const vm = buildUticCameraViewModel(record, this.videoSourceRegistry);
      this.videoManager.switchTo(vm, { force });
    }

    // [수정: "추적 차량 화면의 '실시간 CCTV' 패널을 없애고, 그 기능(연결된 CCTV를
    // 클릭하면 영상이 뜨는 것)만 관제 화면 오른쪽 CCTV 사이드바로 옮겨달라"]
    // 예전엔 여기서 videoManager.switchTo()만 호출했다 - 그 결과가 보이려면 map.js
    // 자신의 <section class="video-panel">("추적 차량" 화면 전용, iframe 내부)이
    // 떠 있어야 했다. 이제 그 패널은 대시보드(React)에서 더 이상 띄우지 않으므로,
    // Real Journey의 "CCTV 바로가기"와 동일한 경로(window.__appGoToJourneyStartCctv →
    // postMessage cctv:select)로 부모 대시보드에 알려서, 관제 화면의 CCTV 사이드바가
    // 이 카메라로 전환되게 한다.
    // [버그 수정] 처음엔 this.videoSourceRegistry.getSource(record.cam_id)가 있을 때만
    // (실시간 UTIC HLS 스트림 303건 중 일부에만 연결된) 보냈는데, 그러면 우리가 실제로
    // "CCTV 관리"(/api/cameras)에 등록해서 쓰는 데모 카메라 4대(L010111 등, AI
    // 이상운전 감지가 실제로 이 카메라들을 대상으로 함)는 그 UTIC 스트림 레지스트리에는
    // 없어서 조건을 통과 못 하고 조용히 씹혔다 - "화면 정중앙 알림 → 지도에서 실시간으로
    // 보기를 눌러도 CCTV 화면으로 안 넘어간다"는 문제의 원인이었다. "정말 연결됐는지"의
    // 최종 판단은 어차피 받는 쪽(DashboardCctvPanel)이 자기 카메라 목록으로 다시
    // 확인하므로(못 찾으면 조용히 무시), 여기서는 그냥 항상 보낸다.
    if (switchVideo && window.__appGoToJourneyStartCctv) {
      window.__appGoToJourneyStartCctv(record.cam_id);
    }

    if (this.onCameraSelected) this.onCameraSelected(record);
  }

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

  addTrajectoryPoint(latlng) {
    if (!this.trajectoryPoints) this.trajectoryPoints = [];

    const last = this.trajectoryPoints[this.trajectoryPoints.length - 1];
    if (last && last[0] === latlng[0] && last[1] === latlng[1]) return;
    this.trajectoryPoints.push(latlng);

    if (this.trajectoryPoints.length < 2) return;

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

  clearTrajectory() {
    if (this.trajectoryPolyline) {
      this.map.removeLayer(this.trajectoryPolyline);
      this.trajectoryPolyline = null;
    }
    this.trajectoryPoints = [];
  }

  setRealJourneyPoints(points) {
    // [참고] 지금은 아무도 호출하지 않는다(appendRealJourneyPoint()로 실시간
    // 누적 방식만 씀) - 혹시 필요해질 때를 위해 남겨둔다.
    if (!points || points.length < 2) {
      if (this.realJourneyPolyline) {
        this.map.removeLayer(this.realJourneyPolyline);
        this.realJourneyPolyline = null;
      }
      return;
    }

    const routeColor =
      getComputedStyle(document.documentElement).getPropertyValue("--accent-alert").trim() || "#ef4444";

    if (!this.realJourneyPolyline) {
      this.realJourneyPolyline = L.polyline(points, {
        color: routeColor,
        weight: 4,
        opacity: 0.85,
        lineCap: "round",
        lineJoin: "round",
      }).addTo(this.map);
    } else {
      this.realJourneyPolyline.setLatLngs(points);
    }
  }

  clearRealJourney() {
    if (this.realJourneyPolyline) {
      this.map.removeLayer(this.realJourneyPolyline);
      this.realJourneyPolyline = null;
    }
    // [수정: "동교동삼거리 사각지대" 버그] 예전엔 좌표를 하나의 평평한 배열
    // (realJourneyPoints)에 계속 append만 했다 - 그런데 사각지대 구간에서는
    // 일부러 좌표를 안 그린 채 건너뛰었기 때문에, Leaflet이 "마지막으로 그린
    // 점(신촌 근처)"과 "다음에 그려진 점(합정역 이후)" 사이를 자동으로 직선
    // 으로 이어버렸다 - 화면에 보인 그 긴 사선 직선의 진짜 원인이었다.
    // 이제는 여러 개의 "끊어진 선분(segment)"을 따로 관리한다 - Leaflet의
    // L.polyline()은 좌표 배열의 배열([[..], [..]])을 주면 그 사이는 자동으로
    // 잇지 않고 각각 독립된 선으로 그린다(MultiPolyline).
    this.realJourneySegments = [];
  }

  // [신규] 사각지대(예: 동교동삼거리) 통과 등, 지금까지 그린 선과 이어붙이면
  // 안 되는 지점에서 호출한다 - 다음 appendRealJourneyPoint()부터는 새 선분에
  // 쌓이기 시작해서, 이전 선분과 화면에서 자동으로 연결되지 않는다.
  startNewRealJourneySegment() {
    if (!this.realJourneySegments) this.realJourneySegments = [];
    if (
      this.realJourneySegments.length === 0 ||
      this.realJourneySegments[this.realJourneySegments.length - 1].length > 0
    ) {
      this.realJourneySegments.push([]);
    }
  }

  appendRealJourneyPoint(latlng) {
    if (!this.realJourneySegments) this.realJourneySegments = [];
    if (this.realJourneySegments.length === 0) this.realJourneySegments.push([]);

    const currentSegment = this.realJourneySegments[this.realJourneySegments.length - 1];

    const last = currentSegment[currentSegment.length - 1];
    if (last && last[0] === latlng[0] && last[1] === latlng[1]) return;
    currentSegment.push(latlng);

    this._redrawRealJourneySegments();
  }

  // [신규: animateAlong() 이식용] animateAlong()의 onFrame은 appendRealJourneyPoint()
  // 처럼 점을 하나씩 이어붙이는 게 아니라, "지나온 좌표 + 지금 보간 중인 좌표"
  // 전체 배열을 매 프레임 통째로 넘겨준다(setRealJourneyPoints와 같은 전체
  // 재그리기 방식). 그래서 지금 그리고 있는 마지막 선분(segment)의 내용만
  // 매 프레임 통째로 교체해서 다시 그린다 - 사각지대 이전에 이미 완성된
  // 선분들은 건드리지 않는다(startNewRealJourneySegment()로 분리해둔 덕분).
  setCurrentRealJourneySegment(points) {
    if (!this.realJourneySegments) this.realJourneySegments = [];
    if (this.realJourneySegments.length === 0) this.realJourneySegments.push([]);
    this.realJourneySegments[this.realJourneySegments.length - 1] = points.slice();
    this._redrawRealJourneySegments();
  }

  _redrawRealJourneySegments() {
    // 선분이 하나도 2점 이상이 안 되면(막 시작한 선분 하나뿐) 아직 그릴 게 없다.
    const drawable = this.realJourneySegments.filter((seg) => seg.length >= 2);
    if (drawable.length === 0) return;

    const routeColor =
      getComputedStyle(document.documentElement).getPropertyValue("--accent-alert").trim() || "#ef4444";

    if (!this.realJourneyPolyline) {
      this.realJourneyPolyline = L.polyline(drawable, {
        color: routeColor,
        weight: 4,
        opacity: 0.85,
        lineCap: "round",
        lineJoin: "round",
      }).addTo(this.map);
    } else {
      this.realJourneyPolyline.setLatLngs(drawable);
    }
  }

  async getRoadSegment(fromLatLng, toLatLng) {
    if (!this._roadSegmentCache) this._roadSegmentCache = new Map();

    const key = `${fromLatLng[0].toFixed(6)},${fromLatLng[1].toFixed(6)}->${toLatLng[0].toFixed(6)},${toLatLng[1].toFixed(6)}`;
    if (this._roadSegmentCache.has(key)) return this._roadSegmentCache.get(key);

    const straightLine = [fromLatLng, toLatLng];
    const bearing = computeBearingDeg(fromLatLng, toLatLng);
    const BEARING_TOLERANCE_DEG = 60;
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

      const rawPath = coords.map(([lng, lat]) => [lat, lng]);
      const path = stripStartUTurn(rawPath);
      this._roadSegmentCache.set(key, path);
      return path;
    } catch (err) {
      console.warn("[ROUTE] 도로 경로를 가져오지 못해 직선으로 대체합니다:", err.message || err);
      this._roadSegmentCache.set(key, straightLine);
      return straightLine;
    }
  }
}

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

  spawnAtEvent(cameraViewModel, eventData) {
    const trackId = eventData.trackId != null ? String(eventData.trackId) : `#${Math.floor(100 + Math.random() * 900)}`;
    const lat = eventData.lat != null ? eventData.lat : cameraViewModel.lat;
    const lng = eventData.lng != null ? eventData.lng : cameraViewModel.lng;

    this.state = {
      plate: eventData.plate || null,
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

  clearAlertState() {
    if (!this.marker || !this.isAlertActive) return;
    this.isAlertActive = false;
    this.marker.setIcon(this._createIcon(false));
  }

  focusCurrent(mapManager, options = {}) {
    if (!this.marker) return false;
    const openPopup = options.openPopup !== false;
    const { lat, lng } = this.marker.getLatLng();
    mapManager.focus(lat, lng);
    if (openPopup) this.marker.openPopup();
    return true;
  }

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
      return;
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

    const TOTAL_DURATION_MS = 2700;
    let segIdx = 0;
    let lastPointElapsedTotal = 0;
    const overallStart = performance.now();

    const runSegment = () => {
      if (segIdx >= segLengths.length) {
        this.marker.setIcon(this._createIcon(this.isAlertActive));
        this.marker.setPopupContent(this.popupManager.buildVehiclePopup(this.state));
        this._animFrameId = null;
        resolve();
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

        const elapsedTotal = now - overallStart;
        if (elapsedTotal - lastPointElapsedTotal > 100 || t === 1) {
          routeManager.addTrajectoryPoint([lat, lng]);
          lastPointElapsedTotal = elapsedTotal;
          this.mapManager.panFollow(lat, lng);
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

  clearAlertState() {
    if (!this.marker || !this.isAlertActive) return;
    this.setAlertStyle(false, { type: "이동 중", reason: this.state ? this.state.reason : "-" });
  }

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

    this.mapManager.panFollow(lat, lng);
  }

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

class RealVehicleMarker {
  constructor(mapManager) {
    this.mapManager = mapManager;
    this.marker = null;
    this._animFrameId = null;
    this._frameLogCounter = 0;
    this._isAnimating = false;
    this._label = null;
  }

  _createIcon() {
    return L.divIcon({
      className: "",
      html: `<div class="vehicle-marker vehicle-marker--alert">🚗</div>`,
      iconSize: [30, 30],
      iconAnchor: [15, 15],
    });
  }

  setPosition(lat, lng, label) {
    console.log(
      "[REAL JOURNEY] setPosition 호출:",
      lat,
      lng,
      label
    );

    const map = this.mapManager.getMap();

    console.log(
      "[REAL JOURNEY] Leaflet map:",
      map
    );

    if (!map) {
      console.error(
        "[REAL JOURNEY] Leaflet map 객체가 없습니다."
      );
      return;
    }

    if (!this.marker) {
      console.log(
        "[REAL JOURNEY] 🚗 차량 마커 생성"
      );

      this.marker = L.marker(
        [lat, lng],
        {
          icon: this._createIcon(),
          zIndexOffset: 700
        }
      ).addTo(map);

    } else {
      console.log(
        "[REAL JOURNEY] 🚗 차량 마커 위치 갱신"
      );

      this.marker.setLatLng([lat, lng]);
    }

    // [main에서 이식] 위치가 갱신될 때마다 지도도 함께 따라간다("실시간으로
    // 보기" 버튼과 연동, mapManager.panFollow()/resumeFollow() 패턴은
    // VehicleManager와 동일 - 사용자가 지도를 직접 드래그하면 자동으로 멈춘다).
    this.mapManager.panFollow(lat, lng);

    if (label) {
      this.marker.bindTooltip(
        String(label),
        {
          permanent: false
        }
      );
    }

    // [유지: 사각지대 연출] "안 보이는 구간" 연출(hide()) 이후 다시
    // setPosition()이 호출되면(=재등장) 마커가 다시 보여야 하므로 항상
    // 불투명도를 되돌려놓는다. hide() 상태가 아니었을 때는 아무 효과 없다.
    this.marker.setOpacity(1);
  }

  // [main에서 이식: "이상감지 차량이 지도 위에서 실시간으로 움직이면서
  // 폴리라인이 실시간으로 그려져야해"]
  //
  // 예전 followPath()/_consumeQueue()는 payload가 올 때마다 애니메이션을
  // "큐"에 쌓았다 - 파이썬이 구간을 여러 번(직선 → 도로경로로 교체) 빠르게
  // 보내면 큐가 쌓여서, 파이썬을 이미 끈 뒤에도 오래된 애니메이션이 한참
  // 재생되며 지그재그로 겹쳐 그려지는 문제가 있었다(main에서 이미 고친 버그).
  //
  // 지금은 큐가 없다 - payload가 새로 오면 진행 중이던 애니메이션을 즉시
  // 취소하고(_cancelAnimation) 마커의 "현재 실제 화면 위치"에서 새 points
  // 배열 쪽으로 바로 이어서 애니메이션을 다시 시작한다.
  //
  // [사각지대 연출을 위해 main 대비 추가] onComplete 콜백 - 이번 호출에
  // 넘긴 points를 끝까지 다 소진하고 애니메이션이 멈췄을 때 1번 호출된다.
  // 사각지대 진입 지점(REAL_JOURNEY_GAP_WAYPOINT) 직전까지만 잘라서 넘긴
  // 뒤, 실제로 거기 도착한 시점에 마커를 숨기기 위해 필요하다
  // (RealVehicleJourneyListener 콜백 참고).
  animateAlong(points, label, onFrame, onComplete) {
    if (!points || points.length === 0) return;
    this._label = label;

    this._cancelAnimation();

    // 현재 마커 위치에서 새 points 배열상 가장 가까운 지점을 찾아 그 지점부터
    // 이어서 애니메이션한다 - 뒤로 순간이동하는 부자연스러운 점프를 막는다.
    let startIdx = 0;
    if (this.marker) {
      const cur = this.marker.getLatLng();
      let bestDist = Infinity;
      for (let i = 0; i < points.length; i++) {
        const d = haversineMeters([cur.lat, cur.lng], points[i]);
        if (d < bestDist) {
          bestDist = d;
          startIdx = i;
        }
      }
    }

    const passedPoints = points.slice(0, startIdx + 1);
    const remaining = points.slice(startIdx);

    if (remaining.length <= 1) {
      // 더 이동할 구간이 없다 - 위치만 즉시 맞추고 폴리라인은 전체 좌표로 그린다.
      const [lat, lng] = points[points.length - 1];
      this.setPosition(lat, lng, label);
      if (onFrame) onFrame(points);
      if (onComplete) onComplete();
      return;
    }

    this._isAnimating = true;
    this._runAnimatedSegments(remaining, passedPoints, label, onFrame, onComplete);
  }

  _runAnimatedSegments(remaining, passedPoints, label, onFrame, onComplete) {
    const self = this;
    const segLengths = [];
    for (let i = 1; i < remaining.length; i++) {
      segLengths.push(haversineMeters(remaining[i - 1], remaining[i]));
    }

    const SPEED_METERS_PER_SEC = 300;
    let segIdx = 0;

    const runSegment = () => {
      if (segIdx >= segLengths.length) {
        console.log("[REAL JOURNEY] 🚗 애니메이션 구간 이동 완료");
        self._animFrameId = null;
        self._isAnimating = false;
        if (onComplete) onComplete();
        return;
      }

      const from = remaining[segIdx];
      const to = remaining[segIdx + 1];
      const segLen = segLengths[segIdx] || 1;
      const segDuration = Math.max(200, (segLen / SPEED_METERS_PER_SEC) * 1000);
      const segStart = performance.now();

      const step = (now) => {
        const t = Math.min(1, (now - segStart) / segDuration);
        const lat = from[0] + (to[0] - from[0]) * t;
        const lng = from[1] + (to[1] - from[1]) * t;
        self.setPosition(lat, lng, label);
        if (onFrame) onFrame(passedPoints.concat([[lat, lng]]));

        self._frameLogCounter += 1;
        if (self._frameLogCounter % 10 === 0) {
          console.log("[REAL JOURNEY] 🚗 현재 위치", lat, lng);
        }

        if (t < 1) {
          self._animFrameId = requestAnimationFrame(step);
        } else {
          passedPoints.push(to);
          segIdx += 1;
          runSegment();
        }
      };
      self._animFrameId = requestAnimationFrame(step);
    };

    runSegment();
  }

  _cancelAnimation() {
    if (this._animFrameId) {
      cancelAnimationFrame(this._animFrameId);
      this._animFrameId = null;
    }
    this._isAnimating = false;
  }

  // [유지: 사각지대 연출] 카메라 사이 "사각지대" 구간(예: 동교동삼거리)
  // 연출용 - 마커를 지도에서 완전히 떼어내지 않고 투명하게만 만든다.
  // remove()와 달리 다음 setPosition() 호출로 그대로 이어서 다시 보이게
  // 할 수 있다. 큐가 없어졌으므로(clearQueue() 불필요) _cancelAnimation()과도
  // 무관하게 독립적으로 호출하면 된다.
  hide() {
    if (this.marker) this.marker.setOpacity(0);
  }

  remove() {
    this._cancelAnimation();

    if (this.marker) {
      const map = this.mapManager.getMap();

      if (map) {
        map.removeLayer(this.marker);
      }

      this.marker = null;

      console.log(
        "[REAL JOURNEY] 🚗 차량 마커 제거"
      );
    }
  }
}

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

  setTheme(theme) {
  if (theme !== "dark" && theme !== "light") return;
  this.theme = theme;
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

  showMessage(text) {
    if (!this.containerEl) return;
    const el = document.createElement("div");
    el.className = "ai-toast";
    el.innerHTML = `<div class="ai-toast__title">${text}</div>`;
    this.containerEl.appendChild(el);
    setTimeout(() => el.remove(), 3000);
  }
}

class ForzaBackgroundAnalyzer {
  constructor(demoCameraIdMap, forzaDemoSources) {
    this.demoCameraIdMap = demoCameraIdMap;
    this.forzaDemoSources = forzaDemoSources;
    this.sources = new Map();
    this.onEpisode = null;
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
      if (now < state.startTime) return;

      const elapsedSec = (now - state.startTime) / 1000;
      const virtualT = state.durationSec > 0 ? elapsedSec % state.durationSec : elapsedSec;

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

class ForzaDemoTimeline {
  constructor(demoCameraIdMap, forzaDemoSources) {
    this.demoCameraIdMap = demoCameraIdMap;
    this.forzaDemoSources = forzaDemoSources;
    this.stageOrder = ["A", "B", "C", "D"];
    this.currentStageIndex = -1;
    this._stageAnomalyFiredIndex = 0;
    this._anomalyEpisodesCache = new Map();
    this._stageDurations = new Map();
    this._stageStartAt = null;
    this._tickIntervalId = null;
    this._advanceTimeoutId = null;
    this._finished = false;

    this.onStageStart = null;
    this.onProgress = null;
    this.onStageEnd = null;
    this.onAnomaly = null;
    this.onFinished = null;
  }

  _currentDemoId() {
    return this.stageOrder[this.currentStageIndex] || null;
  }

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

  start() {
    setTimeout(() => this._begin(), CONFIG.FORZA_DEMO_START_DELAY_MS);
  }

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
        console.log(`[DEMO ${demoId}] 실제 영상 길이 확인: ${duration.toFixed(2)}s`);
      } catch (err) {
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
      console.error(`[DEMO ${demoId}] duration을 확인하지 못해 이 stage로 진행하지 않습니다.`);
      return;
    }

    this.currentStageIndex = index;
    const realCamId = this.demoCameraIdMap[demoId];
    const source = this.forzaDemoSources[realCamId];

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

  reset() {
    if (this._tickIntervalId) clearInterval(this._tickIntervalId);
    if (this._advanceTimeoutId) clearTimeout(this._advanceTimeoutId);
    this._tickIntervalId = null;
    this._advanceTimeoutId = null;
    this.currentStageIndex = -1;
    this._stageStartAt = null;
    this._finished = false;
    this._anomalyEpisodesCache.clear();
    this.start();
  }
}

class EventManager {
  constructor(cameraManager, vehicleManager, uiManager, routeManager, toastManager, videoSourceRegistry) {
    this.cameraManager = cameraManager;
    this.vehicleManager = vehicleManager;
    this.uiManager = uiManager;
    this.routeManager = routeManager;
    this.toastManager = toastManager;
    this.videoSourceRegistry = videoSourceRegistry;

    this.log = [];
    this.alertDetectionCount = 0;
    this.trackedVehicleCount = 0;
    this.activeTracks = new Map();

    this.currentSelectedCamera = null;

    this.vehicleCurrentCamera = null;
    this.demoSequenceIndex = -1;
    this._demoMovement = null;

    this.demoVideoFollowActive = false;

    this.demoEpisodes = new Map();

    this.demoOrder = ["A", "B", "C", "D"];

    // [신규] Real Journey 이벤트 카드 - 지금 활성 상태인 Real Journey 카드를
    // 하나만 참조로 들고 있는다(중복 카드 생성 방지용). RealVehicleMarker/
    // RealVehicleJourneyListener와는 무관하게, 오직 "카드가 이미 있는가"만
    // 판단하는 용도다 - upsertRealJourneyEvent()/resolveRealJourneyEvent() 참고.
    this._realJourneyLogEntry = null;
    // Real Journey 이벤트 카드를 클릭했을 때 무엇을 할지는 EventManager가 직접
    // 알지 못한다(RealVehicleMarker 인스턴스를 갖고 있지 않으므로) - 초기화부에서
    // 콜백을 연결해준다.
    this.onRealJourneyCardClick = null;

    this.listEl = document.getElementById("event-list");
    this.emptyEl = document.getElementById("event-empty");
    this.countEl = document.getElementById("event-count");
  }

  triggerAiEvent(record, eventData, options = {}) {
    const force = !!options.force;
    // [신규: 사용자 요청 - "실시간으로 보기 누르면 폴리라인 그리는 차량에 포커싱 돼서
    // 따라가게 해달라"] 기본값은 true(예전 그대로 - 카메라 핀으로 지도 확대/팝업)라서
    // 다른 호출부(mock 이벤트 WebSocket 등)는 그대로 동작한다. Real Journey 흐름
    // (omecca-track-vehicle-event 핸들러)에서만 false로 넘겨서, 카메라 핀이 아니라
    // 실제로 움직이는 Real Journey 차량 마커 쪽에 포커스를 맡긴다.
    const focusCameraPin = options.focusCameraPin !== false;
    const cameraViewModel = buildUticCameraViewModel(record, this.videoSourceRegistry);
    const normalized = Object.assign({ icon: "🚨", severity: "alert" }, eventData);
    const trackKey = eventData.trackId != null ? String(eventData.trackId) : null;

    if (this.toastManager) this.toastManager.show(cameraViewModel, normalized);

    this.log.unshift({ camera: cameraViewModel, event: normalized });
    this.renderPanel();

    this.cameraManager.setAlert(cameraViewModel.id, true);
    this.cameraManager.selectById(cameraViewModel.id, {
      openPopup: focusCameraPin,
      zoom: focusCameraPin,
      switchVideo: true,
      force,
    });

    // [삭제됨: 사용자 요청 - "중앙 화면 알림 팝업 클릭하면 저 TRACK.../추적 차량 팝업이
    // 잡혀서 뜨는데, 저거 안 뜨게 없애줘"] 예전엔 여기서 vehicleManager.spawnAtEvent()로
    // 지도 위에 별도의 "🚗 추적 차량" 마커+상세 팝업(번호판/Track ID/원인/현재 위치/
    // 감지 시간 등)을 항상 만들었다. CCTV 전환(위 selectById switchVideo:true)과
    // 카메라 핀 강조(setAlert)만으로도 "지도에서 실시간으로 보기" 요구사항은 충분히
    // 충족되므로, 더 이상 이 별도 마커/팝업을 만들지 않는다.

    this.alertDetectionCount += 1;
    this._markTrackActive(trackKey, cameraViewModel.id);

    this.uiManager.setLastUpdate(eventData.time);
    this.updateStats();
  }

  advanceDemoRoute(demoRealCamId) {
    console.warn(
      "[DEMO] advanceDemoRoute()는 더 이상 자동으로 호출되지 않습니다."
    );
  }

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

    const isNewEpisode = !this.demoEpisodes.has(globalVehicleId);

    if (isNewEpisode && cameraViewModel.demoId && cameraViewModel.demoId !== this.demoOrder[0]) {
      console.log(
        `[DEMO] ${cameraViewModel.demoId} 지점에서 감지되었지만 아직 ${this.demoOrder[0]}(시작 지점)에서 알림이 생성되지 않아 무시합니다.`
      );
      return;
    }

    if (!isNewEpisode) {
      this._markTrackActive(globalVehicleId, cameraViewModel.id);
      this.updateStats();
      return;
    }

    if (this.toastManager) this.toastManager.show(cameraViewModel, normalized);

    const logEntry = { camera: cameraViewModel, event: normalized };
    this.log.unshift(logEntry);

    this.demoEpisodes.set(globalVehicleId, {
      firstDetectedAt: eventData.time,
      firstDetectedCamera: demoRealCamId,
      logEntry,
    });

    this.alertDetectionCount += 1;

    this.cameraManager.setAlert(cameraViewModel.id, true);
    this.vehicleManager.setAlertStyle(true, eventData);
    this.trackedVehicleCount = this.vehicleManager.marker ? 1 : this.trackedVehicleCount;

    this._markTrackActive(globalVehicleId, cameraViewModel.id);

    this.uiManager.setLastUpdate(eventData.time);
    this.updateStats();
    this.renderPanel();

    this._forwardDemoEventToGateway(demoRealCamId, cameraViewModel, eventData, globalVehicleId);
  }

  _forwardDemoEventToGateway(demoRealCamId, cameraViewModel, eventData, globalVehicleId) {
    const payload = {
      source_type: "DEMO",
      source_id: demoRealCamId,
      latitude: cameraViewModel.lat,
      longitude: cameraViewModel.lng,
      anomaly: true,
      global_vehicle_id: globalVehicleId,
      track_id: eventData.trackId,
      plate: eventData.plate || null,
      reason: eventData.reason || null,
      confidence: eventData.confidence,
      location_name: cameraViewModel.location,
      time: eventData.time,
      timestamp: Date.now() / 1000,
    };

    fetch(CONFIG.MAP_EVENTS_POST_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
      .then((res) => {
        if (!res.ok) {
          console.warn(`[DEMO→GATEWAY] POST ${CONFIG.MAP_EVENTS_POST_URL} 실패 (HTTP ${res.status})`);
        } else {
          console.log("[DEMO→GATEWAY] Forza DEMO 알림을 게이트웨이로 전달했습니다.", payload);
        }
      })
      .catch((err) => {
        console.warn(`[DEMO→GATEWAY] 전달 실패(서버 미기동 등) - 지도 표시에는 영향 없음:`, err.message);
      });
  }

  beginDemoStageMovement(demoId, realCamId) {
    this.vehicleCurrentCamera = realCamId;

    if (this.demoVideoFollowActive) {
      this.cameraManager.selectById(realCamId, { openPopup: false, zoom: false, switchVideo: true, force: true });
    }

    const stageIdx = this.demoOrder.indexOf(demoId);
    const nextIdx = stageIdx + 1;
    if (nextIdx >= this.demoOrder.length) {
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

    this.routeManager.getRoadSegment([fromVM.lat, fromVM.lng], [toVM.lat, toVM.lng]).then((pathPoints) => {
      if (this._demoMovement !== movement) return;
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

  updateDemoStageProgress(demoId, progress) {
    const movement = this._demoMovement;
    if (!movement || !movement.ready) return;

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

    this.vehicleManager.setPositionForDemo(point, movement.toVM);
    this.routeManager.addTrajectoryPoint(point);
    this.trackedVehicleCount = this.vehicleManager.marker ? 1 : this.trackedVehicleCount;
  }

  completeDemoStageMovement(demoId, realCamId) {
    const movement = this._demoMovement;

    const nextIdx = this.demoOrder.indexOf(demoId) + 1;
    if (nextIdx < this.demoOrder.length) {
      const nextDemoId = this.demoOrder[nextIdx];
      const nextRealCamId = CONFIG.DEMO_CAMERA_ID_MAP[nextDemoId];

      if (movement && movement.toVM) {
        this.vehicleManager.setPositionForDemo([movement.toVM.lat, movement.toVM.lng], movement.toVM);
        if (movement.pathPoints && movement.pathPoints.length) {
          this.routeManager.addTrajectoryPoint(movement.pathPoints[movement.pathPoints.length - 1]);
        }
        this.trackedVehicleCount = this.vehicleManager.marker ? 1 : this.trackedVehicleCount;
      } else {
        console.warn(
          `completeDemoStageMovement: ${demoId}→${nextDemoId} 구간의 도로 경로가 아직 준비되지 않아 정확한 좌표로 스냅하지 못했습니다.`
        );
      }

      this.vehicleCurrentCamera = nextRealCamId;
      this.demoSequenceIndex = nextIdx;

      if (!this.trajectorySegments) this.trajectorySegments = [];
      this.trajectorySegments.push({ from: realCamId, to: nextRealCamId, globalVehicleId: CONFIG.DEMO_VEHICLE_ID });
    }
    this._demoMovement = null;
    this.renderPanel();
  }

  resetDemoSession() {
    this.routeManager.clearTrajectory();
    this.vehicleManager.reset();
    this.activeTracks.forEach((entry) => clearTimeout(entry.timerId));
    this.activeTracks.clear();
    this.trackedVehicleCount = 0;
    this.demoEpisodes.clear();
    this.trajectorySegments = [];
    this.vehicleCurrentCamera = null;
    this.demoSequenceIndex = -1;
    this._demoMovement = null;
    this.updateStats();
    if (window.forzaDemoTimeline) window.forzaDemoTimeline.reset();
  }

  // ---- [신규] Real Journey 이벤트 리스트 통합 ----
  // active=true payload가 올 때마다 호출된다. 이미 활성 카드(this._realJourneyLogEntry)가
  // 있으면 그 카드의 내용(카메라명/ID)만 갱신하고 새 카드를 만들지 않는다(요구사항:
  // "하나의 활성 Real Journey는 이벤트 리스트에 카드 1개만"). 처음 호출될 때만
  // this.log에 새 항목을 unshift한다.
  //
  // [변경: "서버 파이프라인 대신 postMessage 방식으로 전환"]
  // 이전에는 POST /api/map/events → gateway → /topic/events 경로로 오른쪽 React
  // 이벤트 리스트에 전달했다. 이번 요청으로 그 경로는 "일단 사용하지 않고"(완전히
  // 삭제하지는 않음 - _forwardRealJourneyEventToGateway 메서드는 아래 그대로 남겨둠,
  // 더 이상 호출만 안 함), CCTV 바로가기 때 이미 성공적으로 쓰던 iframe→부모 React
  // 통신 방식(window.parent.postMessage)을 그대로 재사용한다.
  upsertRealJourneyEvent(payload) {
    let entry = this._realJourneyLogEntry;

    if (!entry) {
      // [신규: "음주운전이랑 관심대상 기능 합치기"] payload.reason("DUI"/"TARGET")에
      // 맞춰 카드 문구도 알림 카드/팝업과 동일한 기준으로 바꾼다.
      const normalized = {
        icon: payload.reason === "TARGET" ? "🎯" : "🚨",
        type: payload.reason === "TARGET" ? "관심 차량 감지" : "이상운전 감지",
        severity: "alert",
        time: new Date().toLocaleTimeString("ko-KR", { hour12: false }),
        sourceType: "REAL_JOURNEY", // renderPanel()의 클릭 분기 + plate 표시 분기에서 사용
        statusText: "이동 중",
      };
      const camera = {
        location: payload.currentCamName || payload.currentCamId || "-",
        id: payload.currentCamId,
      };
      entry = { camera, event: normalized };
      this._realJourneyLogEntry = entry;
      this.log.unshift(entry);
      this.alertDetectionCount += 1; // "사건" 단위로 1회만 증가 - 이후 갱신은 카운트하지 않음

      // [변경] 최초(=이 사건의 첫) active=true일 때만 1번 postMessage로 부모(React
      // 대시보드)에 알린다 - A→B→C→D 이동 중 계속 오는 후속 payload(else 분기)는
      // 절대 다시 보내지 않는다(중복 방지).
      this._postRealJourneyEventToParent(payload);
    } else {
      entry.camera.location = payload.currentCamName || payload.currentCamId || entry.camera.location;
      entry.camera.id = payload.currentCamId;
      entry.event.statusText = "이동 중";
    }

    this.renderPanel();
    this.updateStats();
  }

  // [신규] Real Journey의 최초 감지를 CCTV 바로가기와 동일한 방식(iframe→부모
  // window.parent.postMessage)으로 부모 React 대시보드에 알린다. 대상 origin은
  // 기존 CCTV 바로가기 코드(window.__appSelectCamera 등)가 이미 쓰고 있는 "*"를
  // 그대로 맞춘다 - 특정 포트로 고정하면 개발 환경마다 포트가 달라질 때(또는 다른
  // origin에서 iframe이 열릴 때) 조용히 씹히는 문제가 생길 수 있어, 이미 검증된
  // 기존 관례를 그대로 따랐다.
  _postRealJourneyEventToParent(payload) {
    if (!(window.parent && window.parent !== window)) {
      console.warn("[REAL JOURNEY→DASHBOARD] iframe 밖에서 실행 중이라 postMessage를 보낼 부모가 없습니다.");
      return;
    }

    const eventPayload = {
      id: `real-journey-${payload.currentCamId || "unknown"}-${Date.now()}`,
      icon: payload.reason === "TARGET" ? "🎯" : "🚨",
      type: payload.reason === "TARGET" ? "관심 차량 감지" : "이상운전 감지",
      severity: "alert",
      time: new Date().toLocaleTimeString("ko-KR", { hour12: false }),
      camId: payload.currentCamId,
      cameraName: payload.currentCamName,
      trackId: payload.trackId || null,
      plate: payload.plate || null, // 없으면 지어내지 않고 그대로 null - App.jsx 쪽에서 "차량번호 확인 중"으로 표시
      status: "이동 중",
    };

    window.parent.postMessage({ type: "real-journey-event", event: eventPayload }, "*");
    console.log("[REAL JOURNEY→DASHBOARD] postMessage 전송:", eventPayload);
  }

  // [비활성화됨 - 일단 사용하지 않음] 서버 파이프라인(POST /api/map/events) 방식.
  // 완전히 삭제하지는 않았다 - 나중에 다시 필요해지면 upsertRealJourneyEvent()에서
  // this._postRealJourneyEventToParent(payload) 대신 이 메서드를 다시 호출하면 된다.
  _forwardRealJourneyEventToGateway(payload) {
    const latestPoint =
      Array.isArray(payload.points) && payload.points.length > 0
        ? payload.points[payload.points.length - 1]
        : null;

    const latitude =
      payload.currentCamLat ?? payload.currentLat ?? payload.latitude ?? latestPoint?.lat ?? null;
    const longitude =
      payload.currentCamLng ?? payload.currentLng ?? payload.longitude ?? latestPoint?.lng ?? null;

    if (latitude == null || longitude == null) {
      console.warn("[REAL JOURNEY→GATEWAY] 좌표를 확인할 수 없어 이벤트를 전송하지 않습니다.", payload);
      return;
    }

    const eventPayload = {
      source_type: "UTIC", // REAL_JOURNEY는 서버가 허용하지 않으므로 사용 금지
      source_id: payload.currentCamId || "REAL-JOURNEY",
      latitude,
      longitude,
      anomaly: true,
      track_id: payload.trackId ?? null,
      plate: payload.plate ?? null,
      reason: "이상운전 감지",
      confidence: payload.confidence ?? null,
      location_name: payload.currentCamName || payload.currentCamId || "-",
      time: new Date().toLocaleTimeString("ko-KR", { hour12: false }),
      timestamp: Date.now() / 1000,
    };

    // CONFIG.MAP_EVENTS_POST_URL을 그대로 재사용 - 새 URL 안 만듦.
    fetch(CONFIG.MAP_EVENTS_POST_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(eventPayload),
    })
      .then((res) => {
        if (!res.ok) {
          console.warn(`[REAL JOURNEY→GATEWAY] 이벤트 전송 실패: HTTP ${res.status}`);
          return;
        }
        console.log("[REAL JOURNEY→GATEWAY] 이벤트 리스트 전송 성공:", eventPayload);
      })
      .catch((err) => {
        console.warn("[REAL JOURNEY→GATEWAY] 이벤트 전송 실패:", err.message);
      });
  }

  // active=false(여정 종료) payload가 오면 호출된다. 카드 자체는 로그에서 지우지 않고
  // (다른 이벤트들과 동일하게 "발생 이력"으로 남긴다) 상태 텍스트만 "종료됨"으로 바꾼다.
  // this._realJourneyLogEntry 참조는 끊어서, 다음번 active=true는 새 카드로 취급되게 한다.
  resolveRealJourneyEvent() {
    if (this._realJourneyLogEntry) {
      this._realJourneyLogEntry.event.statusText = "종료됨";
      this._realJourneyLogEntry = null;
      this.renderPanel();
    }
  }

  _markTrackActive(trackKey, camId) {
    if (!trackKey) return;

    const existing = this.activeTracks.get(trackKey);
    if (existing) clearTimeout(existing.timerId);

    const timerId = setTimeout(() => this._expireTrack(trackKey), CONFIG.ANOMALY_ACTIVE_MS);
    this.activeTracks.set(trackKey, { camId, timerId });
  }

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

        // [수정: Real Journey 통합] Real Journey 카드는 trackId가 없으므로(항상
        // "-"로 나오는 것을 방지) 번호판 행을 명시적으로 "차량번호 확인 중"(또는
        // 실제 LPR 값이 나중에 연결되면 그 값)으로 표시한다 - 절대 임의 번호를 지어내지 않는다.
        const plateOrTrack =
          event.sourceType === "REAL_JOURNEY"
            ? `<span class="event-card__label">차량번호</span><span class="event-card__value event-card__value--plate">${
                event.plate || PLATE_UNKNOWN_LABEL_MAP_JS
              }</span>`
            : event.plate
            ? `<span class="event-card__label">차량번호</span><span class="event-card__value event-card__value--plate">${event.plate}</span>`
            : `<span class="event-card__label">Track ID</span><span class="event-card__value event-card__value--plate">${
                event.trackId != null ? event.trackId : "-"
              }</span>`;

        // [신규] Real Journey 카드에만 "상태"(이동 중/종료됨) 행을 추가로 보여준다.
        const statusRow = event.statusText
          ? `<span class="event-card__label">상태</span><span class="event-card__value">${event.statusText}</span>`
          : "";

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

              ${statusRow}
              ${confidenceRow}
            </div>
          </div>
        `;
      })
      .join("");

    this.listEl.innerHTML = `<div id="event-empty" class="event-empty" style="display:none"></div>${cardsHtml}`;
    this.emptyEl = document.getElementById("event-empty");

    this.listEl.querySelectorAll(".event-card").forEach((cardEl) => {
      cardEl.addEventListener("click", () => {
        const index = parseInt(cardEl.dataset.logIndex, 10);
        const entry = this.log[index];
        if (!entry) return;

        // [수정: Real Journey 통합] Real Journey 카드는 UTIC 카메라 선택 로직이
        // 아니라, 지도 이동 + 차량 마커 팝업 열기를 해야 한다 - 초기화부에서
        // 연결해준 콜백(onRealJourneyCardClick)에 위임한다. cameraManager를
        // 통한 기존 클릭 동작은 손대지 않는다(else 분기 그대로).
        if (entry.event.sourceType === "REAL_JOURNEY") {
          if (this.onRealJourneyCardClick) this.onRealJourneyCardClick();
          return;
        }

        this.cameraManager.selectById(entry.camera.id, { openPopup: true, zoom: true, switchVideo: true });
      });
    });
  }
}

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
        this.lastSeq = data.seq;
        return;
      }

      if (data.seq !== this.lastSeq) {
        this.lastSeq = data.seq;
        if (data.seq > 0) this.onEvent(data);
      }
    } catch (err) {
      if (!this._warned) {
        console.warn("AI 이벤트 폴링 대기 중 (data/event.json 을 찾을 수 없습니다).", err);
        this._warned = true;
      }
    }
  }
}

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
      this._warned = false;
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
   [재활성화됨: "알림 팝업 구현"] RealJourneyAlertManager - active=true가 될
   때마다 화면 우상단(고정 위치)에 Alert Card를 띄운다. 한동안 EventManager.
   upsertRealJourneyEvent()의 오른쪽 이벤트 리스트 카드로만 대체했었는데,
   이제 둘 다 함께 쓴다 - 리스트 카드는 발생 이력을, 이 카드는 지금 이
   순간 눈에 바로 띄는 알림을 담당한다. 번호판(payload.plate)이 오면 함께
   표시한다(초기화부의 RealVehicleJourneyListener 콜백 참고).
================================================== */
class RealJourneyAlertManager {
  constructor(mapManager) {
    this.mapManager = mapManager;
    this.el = null;
    this._injectStyleOnce();
  }

  _injectStyleOnce() {
    if (document.getElementById("real-journey-alert-style")) return;
    const style = document.createElement("style");
    style.id = "real-journey-alert-style";
    style.textContent = `
      @keyframes rjaSlideIn { from { transform: translateX(120%); opacity: 0; } to { transform: translateX(0); opacity: 1; } }
      .real-journey-alert-card {
        position: fixed; top: 84px; right: 20px; z-index: 6000;
        width: 250px; background: rgba(18,18,22,0.95); color: #f2f2f2;
        border: 1px solid rgba(239,68,68,0.55); border-radius: 10px;
        box-shadow: 0 0 16px rgba(239,68,68,0.3), 0 4px 14px rgba(0,0,0,0.45);
        padding: 14px 16px; font-family: inherit; font-size: 13px;
        animation: rjaSlideIn 0.35s ease-out;
      }
      .real-journey-alert-card .rja-title {
        font-weight: 700; font-size: 14px; color: #ff5c5c; margin-bottom: 8px;
      }
      .real-journey-alert-card .rja-row {
        display: flex; justify-content: space-between; margin: 4px 0; color: #dcdcdc;
      }
      .real-journey-alert-card .rja-row .rja-label { color: #9a9a9a; }
      .real-journey-alert-card .rja-focus-btn {
        margin-top: 10px; width: 100%; padding: 7px 0; border-radius: 6px;
        border: 1px solid rgba(239,68,68,0.5); background: rgba(239,68,68,0.14);
        color: #ff8f8f; font-size: 12px; cursor: pointer;
      }
      .real-journey-alert-card .rja-focus-btn:hover { background: rgba(239,68,68,0.26); }
    `;
    document.head.appendChild(style);
  }

  show({ camName, camId, plate, lat, lng, reason }) {
    const isNew = !this.el;
    if (isNew) {
      this.el = document.createElement("div");
      this.el.className = "real-journey-alert-card";
      document.body.appendChild(this.el);
    }

    // [신규: "음주운전이랑 관심대상 기능 합치기"] 백엔드(test_suspicious_driving.py의
    // journey.reason)가 이번 여정이 음주운전 확정 때문인지, 등록된 관심 차량
    // 매칭 때문인지 함께 보내준다. 같은 프레임에 둘 다 감지되면 음주운전이
    // 우선이므로 reason도 그 기준을 그대로 따른다 - 여기선 표시 문구만 바꾼다.
    const title = reason === "TARGET" ? "🎯 관심 차량 감지" : "🚨 이상운전 차량 감지";

    const plateLabel = plate || PLATE_UNKNOWN_LABEL_MAP_JS;
    this.el.innerHTML = `
      <div class="rja-title">${title}</div>
      <div class="rja-row"><span class="rja-label">CCTV</span><span class="rja-value">${camName || "-"}</span></div>
      ${camId ? `<div class="rja-row"><span class="rja-label">CCTV ID</span><span class="rja-value">${camId}</span></div>` : ""}
      <div class="rja-row"><span class="rja-label">차량</span><span class="rja-value">${plateLabel}</span></div>
      <div class="rja-row"><span class="rja-label">상태</span><span class="rja-value">이동 중</span></div>
      <button type="button" class="rja-focus-btn">지도에서 확인</button>
    `;

    const btn = this.el.querySelector(".rja-focus-btn");
    btn.onclick = () => {
      if (lat != null && lng != null) this.mapManager.focus(lat, lng);
    };

    if (isNew) {
      console.log("[REAL JOURNEY ALERT] 🚨 새 이상운전 알림 카드 생성", { camName, camId });
    }
  }

  hide() {
    if (this.el) {
      this.el.remove();
      this.el = null;
      console.log("[REAL JOURNEY ALERT] 알림 카드 제거(여정 종료)");
    }
  }
}

const PLATE_UNKNOWN_LABEL_MAP_JS = "차량번호 확인 중";

// [신규] Real Journey 차량 마커에 붙일 상세 팝업 HTML을 만든다. PopupManager와
// 완전히 별개의 함수다 - PopupManager는 Forza/UTIC 추적 차량(window.__appSelectCamera
// 등)에 강하게 묶여 있어서, Real Journey에 그대로 재사용하면 엉뚱한 콜백을
// 참조하게 된다. 요구사항의 X 버튼은 별도로 만들지 않는다 - Leaflet의 기본
// 팝업 닫기 버튼(closeButton:true)이 "팝업만 닫고 마커/Journey는 그대로 유지"를
// 정확히 그대로 해준다.
//
// [버그 수정: "CCTV 바로가기 버튼을 눌러도 반응 없음"]
// 원인: Leaflet의 Popup은 popup 컨테이너를 만들 때 내부적으로
// L.DomEvent.disableClickPropagation(container)를 자동으로 호출한다(지도 클릭과
// 겹치지 않도록 하는 Leaflet 표준 동작). 그래서 popup 안에서 발생한 click 이벤트는
// popup 컨테이너 지점에서 버블링이 완전히 끊기고, document까지 절대 전파되지 않는다
// - 그 결과 document.addEventListener("click", ...) 같은 문서 레벨 이벤트 위임
// (delegation) 방식으로는 이 버튼 클릭을 영원히 받을 수 없었다(파일 아래쪽에
// 있던 delegation 리스너를 제거한 이유).
// 반면 버튼 자신에게 직접 붙는 인라인 onclick은 이 전파 차단과 무관하게 항상
// 정상 동작한다 - 아래(다른 팝업, PopupManager.buildVehiclePopup)의 "CCTV 영상
// 보기" 버튼도 원래 이 방식이었다. window.__appGoToJourneyStartCctv는 파일
// 최상단(CONFIG 바로 다음)에 정의돼 있어 이 시점엔 이미 항상 존재한다.
function buildRealJourneyPopupHtml(payload) {
  // [수정: "알림 팝업에 차량 번호까지"] 이제 백엔드(test_suspicious_driving.py의
  // send_journey_update)가 매칭된 관심 차량의 번호판을 payload.plate로 함께
  // 보낸다. 아직 OCR로 확정 전이면 null - 그 경우에만 대체 라벨을 쓴다(지어내지
  // 않음).
  const plate = payload.plate || PLATE_UNKNOWN_LABEL_MAP_JS;
  // [신규: "음주운전이랑 관심대상 기능 합치기"] payload.reason("DUI"/"TARGET")에
  // 맞춰 팝업 제목도 우상단 알림 카드와 동일한 기준으로 바꾼다.
  const popupTitle = payload.reason === "TARGET" ? "🎯 관심 차량 감지" : "🚨 이상운전 감지";
  return `
    <div class="cctv-popup">
      <div class="cctv-popup__header">
        <div class="cctv-popup__title">
          <span class="cctv-popup__name">${popupTitle}</span>
        </div>
      </div>
      <div class="cctv-popup__body">
        <span class="cctv-popup__label">CCTV</span>
        <span class="cctv-popup__value">${payload.currentCamName || "-"}</span>

        <span class="cctv-popup__label">CCTV ID</span>
        <span class="cctv-popup__value">${payload.currentCamId || "-"}</span>

        <span class="cctv-popup__label">차량번호</span>
        <span class="cctv-popup__value">${plate}</span>

        <span class="cctv-popup__label">상태</span>
        <span class="cctv-popup__value">이동 중</span>

        <button
          type="button"
          class="popup-btn real-journey-cctv-btn"
          onclick="window.__appGoToJourneyStartCctv && window.__appGoToJourneyStartCctv('${payload.currentCamId || ""}')"
        >
          📹 CCTV 바로가기
        </button>
      </div>
    </div>
  `;
}

class RealVehicleJourneyListener {
  constructor(stompUrl, onUpdate) {
    this.stompUrl = stompUrl;
    this.onUpdate = onUpdate;
    this.client = null;
  }

  _loadScript(src) {
    return new Promise((resolve, reject) => {
      if (document.querySelector(`script[src="${src}"]`)) {
        resolve();
        return;
      }
      const script = document.createElement("script");
      script.src = src;
      script.onload = () => resolve();
      script.onerror = () => reject(new Error(`스크립트 로딩 실패: ${src}`));
      document.head.appendChild(script);
    });
  }

  async start() {
    try {
      await this._loadScript("https://cdn.jsdelivr.net/npm/sockjs-client@1.6.1/dist/sockjs.min.js");
      await this._loadScript("https://cdn.jsdelivr.net/npm/@stomp/stompjs@7.0.0/bundles/stomp.umd.min.js");
    } catch (err) {
      console.warn("[REAL JOURNEY] STOMP/SockJS 라이브러리 로딩 실패 - 실시간 경로 표시를 사용할 수 없습니다.", err);
      return;
    }

    if (typeof SockJS === "undefined" || typeof StompJs === "undefined") {
      console.warn("[REAL JOURNEY] SockJS/StompJs 전역 객체를 찾을 수 없습니다.");
      return;
    }

    this.client = new StompJs.Client({
      webSocketFactory: () => new SockJS(this.stompUrl),
      reconnectDelay: 3000,
      onConnect: () => {
        console.log(`[REAL JOURNEY] STOMP 연결됨: ${this.stompUrl}`);
        this.client.subscribe("/topic/cctv/journey", (message) => {
          try {
            const payload = JSON.parse(message.body);

            console.log("[REAL JOURNEY] PAYLOAD 수신:", payload);

            this.onUpdate(payload);
          } catch (err) {
            console.warn("[REAL JOURNEY] payload 파싱 실패:", err);
          }
        });
      },
      onStompError: (frame) => {
        console.warn("[REAL JOURNEY] STOMP 오류:", frame.headers && frame.headers.message);
      },
    });
    this.client.activate();
  }

  stop() {
    if (this.client) this.client.deactivate();
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const mapManager = new MapManager("map");
  const popupManager = new PopupManager();
  const videoManager = new VideoManager();
  const routeManager = new RouteManager(mapManager.getMap());
  const vehicleManager = new VehicleManager(mapManager, popupManager);
  const videoSourceRegistry = new VideoSourceRegistry();
  const uticCameraManager = new UticCameraManager(mapManager, videoManager, videoSourceRegistry);
  const toastManager = new ToastManager(document.getElementById("ai-toast-container"));

  const videoModalManager = new VideoModalManager(
    document.getElementById("video-frame"),
    () => document.getElementById("video-overlay-title").textContent
  );

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
  uiManager.updateHeaderStats({ cameraCount: 0, trackedVehicleCount: 0, alertVehicleCount: 0, alertDetectionCount: 0 });

  window.addEventListener("message", (event) => {
    const data = event.data;
    if (data && data.type === "omecca-theme" && (data.theme === "dark" || data.theme === "light")) {
      uiManager.setTheme(data.theme);
    }

    if (data && data.type === "omecca-view-mode") {
      document.documentElement.classList.toggle("show-video-panel", !!data.showVideoPanel);
    }

    if (data && data.type === "omecca-focus-tracked-vehicle") {
      mapManager.resumeFollow();
      const focused = vehicleManager.focusCurrent(mapManager);
      if (!focused) {
        toastManager.showMessage("🚗 현재 추적 중인 차량이 없습니다");
      }
    }

    if (data && data.type === "omecca-track-vehicle-event") {
      mapManager.resumeFollow();
      const payload = data.vehicle || {};
      const record = payload.camId ? uticCameraManager.getRecordById(payload.camId) : null;
      const eventData = {
        trackId: payload.trackId,
        lat: payload.lat,
        lng: payload.lng,
        plate: payload.plate || null,
        type: payload.type || "이상 감지",
        reason: payload.reason || "-",
        confidence: payload.confidence != null ? payload.confidence : null,
        time: payload.time || new Date().toLocaleTimeString("ko-KR", { hour12: false }),
      };

      if (record) {
        // [수정: 사용자 요청 - "실시간으로 보기 누르면 다른 곳(카메라 핀)에 포커싱
        // 된다, 폴리라인 그리는 차량에 포커싱 돼서 따라가게 해달라"] focusCameraPin:
        // false를 넘겨서 CCTV 화면 전환(switchVideo)만 하고, 지도 확대/카메라 핀
        // 팝업은 열지 않는다 - 포커스는 아래에서 실제로 움직이는 Real Journey 차량
        // 마커(realVehicleMarker) 쪽으로 보낸다.
        eventManager.triggerAiEvent(record, eventData, { force: true, focusCameraPin: false });
        scheduleBeforeAfterCapture(eventData.trackId);
      } else if (payload.lat != null && payload.lng != null) {
        const fallbackCam = {
          id: payload.camId || `EVT-${eventData.trackId || eventData.time}`,
          name: payload.locationLabel || payload.camId || "-",
          lat: payload.lat,
          lng: payload.lng,
        };
        vehicleManager.spawnAtEvent(fallbackCam, eventData);
        toastManager.showMessage("📹 이 카메라는 실시간 CCTV 연동 대상이 아닙니다");
      } else {
        toastManager.showMessage("🚗 위치 정보가 없어 지도에 표시할 수 없습니다");
      }

      // [신규] 폴리라인을 따라 실제로 움직이는 Real Journey 차량 마커로 지도를
      // 이동시키고 그 마커의 상세 팝업을 연다 - 이벤트 리스트의 "Real Journey 카드"를
      // 클릭했을 때(위 eventManager.onRealJourneyCardClick)와 동일한 동작이다.
      // realVehicleMarker.marker가 아직 없으면(여정의 첫 좌표가 아직 안 왔으면)
      // 아무 것도 하지 않는다 - mapManager.resumeFollow()로 이미 추적 모드는 켜져
      // 있으므로, 다음 좌표가 도착하면(RealVehicleMarker.setPosition) 자동으로
      // 따라가기 시작한다.
      if (realVehicleMarker.marker) {
        const { lat, lng } = realVehicleMarker.marker.getLatLng();
        mapManager.focus(lat, lng);
        realVehicleMarker.marker.openPopup();
      } else {
        vehicleManager.focusCurrent(mapManager, { openPopup: false });
      }
    }
  });
  if (window.parent && window.parent !== window) {
    window.parent.postMessage({ type: "omecca-map-ready" }, "*");
  }

  const eventManager = new EventManager(
    uticCameraManager,
    vehicleManager,
    uiManager,
    routeManager,
    toastManager,
    videoSourceRegistry
  );

  uticCameraManager.onCameraSelected = (record) => {
    eventManager.currentSelectedCamera = record.cam_id;
  };

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
      confidence: null,
    });
  };

  // [수정] CONFIG.ENABLE_FORZA_DEMO가 false면(기본값) 아래 발표용 데모를 아예 만들지도
  // 시작하지도 않는다. 다만 예전에 이미 떠 있던 낡은 DEMO-DRUNK-001 이벤트/팝업이
  // 화면에 남아있을 수 있으니, reset 요청은 데모 켜짐 여부와 무관하게 항상 보내서
  // 정리한다.
  fetch("http://localhost:4000/api/map/demo/reset", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ trackId: CONFIG.DEMO_VEHICLE_ID }),
  })
    .then((res) => res.json())
    .then((body) => console.log("[DEMO→GATEWAY] 페이지 로드 시 이전 데모 이벤트 초기화:", body))
    .catch((err) => console.warn("[DEMO→GATEWAY] 초기화 요청 실패(서버 미기동 등):", err.message));

  if (CONFIG.ENABLE_FORZA_DEMO) {
    const forzaDemoTimeline = new ForzaDemoTimeline(CONFIG.DEMO_CAMERA_ID_MAP, CONFIG.FORZA_DEMO_SOURCES);

    forzaDemoTimeline.onStageStart = (demoId, realCamId) => {
      console.log(`[DEMO] ${demoId}(${realCamId}) stage 시작`);
      eventManager.beginDemoStageMovement(demoId, realCamId);
    };

    forzaDemoTimeline.onProgress = (demoId, progress) => {
      eventManager.updateDemoStageProgress(demoId, progress);
    };

    forzaDemoTimeline.onStageEnd = (demoId, realCamId) => {
      console.log(`[DEMO] ${demoId}(${realCamId}) stage 종료 - 다음 stage로 자동 전환`);
      eventManager.completeDemoStageMovement(demoId, realCamId);
    };

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
        confidence: null,
      });
    };

    forzaDemoTimeline.onFinished = () => {
      console.log("[DEMO] 발표용 Forza DEMO 시나리오가 모두 끝났습니다. 차량은 D(한강대교남단)에 고정된 상태로 유지됩니다.");
    };

    forzaDemoTimeline.start();
    window.forzaDemoTimeline = forzaDemoTimeline;
  }

  function captureVideoFrame(videoEl) {
    if (!videoEl || videoEl.readyState < 2 || !videoEl.videoWidth || !videoEl.videoHeight) return null;
    const canvas = document.createElement("canvas");
    canvas.width = videoEl.videoWidth;
    canvas.height = videoEl.videoHeight;
    const ctx = canvas.getContext("2d");
    ctx.drawImage(videoEl, 0, 0, canvas.width, canvas.height);

    try {
      const log = videoManager.trackLogCache;
      const frame = log && log.frames ? videoManager._findNearestFrame(log.frames, videoEl.currentTime) : null;
      if (log && log.width && log.height && frame && frame.boxes) {
        const scaleX = canvas.width / log.width;
        const scaleY = canvas.height / log.height;
        frame.boxes.forEach((b) => {
          const x = b.x1 * scaleX;
          const y = b.y1 * scaleY;
          const w = (b.x2 - b.x1) * scaleX;
          const h = (b.y2 - b.y1) * scaleY;
          ctx.lineWidth = b.alert ? 4 : 2;
          ctx.strokeStyle = b.alert ? "#ff3b3b" : "rgba(56, 189, 248, 0.6)";
          ctx.strokeRect(x, y, w, h);
          if (b.alert) {
            ctx.fillStyle = "#ff3b3b";
            ctx.font = "bold 22px sans-serif";
            ctx.fillText("이상 주행 감지", x, Math.max(y - 10, 24));
          }
        });
      }
    } catch (err) {
      console.warn("[CAPTURE] 바운딩 박스 합성 실패:", err.message);
    }

    try {
      return canvas.toDataURL("image/jpeg", 0.85);
    } catch (err) {
      console.warn("[CAPTURE] 프레임 캡쳐 실패:", err.message);
      return null;
    }
  }

  function uploadCaptures(trackId, beforeImage, afterImage) {
    if (!trackId || (!beforeImage && !afterImage)) return;
    fetch(CONFIG.MAP_CAPTURES_POST_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ trackId, beforeImage, afterImage }),
    })
      .then((res) => {
        if (!res.ok) console.warn(`[CAPTURE] 업로드 실패 (HTTP ${res.status})`);
      })
      .catch((err) => {
        console.warn("[CAPTURE] 업로드 실패(서버 미기동 등) - 영상 표시에는 영향 없음:", err.message);
      });
  }

  function scheduleBeforeAfterCapture(trackId) {
    if (!trackId) return;
    const grabBefore = () => {
      const beforeImage = captureVideoFrame(videoManager.videoEl);
      setTimeout(() => {
        const afterImage = captureVideoFrame(videoManager.videoEl);
        uploadCaptures(trackId, beforeImage, afterImage);
      }, CONFIG.CAPTURE_AFTER_DELAY_MS);
    };
    const el = videoManager.videoEl;
    if (el.readyState >= 2 && el.videoWidth) {
      grabBefore();
    } else {
      el.addEventListener("loadeddata", grabBefore, { once: true });
    }
  }

  window.__appSelectCamera = (cameraId) => {
    // [수정: "실시간 CCTV 패널 제거"] 예전엔 "추적 차량" 화면(map.js 자체의
    // video-panel)으로 강제 전환시켰다. 그 패널을 없앤 지금은, 아래
    // uticCameraManager.selectById(..., switchVideo:true)가 알아서
    // window.__appGoToJourneyStartCctv를 통해 관제 화면 CCTV 사이드바로
    // 전환 요청을 보낸다(UticCameraManager.selectRecord 참고) - 여기서 따로
    // "추적 차량 화면으로 가라"고 요청할 필요가 없어졌다.

    mapManager.resumeFollow();

    const targetCameraId = eventManager.vehicleCurrentCamera || cameraId;

    eventManager.demoVideoFollowActive = true;

    uticCameraManager.selectById(targetCameraId, { openPopup: true, zoom: true, switchVideo: true, force: true });

    const trackId = vehicleManager.state ? vehicleManager.state.trackId : null;
    scheduleBeforeAfterCapture(trackId);
  };

  // window.__appGoToJourneyStartCctv 정의는 이 파일 최상단(CONFIG 바로 다음)으로
  // 옮겼다 - 아래 "[이동됨]" 주석 참고.

  const uticCamerasLoaded = uticCameraManager.loadData("data/utic-cameras-seoul.json");
  const videoSourcesLoaded = videoSourceRegistry
    .loadData("data/utic-video-sources.json")
    .then((list) => console.log(`[UTIC VIDEO SOURCE] 등록된 영상 공급원 ${list.length}건`))
    .catch((err) => {
      console.warn("UTIC 영상 공급원 데이터 로드 실패 (영상 없이 계속 진행):", err);
      return [];
    });

  Promise.all([uticCamerasLoaded, videoSourcesLoaded])
    .then(([records]) => {
      uticCameraManager.render(records);
      console.log(`[UTIC CCTV] 서울 실시간 CCTV ${records.length}건 표시`);

      eventManager.updateStats();

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

    window.resetDemoTrajectory = () => eventManager.resetDemoSession();
  })
    .catch((err) => console.error("UTIC CCTV 초기화 실패:", err));

  window.mapManager = mapManager;
  window.uticCameraManager = uticCameraManager;
  window.videoSourceRegistry = videoSourceRegistry;
  window.videoManager = videoManager;
  window.vehicleManager = vehicleManager;
  window.eventManager = eventManager;
  window.routeManager = routeManager;
  window.videoModalManager = videoModalManager;

  const realVehicleMarker = new RealVehicleMarker(mapManager);

  console.log(
    "[REAL JOURNEY] RealVehicleMarker 생성 완료",
    realVehicleMarker
  );

  // [수정: "알림 팝업 구현"] 오른쪽 이벤트 리스트 카드(EventManager.
  // upsertRealJourneyEvent())는 계속 유지하되, 예전에 꺼뒀던 화면 우상단 고정
  // 알림 카드(RealJourneyAlertManager)도 다시 켠다 - 이제는 번호판까지 표시
  // 한다. 여정이 새로 시작될 때 show(), 종료될 때 hide()를 호출한다
  // (RealVehicleJourneyListener 콜백 참고).
  const realJourneyAlertManager = new RealJourneyAlertManager(mapManager);

  // [신규] 이벤트 리스트에서 Real Journey 카드를 클릭했을 때: 차량의 "지금" 위치로
  // 지도를 이동하고, 그 차량 마커의 팝업을 연다. realVehicleMarker.marker가
  // 아직 없으면(여정이 이미 끝나 마커가 제거된 경우 등) 아무것도 하지 않는다.
  eventManager.onRealJourneyCardClick = () => {
    if (!realVehicleMarker.marker) return;
    const { lat, lng } = realVehicleMarker.marker.getLatLng();
    mapManager.focus(lat, lng);
    realVehicleMarker.marker.openPopup();
  };

  // [신규] Real Journey 차량 마커에 상세 팝업을 동기화한다. RealVehicleMarker의
  // marker 인스턴스는 여정이 진행되는 동안 하나만 재사용되므로(setPosition()이
  // 처음에만 새로 만들고 이후엔 setLatLng만 호출), 팝업을 한 번 bindPopup해두면
  // Leaflet이 마커 이동을 따라 팝업도 자동으로 옮겨주고, 마커 클릭 시 자동으로
  // 열리며, X 버튼은 Leaflet 기본 동작으로 팝업만 닫는다 - 여기서 새로 구현한
  // 것은 하나도 없다.
  function syncRealJourneyPopup(payload) {
    if (!realVehicleMarker.marker) return; // 아직 마커가 만들어지기 전(다음 payload 때 다시 시도됨)
    const html = buildRealJourneyPopupHtml(payload);
    if (realVehicleMarker.marker.getPopup()) {
      realVehicleMarker.marker.setPopupContent(html);
    } else {
      realVehicleMarker.marker.bindPopup(html, { closeButton: true });
    }
  }

  // [신규: "CCTV 자동 전환이 안 됨"] 직전 payload의 currentCamId를 기억해뒀다가,
  // 실제로 카메라가 바뀐 시점에만 자동 전환을 트리거하기 위한 값이다.
  let realJourneyPrevCamId = null;

  // [수정: "동교동삼거리는 카메라 경계가 아니라 지리적으로 신촌↔합정역
  // 구간 도로 중간에 있다"] camId 쌍(A→B)으로 사각지대를 판정하던 방식은
  // 폐기했다 - 실제 OSRM 도로 경로를 그려보니 동교동삼거리는 "신촌→합정역"
  // 구간의 도로 경로 *중간*에 있었지, 카메라 전환 경계(신촌→합정역 자체,
  // 또는 합정역→양화대교북단)와 일치하지 않았다. 그래서 이제는 애니메이션
  // 중인 도로 좌표들이 동교동삼거리 좌표에 실제로 가까워지는 지점을 찾아서
  // 그 지점에서 끊는다 - 어느 leg(카메라 구간) 안에서 발생하든 상관없다.
  //
  // 좌표는 정확한 측량값이 아니라 지도로 눈대중한 근사치다 - 실제 재생해보고
  // 끊기는 지점이 원하는 곳과 다르면 lat/lng나 radiusMeters를 조정하면 된다.
  const REAL_JOURNEY_GAP_WAYPOINT = {
    lat: 37.5570,
    lng: 126.9260,
    radiusMeters: 250,
  };
  // [신규: "동교동삼거리에서 사라질 때 CCTV 마커 표시를 지나고 사라지게"]
  // 위 REAL_JOURNEY_GAP_WAYPOINT는 지도로 눈대중한 근사 좌표다. 실제 지도에
  // 그려진 동교동삼거리 CCTV 아이콘(utic-cameras-seoul.json 기준)과 정확히
  // 맞추기 위해, 아래 camId로 uticCameraManager에서 진짜 좌표를 조회해서 쓴다
  // (조회 실패 시 위 근사 좌표로 폴백 - resolveGapWaypoint() 참고).
  const REAL_JOURNEY_GAP_WAYPOINT_CAM_ID = "L010078"; // 동교동삼거리 (실제 UTIC camId)
  let _resolvedGapWaypoint = null;
  function resolveGapWaypoint() {
    if (_resolvedGapWaypoint) return _resolvedGapWaypoint;
    const record = uticCameraManager
      ? uticCameraManager.getRecordById(REAL_JOURNEY_GAP_WAYPOINT_CAM_ID)
      : null;
    const lat = record && Number.isFinite(Number(record.lat))
      ? Number(record.lat)
      : REAL_JOURNEY_GAP_WAYPOINT.lat;
    const lng = record && Number.isFinite(Number(record.lng))
      ? Number(record.lng)
      : REAL_JOURNEY_GAP_WAYPOINT.lng;
    // uticCameraManager 데이터가 아직 로딩 전이면 record가 없을 수 있으니,
    // 그 경우엔 캐시하지 않고 다음 호출 때 다시 시도한다.
    if (record) _resolvedGapWaypoint = { lat, lng };
    return { lat, lng };
  }
  // 마커가 아이콘 좌표에 가장 가까워진(closest-approach) 지점을 지나
  // 이 정도(m) 더 실제로 이동한 뒤에야 "지나쳤다"고 보고 숨긴다.
  const REAL_JOURNEY_GAP_PASS_THROUGH_METERS = 25;
  // 사각지대를 빠져나와 다시 나타날 위치 - CAMERA_LOCATIONS의 L010481(양화대교북단)
  // 값과 동일하게 맞춰뒀다(파이썬 test_suspicious_driving.py 쪽 값과 반드시
  // 같이 맞춰야 한다 - 한쪽만 바꾸면 지도 위 위치가 어긋난다).
  // [수정: "재등장 위치가 CCTV 아이콘이랑 안 맞음"] 이 lat/lng는 지도로 눈대중한
  // 근사치라 실제 UTIC CCTV 마커(utic-cameras-seoul.json 기준)의 정확한 좌표와
  // 살짝 어긋났다. 재등장 시점엔 uticCameraManager.getRecordById()로 실제 마커
  // 좌표를 가져와서 쓰고(REAL_JOURNEY_GAP_REVEAL_CAM_ID), 이 객체는 그 조회가
  // 실패했을 때(데이터 미로딩 등)의 폴백으로만 남겨둔다.
  //
  // [긴급 수정: "차량 마커가 안 나타남" 버그] 여기 쓰던 "L010481"은 이
  // 데모(test_suspicious_driving.py의 CAMERA_LOCATIONS)가 독자적으로 붙인
  // 데모용 카메라 ID였는데, 실제 utic-cameras-seoul.json 데이터셋에는 이미
  // 같은 ID로 완전히 다른 진짜 카메라("한강대교남단", 위도 37.51...)가
  // 등록돼 있었다 - ID가 우연히 충돌한 것. 그래서 getRecordById("L010481")가
  // 엉뚱하게 한강대교남단 좌표를 반환했고, 마커가 그쪽으로 순간이동한 뒤 계속
  // 그 방향으로 애니메이션하느라 원래 보던 화면(양화대교북단 부근)에는
  // 나타나지 않았다. 데이터셋을 직접 뒤져서 실제 "양화대교북단"의 진짜
  // camId를 찾았다 - L010194(위도 37.54696, 경도 126.90816). 이 값은
  // test_suspicious_driving.py의 데모 camId(L010481)와는 별개이니 헷갈리지
  // 말 것 - 순수하게 "재등장 지점을 실제 어느 UTIC 마커와 맞출지"만 정하는
  // 용도다.
  // [수정: "우리 데모의 끝 지점은 양화대교북단이 아니라 합정역"] 재등장 지점을
  // 실제 UTIC "합정역" 카메라(L010327, 위도 37.54895, 경도 126.91345)로 바꾼다.
  const REAL_JOURNEY_GAP_REVEAL_CAM_ID = "L010327"; // 합정역 (실제 UTIC camId)
  const REAL_JOURNEY_GAP_REVEAL = { lat: 37.54895, lng: 126.91345, label: "합정역" };
  // [수정: "도로 위에 그려지게"] 예전엔 방위각+거리로 만든 지그재그(가짜
  // 좌표)를 그냥 이어 붙여서 건물을 가로질러 그려지는 문제가 있었다. 이제는
  // 이 방위각+거리는 "대략 이쪽 방향으로 더 가라"는 OSRM 목적지 힌트로만
  // 쓰고, 실제 애니메이션 경로는 routeManager.getRoadSegment()가 돌려주는
  // 진짜 도로 좌표를 쓴다(OSRM 실패 시엔 getRoadSegment 자체가 직선으로
  // 폴백한다). meters는 재등장 지점에서 목적지 힌트까지의 대략 거리.
  const REAL_JOURNEY_GAP_REVEAL_EXTEND_METERS = 250;
  const REAL_JOURNEY_GAP_HIDE_MS = 5000;
  let realJourneyGapTimer = null;
  // 재등장 시 도로 경로(OSRM)를 비동기로 가져오는 동안, 그 사이 다음
  // 사각지대에 이미 들어가거나 여정이 끝나버려서 응답이 도착했을 때는
  // 재생하면 안 된다 - 매 재등장마다 값을 올려서, 응답이 왔을 때 여전히
  // "같은 재등장"인지 확인하는 용도.
  let realJourneyGapToken = 0;
  // 사각지대 진입 후 REAL_JOURNEY_GAP_HIDE_MS가 지날 때까지는 true - 그 사이
  // 도착하는 payload(예: 합정역→양화대교북단 이동 감지)는 지도에 반영하지
  // 않고 무시한다(타이머가 끝나면 어차피 REAL_JOURNEY_GAP_REVEAL 위치로
  // 점프하므로, 그 중간에 들어온 좌표를 따로 그릴 필요가 없다).
  let realJourneySuppressed = false;

  // [수정: "동교동삼거리에서 사라질 때 CCTV 마커 표시를 지나고 사라지게"]
  // 예전엔 동교동삼거리 좌표 반경(radiusMeters) 안에 처음 들어오는 순간
  // 바로 숨겼는데, 그러면 아이콘에 도달하기도 전에(또는 스쳐 지나가자마자)
  // 사라지는 것처럼 보일 수 있었다. 이제는 (1) 전체 누적 좌표(points) 중
  // 아이콘과 가장 가까워지는 지점(closest-approach)을 찾고, (2) 그 지점을
  // 실제로 지나쳐서(경로를 따라 REAL_JOURNEY_GAP_PASS_THROUGH_METERS 이상
  // 더 이동한) 뒤에야 그 지점을 잘라내는 인덱스를 반환한다. 아직 가장
  // 가까운 지점이 배열의 마지막 점이거나(더 지나친 데이터가 아직 없음),
  // 지나친 거리가 충분치 않으면 -1을 반환해 다음 payload를 기다린다.
  function findGapWaypointIndex(points) {
    const waypoint = resolveGapWaypoint();
    const waypointLatLng = [waypoint.lat, waypoint.lng];

    let closestIdx = -1;
    let closestDist = Infinity;
    for (let i = 0; i < points.length; i++) {
      const d = haversineMeters(points[i], waypointLatLng);
      if (d < closestDist) {
        closestDist = d;
        closestIdx = i;
      }
    }

    if (closestIdx === -1 || closestDist > REAL_JOURNEY_GAP_WAYPOINT.radiusMeters) {
      return -1;
    }
    if (closestIdx >= points.length - 1) {
      // 아직 아이콘을 지나쳤다고 볼 만한 다음 좌표가 없다 - 다음 payload를
      // 기다린다.
      return -1;
    }

    let traveled = 0;
    for (let i = closestIdx; i < points.length - 1; i++) {
      traveled += haversineMeters(points[i], points[i + 1]);
      if (traveled >= REAL_JOURNEY_GAP_PASS_THROUGH_METERS) {
        return i + 1;
      }
    }
    // 아직 충분히 지나치지 않았다 - 다음 payload를 기다린다.
    return -1;
  }

  function pointsEqual(p1, p2) {
    return p1 && p2 && p1[0] === p2[0] && p1[1] === p2[1];
  }

  function extractNewJourneySegment(prevPoints, newPoints) {
    let i = 0;
    while (i < prevPoints.length && i < newPoints.length && pointsEqual(prevPoints[i], newPoints[i])) {
      i += 1;
    }
    if (i === 0) return newPoints;
    return newPoints.slice(i - 1);
  }

  const realJourneyListener = new RealVehicleJourneyListener(
    CONFIG.REAL_JOURNEY_STOMP_URL,
    (payload) => {

      console.log(
        "[REAL JOURNEY] PAYLOAD 처리 시작:",
        payload
      );

      if (!payload.active) {

        console.log(
          "[REAL JOURNEY] 여정 종료"
        );

        realVehicleMarker.remove();
        routeManager.clearRealJourney();
        realJourneyPrevCamId = null;
        if (realJourneyGapTimer) {
          clearTimeout(realJourneyGapTimer);
          realJourneyGapTimer = null;
        }
        realJourneyGapToken += 1; // 대기 중인 OSRM 재등장 응답을 무효화
        // 이벤트 리스트 카드 정리 + 우상단 고정 알림 카드도 함께 닫는다.
        eventManager.resolveRealJourneyEvent();
        realJourneyAlertManager.hide();

        return;
      }

      // [수정] 화면 중앙에 큰 Alert Card를 띄우는 대신, 오른쪽 이벤트 리스트에
      // 카드를 추가(또는 이미 있으면 갱신)한다 - EventManager 내부에서 이미
      // "활성 Journey당 카드 1개"를 보장한다.
      eventManager.upsertRealJourneyEvent(payload);

      // [신규: "알림 팝업 구현"] syncRealJourneyPopup()과 같은 방식으로, 매
      // payload마다 우상단 고정 알림 카드 내용을 다시 그린다 - show()는 카드가
      // 이미 떠 있으면 내용만 갱신하고 새로 만들지 않으므로(내부 isNew 분기),
      // 카메라 전환이나(처음엔 None이었다가 나중에 OCR로 확정되는) 번호판 갱신도
      // 자연스럽게 반영된다.
      realJourneyAlertManager.show({
        camName: payload.currentCamName,
        camId: payload.currentCamId,
        plate: payload.plate,
        lat: payload.currentLat,
        lng: payload.currentLng,
        reason: payload.reason,
      });

      const points = (payload.points || []).map(
        (p) => [p.lat, p.lng]
      );

      console.log(
        "[REAL JOURNEY] Polyline 좌표:",
        points
      );

      // [수정: 사용자 요청 - "이상감지 차량이 지도 위에서 실시간으로 움직이면서
      // 폴리라인이 실시간으로 그려져야해"]
      //
      // 이전 단계에서는 정확도를 위해 payload가 올 때마다 즉시 스냅 + 전체
      // 재그리기만 했다(애니메이션 없음) - 도로 위에 정확하게는 그려졌지만
      // 차량이 "순간이동"처럼 보였다.
      //
      // 지금은 realVehicleMarker.animateAlong()으로 마커를 부드럽게 이동시키고,
      // 매 애니메이션 프레임마다 onFrame 콜백에서 routeManager.setRealJourneyPoints()
      // 로 "지나온 좌표 + 지금 보간 중인 좌표"를 항상 전체 다시 그린다. 즉:
      //   - 폴리라인은 절대 append-only로 이어붙이지 않고 매 프레임 authoritative
      //     좌표 기준으로 통째로 다시 그리므로, 오래된 직선이 안 지워지고 남는
      //     문제가 재발하지 않는다(이전 단계에서 고친 버그 그대로 유지).
      //   - 애니메이션은 큐에 쌓이지 않고 새 payload가 오면 즉시 취소 후
      //     현재 위치에서 이어서 재시작하므로, 파이썬이 멈추면 화면도 그 다음
      //     프레임에 바로 멈춘다(밀린 애니메이션이 나중에 재생되는 문제 없음).
      const label = payload.currentCamName || payload.currentCamId;

      if (realJourneySuppressed) {
        // 이미 사각지대에 들어가서 REAL_JOURNEY_GAP_HIDE_MS 타이머가 도는
        // 중이다 - 그 사이 도착하는 payload(예: 합정역→양화대교북단 이동
        // 감지)는 지도에 반영하지 않는다. 타이머가 끝나면 REAL_JOURNEY_GAP_REVEAL
        // 위치로 점프하므로 중간 좌표를 그릴 필요가 없다.
        console.log(
          "[REAL JOURNEY] 🕳️ 사각지대 대기 중 - payload 무시:",
          payload.currentCamId
        );
      } else {
        // [수정: "아이콘을 지나고 사라지게"] 이제 findGapWaypointIndex()는
        // newSegment(이번에 새로 추가된 조각)가 아니라 points(여정 시작부터
        // 지금까지의 전체 누적 좌표)를 받아서, 그 안에서 동교동삼거리 아이콘에
        // 가장 가까워지는 지점을 찾고, 거기서 실제로 더 지나친 지점의 "전역"
        // 인덱스를 바로 돌려준다 - newSegment 기준 로컬 인덱스를 points 기준
        // 전역 인덱스로 다시 변환할 필요가 없다.
        const gapIdx = findGapWaypointIndex(points);

        if (gapIdx === -1) {
          // 사각지대 없음 - animateAlong()으로 마커와 폴리라인을 함께 실시간
          // 으로 채워나간다(마커가 움직이는 매 프레임마다 선도 같이 자람).
          // [main에서 이식] 큐가 없으므로 새 payload가 오면 이전 애니메이션은
          // 즉시 취소되고 마커의 현재 위치에서 이어서 재시작된다 - 밀려서
          // 몰아 재생되는 문제가 구조적으로 생기지 않는다.
          //
          // [수정: "앞쪽 폴리라인이 안 그려짐" 버그] newSegment(이번에 새로
          // 추가된 조각만)가 아니라 points(여정 시작부터 지금까지의 전체
          // 누적 좌표)를 통째로 넘긴다. setCurrentRealJourneySegment()는 매
          // 프레임 현재 선분을 "통째로 다시 그리는" 방식이라, newSegment(매번
          // 새로 생기는 작은 조각)만 넘기면 payload가 새로 올 때마다 그
          // 작은 조각으로 선분 전체가 덮어써져서 이전 payload들이 그려놓은
          // 앞부분이 지워졌다 - 오늘 발견된 버그의 원인. animateAlong()은
          // 어차피 현재 마커 위치에서 가장 가까운 지점을 스스로 찾아 거기서
          // 부터 이어서 애니메이션하므로, 전체 좌표를 넘겨도 처음부터 다시
          // 움직이지 않는다.
          realVehicleMarker.animateAlong(points, label, (framePoints) => {
            routeManager.setCurrentRealJourneySegment(framePoints);
          });
        } else {
          // 사각지대 발견 - 그 지점까지만 애니메이션하고, 거기서 멈춘 뒤
          // 마커를 감춘다. REAL_JOURNEY_GAP_HIDE_MS 후 REAL_JOURNEY_GAP_REVEAL
          // (양화대교북단)로 애니메이션 없이 바로 이동시킨다.
          //
          // gapIdx는 이제 points 배열 기준 전역 인덱스이므로 바로 slice해서
          // "여정 시작부터 사각지대(아이콘을 지나친 지점)까지의 전체 누적
          // 좌표"를 얻는다.
          const beforeGap = points.slice(0, gapIdx + 1);

          // [유지: 레이스 컨디션 버그 수정] gap을 발견한 이 시점에 즉시
          // suppress 플래그를 켜둔다 - beforeGap 애니메이션이 재생되는 몇 초
          // 사이 도착하는 다음 payload가 realJourneySuppressed를 아직 false로
          // 보고 자기 구간을 별도로 재생해버리는 걸 막는다. [main 이식 이후]
          // animateAlong()은 애초에 큐가 없어서(clearQueue() 호출 불필요) 이
          // 시점 이후 들어오는 모든 payload는 아래 realJourneySuppressed
          // 분기에서 그냥 무시되고, 새 애니메이션이 걸릴 일 자체가 없다.
          realJourneySuppressed = true;

          realVehicleMarker.animateAlong(beforeGap, label, (framePoints) => {
            routeManager.setCurrentRealJourneySegment(framePoints);
          }, () => {
            console.log(
              `[REAL JOURNEY] 🕳️ 동교동삼거리 부근 도달 - 마커 ${REAL_JOURNEY_GAP_HIDE_MS}ms 숨김`
            );
            routeManager.startNewRealJourneySegment();
            realVehicleMarker.hide();
            const __gapHideStartedAt = Date.now();
            console.log(
              `[REAL JOURNEY] ⏱️ 숨김 시작 (${new Date(__gapHideStartedAt).toLocaleTimeString()}) - ${REAL_JOURNEY_GAP_HIDE_MS}ms 후 재등장 예정`
            );

            if (realJourneyGapTimer) clearTimeout(realJourneyGapTimer);
            realJourneyGapTimer = setTimeout(() => {
              const __elapsed = Date.now() - __gapHideStartedAt;
              console.log(
                `[REAL JOURNEY] ⏱️ 재등장 (실제 경과 ${__elapsed}ms, 목표 ${REAL_JOURNEY_GAP_HIDE_MS}ms)`
              );

              // [수정: "정확히 CCTV 마커 위치에서 나오지 않음"] 하드코딩된
              // 근사 좌표 대신, 지도에 실제로 그려진 CCTV 아이콘과 동일한
              // 소스(uticCameraManager)에서 좌표를 가져온다 - 데이터 로딩
              // 전이거나 해당 camId가 없으면 근사치로 폴백한다.
              const revealRecord = uticCameraManager
                ? uticCameraManager.getRecordById(REAL_JOURNEY_GAP_REVEAL_CAM_ID)
                : null;
              const revealLat = revealRecord && Number.isFinite(Number(revealRecord.lat))
                ? Number(revealRecord.lat)
                : REAL_JOURNEY_GAP_REVEAL.lat;
              const revealLng = revealRecord && Number.isFinite(Number(revealRecord.lng))
                ? Number(revealRecord.lng)
                : REAL_JOURNEY_GAP_REVEAL.lng;
              const revealLabel = (revealRecord && revealRecord.name) || REAL_JOURNEY_GAP_REVEAL.label;

              // 짠 하고 다시 나타난다 - 사각지대 진입 때와 마찬가지로 애니메이션
              // 없이 즉시 위치를 맞춘다(setPosition이 opacity도 1로 되돌린다).
              realVehicleMarker.setPosition(revealLat, revealLng, revealLabel);
              routeManager.appendRealJourneyPoint([revealLat, revealLng]);
              const myGapToken = ++realJourneyGapToken;

              // [수정: "도로 위에 그려지게"] 재등장 지점에 점 하나만 찍힌 채로
              // 멈춰있지 않도록, 사각지대에 들어가기 직전 진행 방향(bearing)
              // 으로 대략적인 목적지 힌트만 잡고, 실제 애니메이션 경로는
              // routeManager.getRoadSegment()로 진짜 도로 좌표를 받아와서
              // 쓴다 - 예전처럼 방위각+거리로 만든 가짜 지그재그가 건물을
              // 가로질러 그려지는 문제가 없어진다. beforeGap이 점 2개
              // 미만이면(이론상 거의 없음) 방위각을 계산할 수 없으니 건너뛴다.
              if (beforeGap.length >= 2) {
                const bearing = computeBearingDeg(
                  beforeGap[beforeGap.length - 2],
                  beforeGap[beforeGap.length - 1]
                );
                const targetHint = destinationPoint(
                  [revealLat, revealLng],
                  bearing,
                  REAL_JOURNEY_GAP_REVEAL_EXTEND_METERS
                );
                routeManager
                  .getRoadSegment([revealLat, revealLng], targetHint)
                  .then((roadPath) => {
                    // 그 사이 다음 사각지대에 이미 들어갔거나 여정이 끝나서
                    // 더 이상 "같은 재등장"이 아니면 재생하지 않는다.
                    if (myGapToken !== realJourneyGapToken) return;
                    realVehicleMarker.animateAlong(
                      roadPath,
                      revealLabel,
                      (framePoints) => {
                        routeManager.setCurrentRealJourneySegment(framePoints);
                      }
                    );
                  })
                  .catch((err) => {
                    console.warn("[REAL JOURNEY] 재등장 후 도로 경로 가져오기 실패:", err);
                  });
              }

              realJourneySuppressed = false;
              realJourneyGapTimer = null;
            }, REAL_JOURNEY_GAP_HIDE_MS);
          });
        }
      }

      // [신규] 마커가 존재하면(대부분의 경우 이미 존재) 상세 팝업 내용을 최신
      // CCTV 정보로 동기화한다 - 팝업이 열려 있어도, 닫혀 있어도 안전하다.
      syncRealJourneyPopup(payload);

      // [신규: "오른쪽 CCTV에 자동으로 그 CCTV가 보여야 하는데 안 보임"]
      // 예전엔 사용자가 팝업의 "CCTV 바로가기" 버튼을 직접 눌러야만 오른쪽
      // CCTV 패널이 전환됐다(__appGoToJourneyStartCctv는 버튼 onclick에서만
      // 호출됐음). 차량이 새 카메라 구간으로 넘어갈 때(currentCamId 변경)
      // 버튼 클릭 없이도 자동으로 같은 함수를 호출해 오른쪽 패널을 전환한다.
      // 좌표만 갱신되고 카메라는 그대로인 payload가 초당 여러 번 올 수 있어서,
      // camId가 실제로 바뀐 경우에만(=여정 시작 포함) 보낸다 - 그래야 사용자가
      // 수동으로 다른 CCTV를 보고 있을 때 매 프레임 강제로 뺏어오지 않는다.
      if (
        payload.currentCamId &&
        payload.currentCamId !== realJourneyPrevCamId
      ) {
        realJourneyPrevCamId = payload.currentCamId;
        window.__appGoToJourneyStartCctv &&
          window.__appGoToJourneyStartCctv(payload.currentCamId);
      }
    }
  );

  realJourneyListener.start();

  window.realVehicleMarker = realVehicleMarker;
  window.realJourneyListener = realJourneyListener;
  console.log(
  "[REAL JOURNEY] GLOBAL CHECK:",
  window === top,
  window.location.href,
  window.realVehicleMarker
 );
});