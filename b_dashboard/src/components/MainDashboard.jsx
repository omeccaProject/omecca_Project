import { useCallback, useEffect, useRef, useState } from 'react'
import jsPDF from 'jspdf'
import html2canvas from 'html2canvas'
import { EVENT_RISK, EVENT_LABEL, VEHICLE_TRACK_EVENT_TYPES } from '../constants'
import CctvGrid from './CctvGrid'
import EventList from './EventList'
import TargetsPanel from './TargetsPanel'

function fmtTime(iso) {
  if (!iso) return '-'
  return iso.replace('T', ' ').split('.')[0]
}

function fmtLocation(ev) {
  if (ev.location?.lat == null || ev.location?.lng == null) return '-'
  return `${ev.location.lat.toFixed(5)}, ${ev.location.lng.toFixed(5)}`
}

function fmtIsoRaw(iso) {
  if (!iso) return '-'
  return iso.split('.')[0]
}

function fmtGeneratedAt(date) {
  const p = (n) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${p(date.getMonth() + 1)}-${p(date.getDate())} ${p(date.getHours())}:${p(date.getMinutes())}:${p(date.getSeconds())}`
}

function fmtRefId(ev) {
  if (!ev) return '-'
  const num = Number(ev.id)
  if (!Number.isNaN(num) && Number.isFinite(num)) return `EVT-${String(num).padStart(6, '0')}`
  return `EVT-${ev.id ?? '-'}`
}

function fmtPlate(ev) {
  return ev.meta?.plateNumber ?? ev.meta?.licensePlate ?? ev.meta?.plate ?? '-'
}
function fmtLocationLabel(ev) {
  return ev.meta?.locationLabel ?? ev.meta?.location ?? ev.location?.label ?? fmtLocation(ev)
}

function metaLine(ev) {
  const parts = []
  const plate = fmtPlate(ev)
  if (plate !== '-') parts.push(`차량: ${plate}`)
  const loc = fmtLocationLabel(ev)
  if (loc !== '-') parts.push(loc)
  if (ev.confidence != null) parts.push(`신뢰도 ${(ev.confidence * 100).toFixed(0)}%`)
  return parts.length ? parts.join(' · ') : '-'
}

// 대시보드 이벤트(ev)를 GIS 지도(map.js)의 "omecca-track-vehicle-event" 메시지 payload로 변환.
function buildTrackVehiclePayload(ev) {
  const locationLabel = fmtLocationLabel(ev)
  const plate = fmtPlate(ev)
  return {
    camId: ev.camId || null,
    trackId: ev.trackId || null,
    plate: plate !== '-' ? plate : null,
    lat: ev.location?.lat ?? null,
    lng: ev.location?.lng ?? null,
    locationLabel: locationLabel !== '-' ? locationLabel : null,
    type: EVENT_LABEL[ev.eventType] || ev.eventType,
    reason: ev.meta?.trajectoryFeatures ? '차선 지그재그·급가감속 패턴 감지' : (ev.meta?.reason || '-'),
    confidence: ev.confidence != null ? Math.round(ev.confidence * 100) : null,
    time: fmtTime(ev.occurredAt),
  }
}

function IconGrid() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="7" height="7" rx="1.5" />
      <rect x="14" y="3" width="7" height="7" rx="1.5" />
      <rect x="3" y="14" width="7" height="7" rx="1.5" />
      <rect x="14" y="14" width="7" height="7" rx="1.5" />
    </svg>
  )
}
function IconMap() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="9" />
      <circle cx="12" cy="12" r="2.4" />
      <path d="M12 3v3M12 18v3M3 12h3M18 12h3" />
    </svg>
  )
}
function IconCamera() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 8h3l1.5-2h7L17 8h3a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1z" />
      <circle cx="12" cy="13" r="3.2" />
    </svg>
  )
}
function IconClock() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3.2 2" />
    </svg>
  )
}
function IconAlertCircle() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="9" />
      <path d="M12 8v5" />
      <circle cx="12" cy="16" r="0.6" fill="currentColor" stroke="none" />
    </svg>
  )
}
function IconSquare() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <rect x="4" y="4" width="16" height="16" rx="2" />
    </svg>
  )
}

function SidebarRow({ icon, label, count, tone, active, onClick }) {
  const clickable = typeof onClick === 'function'
  return (
    <button
      type="button"
      className={`control-sidebar-row ${active ? 'active' : ''} ${tone ? `tone-${tone}` : ''} ${clickable ? '' : 'static'}`}
      onClick={onClick}
      disabled={!clickable}
    >
      <span className="control-sidebar-row-icon">{icon}</span>
      <span className="control-sidebar-row-label">{label}</span>
      <span className="control-sidebar-row-count">{count}</span>
    </button>
  )
}

// 실시간으로 새 차량 이벤트(음주운전 의심/미등록차량/신호위반/불법유턴)가 들어오면 화면
// 정중앙에 뜨는 알림 팝업. 예전엔 오른쪽 "AI 관제 이벤트" 리스트에서 카드를 직접 찾아
// 클릭해야만 지도에서 그 차량을 볼 수 있었는데, 그러다 보니 대시보드가 아닌 다른 화면을
// 보고 있을 땐 새 차량 이벤트가 온 걸 놓치기 쉬웠다. 이제는 어떤 화면을 보고 있든 이 팝업이
// 바로 뜨고, 클릭 한 번으로 "추적 차량" 뷰 + 지도 포커스까지 한 번에 이동한다.
function VehicleAlertPopup({ event, onFocus, onDismiss }) {
  if (!event) return null

  const risk = EVENT_RISK[event.eventType] || 1
  const plate = fmtPlate(event)
  const loc = fmtLocationLabel(event)

  return (
    <div className="vehicle-alert-overlay" onClick={onDismiss}>
      <div className={`vehicle-alert-box tier-${risk}`} onClick={(e) => e.stopPropagation()}>
        <button type="button" className="vehicle-alert-close" onClick={onDismiss} aria-label="닫기">✕</button>
        <div className="vehicle-alert-eyebrow">TRACK {event.trackId || fmtRefId(event)}</div>
        <div className="vehicle-alert-title">🚗 새 차량 이벤트 감지</div>
        <table className="vehicle-alert-kv">
          <tbody>
            <tr><th>유형</th><td>{EVENT_LABEL[event.eventType] || event.eventType}</td></tr>
            <tr><th>번호판</th><td>{plate}</td></tr>
            <tr><th>카메라 / 위치</th><td>{event.camId || '-'} / {loc}</td></tr>
            <tr><th>감지 시각</th><td>{fmtTime(event.occurredAt)}</td></tr>
          </tbody>
        </table>
        <button type="button" className="vehicle-alert-focus-btn" onClick={onFocus}>
          🗺️ 지도에서 실시간으로 보기 →
        </button>
      </div>
    </div>
  )
}

export default function MainDashboard({
  events,
  focusedEvent,
  onSelectCam,
  total,
  vehicleTargetCount,
  personTargetCount,
  darkMode,
  activeView,
  onChangeView,
  onTargetsChanged,
  vehicleAlert,
  onDismissVehicleAlert,
}) {
  const [exporting, setExporting] = useState(false)
  const [pdfTarget, setPdfTarget] = useState(null)
  const reportRef = useRef(null)
  const mapIframeRef = useRef(null)
  const mapReadyRef = useRef(false)
  // onMessage 핸들러는 darkMode가 바뀔 때만 재구독되므로, activeView를 직접 클로저로
  // 캡처하면 그 사이 activeView가 바뀌어도 낡은 값을 보게 된다. ref로 최신값을 따로 추적.
  const activeViewRef = useRef(activeView)
  activeViewRef.current = activeView
  // 페이지를 막 열자마자(지도 iframe이 아직 "omecca-map-ready"를 보내기 전에) 이벤트
  // 카드를 클릭한 경우를 위한 큐 - 가장 최근 요청 하나만 기억해뒀다가 준비되는 즉시 보낸다.
  const pendingTrackEventRef = useRef(null)

  // GIS 지도(iframe)에 postMessage 하나 보내는 공용 헬퍼. 지도가 아직
  // "omecca-map-ready"를 보내기 전이면 조용히 무시한다(핸드셰이크 전에 보내봐야 유실됨).
  const postToMap = useCallback((payload) => {
    if (!mapReadyRef.current) return
    mapIframeRef.current?.contentWindow?.postMessage(payload, '*')
  }, [])

  useEffect(() => {
    const onMessage = (event) => {
      if (event.data?.type === 'omecca-map-ready') {
        mapReadyRef.current = true
        mapIframeRef.current?.contentWindow?.postMessage(
          { type: 'omecca-theme', theme: darkMode ? 'dark' : 'light' },
          '*',
        )
        // 지도가 막 로드된 시점의(최신) activeView 기준으로 패널 모드도 바로 맞춰준다
        // (예: 새로고침 직후 바로 "추적 차량" 뷰였던 경우).
        const currentView = activeViewRef.current
        mapIframeRef.current?.contentWindow?.postMessage(
          { type: 'omecca-view-mode', showVideoPanel: currentView === 'tracking' },
          '*',
        )
        if (currentView === 'tracking') {
          mapIframeRef.current?.contentWindow?.postMessage({ type: 'omecca-focus-tracked-vehicle' }, '*')
        }
        // 준비되기 전에 놓쳤던 "이 차량 추적해줘" 요청이 있으면 지금 다시 보낸다.
        if (pendingTrackEventRef.current) {
          mapIframeRef.current?.contentWindow?.postMessage(pendingTrackEventRef.current, '*')
          pendingTrackEventRef.current = null
        }
      }

      // 지도(iframe) 안의 "📹 CCTV 영상 보기" 버튼(추적 차량 팝업)을 눌렀을 때 온다.
      // "대시보드"(미니 지도 레이아웃)에는 영상 패널 자체가 없으므로, 이 요청을 받으면
      // "추적 차량" 전체화면 뷰로 전환해서 방금 연결된 영상이 실제로 보이게 한다.
      // onChangeView는 App.jsx에서 setActiveView를 그대로 내려받은 것이라 항상 안정된
      // 참조이므로, 이 핸들러가 darkMode 변경 시에만 재구독되어도 최신 함수를 그대로 쓴다.
      if (event.data?.type === 'omecca-request-tracking-view') {
        onChangeView('tracking')
      }
    }
    window.addEventListener('message', onMessage)
    return () => window.removeEventListener('message', onMessage)
  }, [darkMode, onChangeView])

  useEffect(() => {
    if (!mapReadyRef.current) return
    mapIframeRef.current?.contentWindow?.postMessage(
      { type: 'omecca-theme', theme: darkMode ? 'dark' : 'light' },
      '*',
    )
  }, [darkMode])

  // 대시보드(미니 지도) / 지도(전체화면) / 추적 차량(전체화면 + CCTV 영상 패널) 전환 시
  // 지도 iframe에 패널 모드를 알린다. "추적 차량"으로 들어올 때는 추가로 지금 지도에
  // 떠 있는 추적 차량으로 포커스 이동 + 팝업을 열어달라고도 함께 요청한다.
  useEffect(() => {
    if (activeView !== 'dashboard' && activeView !== 'map' && activeView !== 'tracking') return
    postToMap({ type: 'omecca-view-mode', showVideoPanel: activeView === 'tracking' })
    if (activeView === 'tracking') {
      postToMap({ type: 'omecca-focus-tracked-vehicle' })
    }
  }, [activeView, postToMap])

  const seenCams = [...new Set(events.map((ev) => ev.camId).filter(Boolean))]
  const camIds = seenCams.length > 0 ? seenCams : []

  useEffect(() => {
    if (!pdfTarget) return
    let cancelled = false

    const run = async () => {
      if (!reportRef.current) return
      setExporting(true)
      try {
        const canvas = await html2canvas(reportRef.current, { scale: 2, backgroundColor: '#ffffff' })
        const imgData = canvas.toDataURL('image/png')
        const pdf = new jsPDF({ orientation: 'p', unit: 'pt', format: 'a4' })
        const pageWidth = pdf.internal.pageSize.getWidth()
        const pageHeight = pdf.internal.pageSize.getHeight()
        const imgWidth = pageWidth
        const imgHeight = (canvas.height * imgWidth) / canvas.width

        let heightLeft = imgHeight
        let position = 0
        pdf.addImage(imgData, 'PNG', 0, position, imgWidth, imgHeight)
        heightLeft -= pageHeight

        while (heightLeft > 0) {
          position = heightLeft - imgHeight
          pdf.addPage()
          pdf.addImage(imgData, 'PNG', 0, position, imgWidth, imgHeight)
          heightLeft -= pageHeight
        }

        pdf.save(`report_${pdfTarget.id}_${Date.now()}.pdf`)
      } catch (err) {
        console.error(err)
        alert('PDF 생성 중 오류가 발생했습니다.')
      } finally {
        if (!cancelled) {
          setExporting(false)
          setPdfTarget(null)
        }
      }
    }

    const id = requestAnimationFrame(() => requestAnimationFrame(run))
    return () => {
      cancelled = true
      cancelAnimationFrame(id)
    }
  }, [pdfTarget])

  const bboxStyle = pdfTarget?.bbox
    ? {
        left: `${pdfTarget.bbox[0] * 100}%`,
        top: `${pdfTarget.bbox[1] * 100}%`,
        width: `${pdfTarget.bbox[2] * 100}%`,
        height: `${pdfTarget.bbox[3] * 100}%`,
      }
    : null

  const handleFullscreenMap = () => {
    const el = mapIframeRef.current
    if (el?.requestFullscreen) el.requestFullscreen().catch(() => {})
  }

  // 이벤트 카드 클릭: 기존처럼 포커스만 옮기는 게 아니라, 차량 관련 이벤트
  // (음주운전 의심/미등록차량/신호위반/불법유턴)면 곧바로 "추적 차량" 뷰로 넘어가서
  // 그 차량을 GIS 지도 위에 실시간으로 보여준다.
  const handleEventCardClick = (ev) => {
    onSelectCam(ev)
    if (!VEHICLE_TRACK_EVENT_TYPES.has(ev.eventType)) return
    onChangeView('tracking')
    const message = { type: 'omecca-track-vehicle-event', vehicle: buildTrackVehiclePayload(ev) }
    if (mapReadyRef.current) {
      postToMap(message)
    } else {
      // 지도가 아직 준비 전이면 큐에 담아두고, "omecca-map-ready"가 오는 즉시 보낸다.
      pendingTrackEventRef.current = message
    }
  }

  // 화면 중앙 차량 알림 팝업의 "지도에서 실시간으로 보기" 버튼: 이벤트 카드를 직접 클릭한 것과
  // 똑같이 동작시키고(포커스 + 추적 차량 뷰 전환 + 지도 포커스 메시지), 팝업은 닫는다.
  const handleVehicleAlertFocus = () => {
    if (!vehicleAlert) return
    handleEventCardClick(vehicleAlert)
    onDismissVehicleAlert?.()
  }

  return (
    <div className="control-screen">
      <aside className="control-sidebar">
        <div className="control-sidebar-section">
          <div className="control-sidebar-label">OVERVIEW</div>
          <SidebarRow
            icon={<IconGrid />}
            label="대시보드"
            count={1}
            active={activeView === 'dashboard'}
            onClick={() => onChangeView('dashboard')}
          />
          <SidebarRow
            icon={<IconMap />}
            label="지도"
            count={camIds.length}
            active={activeView === 'map'}
            onClick={() => onChangeView('map')}
          />
          <SidebarRow
            icon={<IconCamera />}
            label="CCTV"
            count={camIds.length}
            active={activeView === 'cctv'}
            onClick={() => onChangeView('cctv')}
          />
          <SidebarRow
            icon={<IconClock />}
            label="남은 이벤트"
            count={total}
            active={activeView === 'events'}
            onClick={() => onChangeView('events')}
          />
        </div>
        <div className="control-sidebar-section">
          <div className="control-sidebar-label">ALERTS</div>
          <SidebarRow
            icon={<IconAlertCircle />}
            label="추적 차량"
            count={vehicleTargetCount}
            tone="amber"
            active={activeView === 'tracking'}
            onClick={() => onChangeView('tracking')}
          />
          <SidebarRow
            icon={<IconSquare />}
            label="관심 대상"
            count={personTargetCount}
            active={activeView === 'targets'}
            onClick={() => onChangeView('targets')}
          />
        </div>
      </aside>

      <div className="control-content">
        {/* 이 지도 iframe은 activeView가 뭐든 항상 DOM에 남아있어야 한다(조건부 렌더링 금지).
            예전엔 activeView가 'cctv'/'events'/'targets'일 때 이 블록 자체가 사라졌는데,
            그러면 React가 iframe을 통째로 unmount해버려서 안에서 진행 중이던 추적 차량
            데모(움직이는 마커, WebSocket 연결, Forza 타임라인)가 전부 초기화됐다 — CCTV/남은
            이벤트/관심대상 눌렀다가 대시보드·추적차량으로 돌아오면 지도가 새로 처음부터 로드되며
            방금까지 이동 중이던 차량이 사라져 보이는 버그의 원인이었다. 이제는 항상 마운트해두고
            "control-map-col-hidden"(display:none) 클래스로 화면에서만 숨겨서, iframe 내부 상태가
            뷰를 왔다갔다 해도 계속 살아있게(추적이 끊기지 않게) 한다. */}
        <div
          className={`control-map-col ${activeView !== 'dashboard' ? 'control-map-col-full' : ''} ${
            activeView === 'dashboard' || activeView === 'map' || activeView === 'tracking' ? '' : 'control-map-col-hidden'
          }`}
        >
          <div className="control-map-wrap">
            {/* allow="autoplay"가 없으면 크로스오리진 iframe 안의 <video autoplay muted>가
                Permissions Policy에 막혀 재생이 안 되고 첫 프레임에서 멈춘 채로 보인다
                (video.play()는 catch로 조용히 실패해서 콘솔 경고 외엔 티가 안 남) -
                "CCTV 영상은 뜨는데 정지/끊겨 보인다"는 문제의 실제 원인이었다. */}
            <iframe ref={mapIframeRef} className="control-map" src="http://localhost:4000/?embed=map" title="GIS 지도" allow="autoplay; fullscreen" />
            <button type="button" className="control-map-fullscreen-btn" onClick={handleFullscreenMap}>
              전체 화면 기록
            </button>
          </div>
        </div>

        {activeView === 'dashboard' && (
          <aside className="control-events-col">
            <div className="control-events-head">AI 관제 이벤트</div>

            <div className="control-events-list">
              {events.length === 0 && (
                <div className="control-events-empty">감지된 이벤트가 없습니다</div>
              )}
              {events.map((ev) => {
                const risk = EVENT_RISK[ev.eventType] || 1
                const isFocused = focusedEvent?.id === ev.id
                return (
                  <div
                    key={ev.id}
                    role="button"
                    tabIndex={0}
                    className={`control-event-card tier-${risk} ${isFocused ? 'focused' : ''}`}
                    onClick={() => handleEventCardClick(ev)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') handleEventCardClick(ev)
                    }}
                  >
                    <div className="control-event-top">
                      <span>{fmtTime(ev.occurredAt)} · {ev.camId || '-'}</span>
                      <button
                        type="button"
                        className="control-event-pdf-btn"
                        title="PDF 리포트 생성"
                        disabled={exporting}
                        onClick={(e) => {
                          e.stopPropagation()
                          setPdfTarget(ev)
                        }}
                      >
                        📄
                      </button>
                    </div>
                    <div className="control-event-title-row">
                      <span className="control-event-title">{EVENT_LABEL[ev.eventType] || ev.eventType}</span>
                      {risk === 3 && <span className="control-event-chip chip-red">위험</span>}
                      {ev.isRegisteredTarget && <span className="control-event-chip chip-amber">관심대상</span>}
                    </div>
                    <div className="control-event-sub">{metaLine(ev)}</div>
                  </div>
                )
              })}
            </div>
          </aside>
        )}

        {activeView === 'cctv' && (
          <div className="control-fullview">
            <CctvGrid events={events} focusedEvent={focusedEvent} onSelectCam={onSelectCam} />
          </div>
        )}

        {activeView === 'events' && (
          <div className="control-fullview">
            <EventList events={events} focusedId={focusedEvent?.id ?? null} onSelect={onSelectCam} />
          </div>
        )}

        {activeView === 'targets' && (
          <div className="control-fullview">
            <TargetsPanel onChanged={onTargetsChanged} />
          </div>
        )}
      </div>

      {pdfTarget && (
        <div className="pdf-report-offscreen">
          <div ref={reportRef} className="evidence-report-sheet">
            <div className="evidence-report-topline">
              <span>OMECCA-3 EVIDENCE REPORT</span>
              <span>REF. {fmtRefId(pdfTarget)}</span>
            </div>
            <hr />
            <h1>{EVENT_LABEL[pdfTarget.eventType] || pdfTarget.eventType} 증거 리포트</h1>

            <section>
              <h2>1. 사건 개요</h2>
              <table className="evidence-kv">
                <tbody>
                  <tr><th>이벤트 유형</th><td>{pdfTarget.eventType}</td></tr>
                  <tr><th>발생 시각</th><td>{fmtIsoRaw(pdfTarget.occurredAt)}</td></tr>
                  <tr><th>카메라 / 위치</th><td>{pdfTarget.camId || '-'} / {fmtLocationLabel(pdfTarget)}</td></tr>
                  <tr><th>추적 ID</th><td>{pdfTarget.trackId || '-'}</td></tr>
                  <tr><th>차량 번호판</th><td>{fmtPlate(pdfTarget)}</td></tr>
                  <tr><th>탐지 신뢰도</th><td>{pdfTarget.confidence != null ? `${(pdfTarget.confidence * 100).toFixed(1)}%` : '-'}</td></tr>
                </tbody>
              </table>
            </section>

            <section>
              <h2>2. 증거 이미지 (탐지 영역 표시)</h2>
              <div className="evidence-images">
                <div className="evidence-image-box">
                  <div className="evidence-image-label">사건 발생 전</div>
                  <div className="evidence-image-frame">
                    {pdfTarget.frameRefBefore ? <img src={pdfTarget.frameRefBefore} alt="사건 발생 전" /> : <div className="evidence-image-empty" />}
                    {bboxStyle && <div className="evidence-bbox" style={bboxStyle} />}
                  </div>
                </div>
                <div className="evidence-image-box">
                  <div className="evidence-image-label">사건 발생 후</div>
                  <div className="evidence-image-frame">
                    {pdfTarget.frameRefAfter ? <img src={pdfTarget.frameRefAfter} alt="사건 발생 후" /> : <div className="evidence-image-empty" />}
                    {bboxStyle && <div className="evidence-bbox" style={bboxStyle} />}
                  </div>
                </div>
              </div>
              <div className="evidence-image-note">* 붉은 사각형은 탐지 모듈이 보고한 bounding box(bbox) 좌표를 표시한 영역입니다.</div>
            </section>

            <section>
              <h2>3. 처리 정보</h2>
              <div className="evidence-process-boxes">
                <div className="evidence-process-box">
                  <div className="evidence-process-label">확인 관제요원</div>
                </div>
                <div className="evidence-process-box">
                  <div className="evidence-process-label">처리 상태 / 인계 기관</div>
                </div>
              </div>
            </section>

            <div className="evidence-report-footer">
              생성일시: {fmtGeneratedAt(new Date())} / 오메카3 관제시스템 자동 생성 / 본 문서는 수사/행정 목적으로만 사용됩니다.
            </div>
          </div>
        </div>
      )}

      <VehicleAlertPopup event={vehicleAlert} onFocus={handleVehicleAlertFocus} onDismiss={onDismissVehicleAlert} />
    </div>
  )
}