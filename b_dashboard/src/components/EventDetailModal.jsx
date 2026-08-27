import { useEffect, useState } from 'react'
import { EVENT_LABEL } from '../constants'
import { generateEventReport, fetchCameras } from '../api'

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

// 차량 DB 대조 결과. d_lpr(LPR 모듈)이 번호판을 읽은 뒤 vehicle 테이블과 맞춰 보고
// meta.vehicleStatus 로 실어 보낸다 — 값은 진작 오고 있었는데 화면에 그리질 않아서
// "미등록인지 등록인지 안 보인다"는 얘기가 나왔다.
const VEHICLE_STATUS_LABEL = {
  registered: '등록 차량',
  unregistered: 'DB 미등록',
  stolen: '도난 신고',
  wanted: '수배 차량',
  fake_plate: '대포차 의심',
  impound: '과태료 체납 영치 대상',
  insurance_expired: '책임보험 만료',
}

// 등록 차량만 평범하게, 나머지는 전부 눈에 띄게. 미등록도 고위험으로 본다
// (수배·도난 차량이 번호판을 갈아 끼우면 DB 에 없는 번호로 나타나기 때문).
const VEHICLE_STATUS_ALERT = new Set([
  'unregistered', 'stolen', 'wanted', 'fake_plate', 'impound', 'insurance_expired',
])

function fmtVehicleStatus(ev) {
  const s = ev.meta?.vehicleStatus
  if (!s) return null
  return { key: s, label: VEHICLE_STATUS_LABEL[s] ?? s, alert: VEHICLE_STATUS_ALERT.has(s) }
}

export default function EventDetailModal({ event, onClose }) {
  const [generating, setGenerating] = useState(false)
  // "카메라 / 위치" 행의 위치는 event.location(lat/lng)이 a_core에서 항상 null로 오기
  // 때문에(위치는 e_tracking 담당, 아직 미연동) 지금까지 계속 "-"로만 떴다. 대신 이미
  // "카메라 관리"에 등록돼 있는 camId ↔ name 매핑을 가져와서, 최소한 그 카메라의 등록된
  // 이름(예: "국립국악원")이라도 보여주도록 한다.
  const [cameraNameById, setCameraNameById] = useState({})

  useEffect(() => {
    fetchCameras()
      .then((list) => {
        const map = {}
        ;(Array.isArray(list) ? list : []).forEach((cam) => {
          if (cam.camId) map[cam.camId] = cam.name
        })
        setCameraNameById(map)
      })
      .catch(() => {}) // 카메라 목록 조회가 실패해도 상세화면 자체는 그대로 봐야 하므로 조용히 무시
  }, [])

  if (!event) return null

  const cameraName = event.camId ? cameraNameById[event.camId] : null

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
            <tr><th>카메라 / 위치</th><td>{event.camId || '-'} · {cameraName || fmtLocationLabel(event)}</td></tr>
            <tr><th>추적 ID</th><td>{event.trackId || '-'}</td></tr>
            <tr><th>차량 번호판</th><td>{fmtPlate(event)}</td></tr>
            {(() => {
              const vs = fmtVehicleStatus(event)
              // 번호판을 못 읽은 이벤트에는 대조 결과 자체가 없다. 그럴 때 '-' 를
              // 띄우면 "조회했는데 아무것도 아님"처럼 보이므로 행을 아예 감춘다.
              if (!vs) return null
              return (
                <tr>
                  <th>차량 조회</th>
                  <td style={vs.alert ? { color: '#d92d20', fontWeight: 600 } : undefined}>
                    {vs.label}
                  </td>
                </tr>
              )
            })()}
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
