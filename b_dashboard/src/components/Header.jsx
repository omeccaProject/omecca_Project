import { EVENT_LABEL, EVENT_TYPES } from '../constants'

export default function Header({
  connected, total, targetCount,
  autoFocus, onAutoFocusChange,
  filterType, onFilterTypeChange,
  filterCam, onFilterCamChange,
  onRefresh,
}) {
  return (
    <header>
      <h1>오메카3 관제 대시보드</h1>
      <div className="status">
        <span className={`dot ${connected ? 'on' : 'off'}`} />
        <span>{connected ? '실시간 연결됨' : '연결 끊김'}</span>
      </div>
      <div className="stat">누적 이벤트 <b>{total}</b></div>
      <div className="stat">관심대상 관련 <b>{targetCount}</b></div>

      <div className="filters">
        <label className="toggle">
          <input type="checkbox" checked={autoFocus} onChange={(e) => onAutoFocusChange(e.target.checked)} />
          신규 이벤트 자동 포커싱
        </label>
        <select value={filterType} onChange={(e) => onFilterTypeChange(e.target.value)}>
          <option value="">전체 이벤트 유형</option>
          {EVENT_TYPES.map((t) => (
            <option key={t} value={t}>{EVENT_LABEL[t]}</option>
          ))}
        </select>
        <input
          placeholder="CCTV ID 필터 (예: CAM-01)"
          value={filterCam}
          onChange={(e) => onFilterCamChange(e.target.value)}
        />
        <button onClick={onRefresh}>새로고침</button>
      </div>
    </header>
  )
}
