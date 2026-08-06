import Badge from './Badge'

function fmtTime(iso) {
  if (!iso) return '-'
  return iso.replace('T', ' ').split('.')[0]
}

export default function EventList({ events, focusedId, onSelect }) {
  if (events.length === 0) {
    return (
      <section className="panel">
        <h2>이벤트 리스트</h2>
        <div className="viewer-empty">표시할 이벤트가 없습니다.</div>
      </section>
    )
  }

  return (
    <section className="panel">
      <h2>이벤트 리스트</h2>
      <div className="event-list">
        {events.map((ev) => (
          <div
            key={ev.id}
            className={`event-row ${ev.id === focusedId ? 'active' : ''}`}
            onClick={() => onSelect(ev)}
          >
            <div className="event-row-top">
              <Badge eventType={ev.eventType} />
              <span className="time">{fmtTime(ev.occurredAt)}</span>
            </div>
            <div className="cam">{ev.camId}{ev.trackId ? ` · ${ev.trackId}` : ''}</div>
            <div className="conf">
              신뢰도 {ev.confidence != null ? `${(ev.confidence * 100).toFixed(0)}%` : '-'}
              {ev.isRegisteredTarget ? ' · 관심대상' : ''}
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}
