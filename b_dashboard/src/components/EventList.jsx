import { useState } from 'react'
import Badge from './Badge'
import { EVENT_RISK, RISK_TIERS, TIER_LABEL } from '../constants'
import { generateEventReport } from '../api'
import EventDetailModal from './EventDetailModal'

function fmtTime(iso) {
  if (!iso) return '-'
  return iso.replace('T', ' ').split('.')[0]
}

// MainDashboard.jsx의 이벤트 카드와 같은 규칙(EVT-000123)으로 파일명을 맞춘다.
function fmtRefId(ev) {
  if (!ev) return '-'
  const num = Number(ev.id)
  if (!Number.isNaN(num) && Number.isFinite(num)) return `EVT-${String(num).padStart(6, '0')}`
  return `EVT-${ev.id ?? '-'}`
}

// title/defaultOpenTier: 사이드바 "고위험" 전용 화면(activeView='critical')처럼 특정 등급만
// 강조해서 보여줘야 하는 화면에서도 이 컴포넌트를 그대로 재사용할 수 있게 옵션으로 뺐다.
export default function EventList({ events, focusedId, onSelect, title = '실시간 이벤트 리스트', defaultOpenTier = 3 }) {
  // 기본으로 고위험 섹션만 펼쳐둠. 섹션 헤더 클릭으로 펼치기/접기.
  const [openTier, setOpenTier] = useState(defaultOpenTier)
  // "남은 이벤트"(전체 목록) 화면에서도 대시보드와 동일하게 상세 확인 없이 바로
  // PDF 리포트를 뽑을 수 있게 각 행에 버튼을 둔다 - 클릭한 이벤트의 id만 잠가서
  // 여러 개를 동시에 눌러도 서로 꼬이지 않게 한다.
  const [generatingReportId, setGeneratingReportId] = useState(null)
  // 행을 클릭하면 상세화면(사건 전/후 캡처 이미지 · 위치 · PDF 리포트 버튼)이 뜬다.
  const [detailEvent, setDetailEvent] = useState(null)

  const handleGenerateReport = async (ev) => {
    if (generatingReportId) return
    setGeneratingReportId(ev.id)
    try {
      const blob = await generateEventReport(ev.id)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `report_${fmtRefId(ev)}.pdf`
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
    } catch (err) {
      console.error(err)
      alert(err.message || 'PDF 리포트 생성에 실패했습니다.')
    } finally {
      setGeneratingReportId(null)
    }
  }

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
                        onClick={() => {
                          onSelect(ev)
                          setDetailEvent(ev)
                        }}
                      >
                        <div className="event-row-top">
                          <span className="event-row-top-left">
                            <Badge eventType={ev.eventType} />
                            <span className="time">{fmtTime(ev.occurredAt)}</span>
                          </span>
                          <button
                            type="button"
                            className="control-event-pdf-btn"
                            title="PDF 리포트 생성"
                            disabled={generatingReportId === ev.id}
                            onClick={(e) => {
                              e.stopPropagation()
                              handleGenerateReport(ev)
                            }}
                          >
                            {generatingReportId === ev.id ? '⏳' : '📄'}
                          </button>
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
      <EventDetailModal event={detailEvent} onClose={() => setDetailEvent(null)} />
    </section>
  )
}