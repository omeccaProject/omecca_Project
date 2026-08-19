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

// 관심 대상(TargetsPanel) 차량 등록 시 "차종" 입력을 돕는 추천 목록(datalist) - 자유 입력도
// 가능하지만, 실무에서 자주 쓰는 모델을 브랜드/트림까지 구체적으로 미리 넣어둬서 관제요원이
// 빠르게 고를 수 있게 한다. 목록에 없는 차종도 직접 타이핑해서 등록 가능.
export const VEHICLE_MODEL_SUGGESTIONS = [
  '현대 아반떼AD',
  '현대 아반떼CN7',
  '현대 쏘나타DN8',
  '현대 싼타페',
  '현대 그랜저IG',
  '현대 그랜저GN7',
  '기아 K5',
  '기아 K8',
  '기아 스포티지',
  '기아 쏘렌토',
  '기아 카니발',
  '제네시스 G80',
  '쌍용 렉스턴',
  '쉐보레 트레일블레이저',
]

// 관심 대상 차량 등록 시 "차량 색상" 선택지. 자주 쓰는 색상 위주로 고정 목록을 두되,
// "기타"를 고르면 직접 입력할 수 있게 TargetsPanel에서 처리한다.
export const VEHICLE_COLOR_OPTIONS = ['흰색', '검정', '은색', '회색', '파랑', '빨강', '노랑', '기타']
