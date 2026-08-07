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
