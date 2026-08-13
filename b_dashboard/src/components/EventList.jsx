import { useState } from 'react'
import Badge from './Badge'
import { EVENT_RISK, RISK_TIERS, TIER_LABEL } from '../constants'

function fmtTime(iso) {
  if (!iso) return '-'
  return iso.replace('T', ' ').split('.')[0]
}

export default function EventList({ events, focusedId, onSelect }) {
  // 기본으로 고위험 섹션만 펼쳐둠. 섹션 헤더 클릭으로 펼치기/접기.
  const [openTier, setOpenTier] = useState(3)

  const grouped = RISK_TIERS.map((level) => ({
    level,
    label: TIER_LABEL[level],
    items: events.filter((ev) => (EVENT_RISK[ev.eventType] || 0) === level),
  }))

  return (
    <section className="panel">
      <h2>실시간 이벤트 리스트</h2>
      <div className="tier-list">
        {grouped.map((tier) => {
          const isOpen = openTier === tier.level
          return (
            <div key={tier.level} className={`tier tier-${tier.level}`}>
              <button
                type="button"
                className={`tier-head ${isOpen ? 'open' : ''}`}
                onClick={() => setOpenTier(isOpen ? null : tier.level)}
              >
                <span>{tier.label}</span>
                <span className="tier-count">{tier.items.length}</span>
              </button>

              {isOpen && (
                <div className="tier-body">
                  {tier.items.length === 0 ? (
                    <div className="tier-empty">해당하는 이벤트가 없습니다.</div>
                  ) : (
                    tier.items.map((ev) => (
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
                    ))
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </section>
  )
}