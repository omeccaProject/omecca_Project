import { useState } from 'react'
import { EVENT_LABEL } from '../constants'
import { generateEventReport } from '../api'

// 대시보드 이벤트 카드/"남은 이벤트" 행을 클릭했을 때 뜨는 상세화면.
// 사건 전/후 캡처 이미지와 위치 정보를 확인하고, 그 자리에서 "📄 PDF 리포트 생성" 버튼으로
// 실제 백엔드가 만든 증거 PDF를 바로 다운로드할 수 있다 - MainDashboard.jsx/EventList.jsx
// 양쪽 리스트에서 공통으로 재사용한다.

function fmtTime(iso) {
  if (!iso) return '-'
  return iso.replace('T', ' ').split('.')[0]
}

function fmtRefId(ev) {
  if (!ev) return '-'
  const num = Number(ev.id)
  if (!Number.isNaN(num) && Number.isFinite(num)) return `EVT-${String(num).padStart(6, '0')}`
  return `EVT-${ev.id ?? '-'}`
}

function fmtLocation(ev) {
  if (ev.location?.lat == null || ev.location?.lng == null) return '-'
  return `${ev.location.lat.toFixed(5)}, ${ev.location.lng.toFixed(5)}`
}

function fmtPlate(ev) {
  return ev.meta?.plateNumber ?? ev.meta?.licensePlate ?? ev.meta?.plate ?? '-'
}

function fmtLocationLabel(ev) {
  return ev.meta?.locationLabel ?? ev.meta?.location ?? ev.location?.label ?? fmtLocation(ev)
}

export default function EventDetailModal({ event, onClose }) {
  const [generating, setGenerating] = useState(false)

  if (!event) return null

  const handleGenerateReport = async () => {
    if (generating) return
    setGenerating(true)
    try {
      const blob = await generateEventReport(event.id)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `report_${fmtRefId(event)}.pdf`
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
    } catch (err) {
      console.error(err)
      alert(err.message || 'PDF 리포트 생성에 실패했습니다.')
    } finally {
      setGenerating(false)
    }
  }

  return (
    <div className="event-detail-overlay" onClick={onClose}>
      <div className="event-detail-box" onClick={(e) => e.stopPropagation()}>
        <button type="button" className="event-detail-close" onClick={onClose} aria-label="닫기">✕</button>

        <div className="event-detail-eyebrow">REF. {fmtRefId(event)}</div>
        <h2 className="event-detail-title">{EVENT_LABEL[event.eventType] || event.eventType}</h2>

        <table className="event-detail-kv">
          <tbody>
            <tr><th>발생 시각</th><td>{fmtTime(event.occurredAt)}</td></tr>
            <tr><th>카메라 / 위치</th><td>{event.camId || '-'} · {fmtLocationLabel(event)}</td></tr>
            <tr><th>추적 ID</th><td>{event.trackId || '-'}</td></tr>
            <tr><th>차량 번호판</th><td>{fmtPlate(event)}</td></tr>
            <tr><th>탐지 신뢰도</th><td>{event.confidence != null ? `${(event.confidence * 100).toFixed(1)}%` : '-'}</td></tr>
          </tbody>
        </table>

        <div className="event-detail-images">
          <div className="event-detail-image-box">
            <div className="event-detail-image-label">사건 발생 전</div>
            <div className="event-detail-image-frame">
              {event.frameRefBefore
                ? <img src={event.frameRefBefore} alt="사건 발생 전" />
                : <div className="event-detail-image-empty">이미지 없음</div>}
            </div>
          </div>
          <div className="event-detail-image-box">
            <div className="event-detail-image-label">사건 발생 후</div>
            <div className="event-detail-image-frame">
              {event.frameRefAfter
                ? <img src={event.frameRefAfter} alt="사건 발생 후" />
                : <div className="event-detail-image-empty">이미지 없음</div>}
            </div>
          </div>
        </div>

        <button
          type="button"
          className="event-detail-pdf-btn"
          disabled={generating}
          onClick={handleGenerateReport}
        >
          {generating ? '⏳ 생성 중...' : '📄 PDF 리포트 생성'}
        </button>
      </div>
    </div>
  )
}
