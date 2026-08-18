import { useState } from 'react'
import Badge from './Badge'
import { EVENT_RISK, RISK_TIERS, TIER_LABEL } from '../constants'

function fmtTime(iso) {
  if (!iso) return '-'
  return iso.replace('T', ' ').split('.')[0]
}

// title/defaultOpenTier: 사이드바 "고위험" 전용 화면(activeView='critical')처럼 특정 등급만
// 강조해서 보여줘야 하는 화면에서도 이 컴포넌트를 그대로 재사용할 수 있게 옵션으로 뺐다.
export default function EventList({ events, focusedId, onSelect, title = '실시간 이벤트 리스트', defaultOpenTier = 3 }) {
  // 기본으로 고위험 섹션만 펼쳐둠. 섹션 헤더 클릭으로 펼치기/접기.
  const [openTier, setOpenTier] = useState(defaultOpenTier)

  const grouped = RISK_TIERS.map((level) => ({
    level,
    label: TIER_LABEL[level],
    items: events.filter((ev) => (EVENT_RISK[ev.eventType] || 0) === level),
  }))

  return (
    <section className="panel">
      <h2>{title}</h2>
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