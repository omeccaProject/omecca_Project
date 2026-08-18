// 이벤트 스키마 규격서(shared/schemas/이벤트_스키마_규격서.md) 기준 7종 고정값.
// 새 이벤트 유형이 추가되면 여기 두 곳(라벨/색상)만 추가하면 화면 전체에 반영됨.
export const EVENT_LABEL = {
  WANTED_PERSON: '수배자',
  WEAPON: '흉기',
  UNREGISTERED_VEHICLE: '미등록차량',
  DEBRIS: '낙하물',
  DUI_PATTERN: '음주운전의심',
  SIGNAL_VIOLATION: '신호위반',
  UTURN_VIOLATION: '불법유턴',
}

export const EVENT_COLOR = {
  WANTED_PERSON: '#e5484d',
  WEAPON: '#f76b15',
  UNREGISTERED_VEHICLE: '#8b5cf6',
  DEBRIS: '#eab308',
  DUI_PATTERN: '#ec4899',
  SIGNAL_VIOLATION: '#4d8dff',
  UTURN_VIOLATION: '#14b8a6',
}

export const EVENT_TYPES = Object.keys(EVENT_LABEL)

// 위험도 등급 — 대시보드 상단 자동 정렬 기준.
// 3=높음(즉각 대응 필요), 2=중간(현장 확인 필요), 1=낮음(참고/기록용)
// 새 이벤트 유형이 생기면 여기에도 등급을 추가해야 함.
export const EVENT_RISK = {
  WANTED_PERSON: 3,
  WEAPON: 3,
  DUI_PATTERN: 3,
  UNREGISTERED_VEHICLE: 2,
  SIGNAL_VIOLATION: 2,
  UTURN_VIOLATION: 2,
  DEBRIS: 1,
}

export const RISK_LABEL = { 3: '높음', 2: '중간', 1: '낮음' }

// 이벤트 리스트 패널의 위험도별 아코디언 섹션 제목
export const TIER_LABEL = { 3: '고위험 이벤트', 2: '중위험 이벤트', 1: '정보 이벤트' }
export const RISK_TIERS = [3, 2, 1]

// 이 이벤트 유형들은 "차량"과 직접 관련된 이벤트라서(음주운전 의심/미등록차량/신호위반/불법유턴),
// 실시간으로 들어오면 화면 중앙에 알림 팝업을 띄우고(App.jsx), 클릭하면 대시보드가 "추적 차량"
// 뷰로 넘어가서 GIS 지도 위에 그 차량을 바로 보여준다(MainDashboard.jsx). WANTED_PERSON/WEAPON/
// DEBRIS는 차량이 아니므로 대상에서 뺀다. App.jsx/MainDashboard.jsx 둘 다 이 값을 그대로 써야
// 하므로 여기 한 곳에만 정의해둔다.
export const VEHICLE_TRACK_EVENT_TYPES = new Set([
  'DUI_PATTERN',
  'UNREGISTERED_VEHICLE',
  'SIGNAL_VIOLATION',
  'UTURN_VIOLATION',
])