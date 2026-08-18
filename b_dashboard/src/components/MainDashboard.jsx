import { useCallback, useEffect, useRef, useState } from 'react'
import { EVENT_RISK, EVENT_LABEL, VEHICLE_TRACK_EVENT_TYPES } from '../constants'
import { generateEventReport } from '../api'
import CctvGrid from './CctvGrid'
import EventList from './EventList'
import TargetsPanel from './TargetsPanel'
import EventDetailModal from './EventDetailModal'

function fmtTime(iso) {
  if (!iso) return '-'
  return iso.replace('T', ' ').split('.')[0]
}

function fmtLocation(ev) {
  if (ev.location?.lat == null || ev.location?.lng == null) return '-'
  return `${ev.location.lat.toFixed(5)}, ${ev.location.lng.toFixed(5)}`
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

// 좌/우 사이드바 접기·펼치기 버튼 아이콘. 기본은 왼쪽(‹)을 가리키고,
// flipped=true면 오른쪽(›)을 가리키게 180도 회전한다.
function IconChevron({ flipped }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      style={{ transform: flipped ? 'rotate(180deg)' : 'none' }}
    >
      <path d="M15 6l-6 6 6 6" />
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
  // 대시보드 상세화면에서 "📄 PDF 리포트 생성" 버튼을 누른 이벤트의 id. b_report를 그 자리에서
  // 실행해 실제 PDF를 만드는 동안(수 초) 버튼을 잠그고 로딩 표시를 보여주기 위한 상태 -
  // 예전처럼 화면을 캡쳐(html2canvas)해서 클라이언트에서 PDF를 만드는 방식이 아니라
  // 백엔드가 만든 진짜 PDF를 그대로 다운로드시키는 방식이라 오프스크린 렌더링이 필요 없다.
  const [generatingReportId, setGeneratingReportId] = useState(null)
  // 이벤트 카드를 클릭하면 상세화면(사건 전/후 캡처 이미지 · 위치 · PDF 리포트 버튼)이
  // 뜨는데, 그 대상 이벤트를 담아둔다. null이면 상세화면이 닫힌 상태.
  const [detailEvent, setDetailEvent] = useState(null)
  // 왼쪽(메뉴)/오른쪽(AI 관제 이벤트) 사이드바 접기 상태. 새로고침해도 마지막 상태가
  // 유지되도록 localStorage에 저장한다(다른 토글들과 동일한 패턴 - CctvGrid의 camCount 참고).
  const [leftCollapsed, setLeftCollapsed] = useState(
    () => localStorage.getItem('omecca_left_sidebar_collapsed') === '1',
  )
  const [rightCollapsed, setRightCollapsed] = useState(
    () => localStorage.getItem('omecca_right_sidebar_collapsed') === '1',
  )
  useEffect(() => {
    localStorage.setItem('omecca_left_sidebar_collapsed', leftCollapsed ? '1' : '0')
  }, [leftCollapsed])
  useEffect(() => {
    localStorage.setItem('omecca_right_sidebar_collapsed', rightCollapsed ? '1' : '0')
  }, [rightCollapsed])
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

  // "📄 PDF 리포트 생성" 버튼 클릭: b_report(파이썬/ReportLab)를 그 자리에서 호출해 실제
  // PDF를 만들고, 완성된 바이너리를 받아 즉시 다운로드시킨다. 관제요원이 버튼을 누른
  // 순간에만 생성되고(기획서 방향과 일치), 이미 만들어진 적 있는 이벤트면 백엔드가 기존
  // PDF를 그대로 재사용해서 돌려준다.
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
      <div className="control-sidebar-wrap">
        <aside className={`control-sidebar ${leftCollapsed ? 'collapsed' : ''}`}>
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
        <button
          type="button"
          className="sidebar-collapse-btn sidebar-collapse-btn-left"
          onClick={() => setLeftCollapsed((v) => !v)}
          title={leftCollapsed ? '메뉴 펼치기' : '메뉴 접기'}
        >
          <IconChevron flipped={leftCollapsed} />
        </button>
      </div>

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
          <div className="control-events-wrap">
            <button
              type="button"
              className="sidebar-collapse-btn sidebar-collapse-btn-right"
              onClick={() => setRightCollapsed((v) => !v)}
              title={rightCollapsed ? 'AI 관제 이벤트 펼치기' : 'AI 관제 이벤트 접기'}
            >
              <IconChevron flipped={!rightCollapsed} />
            </button>
            <aside className={`control-events-col ${rightCollapsed ? 'collapsed' : ''}`}>
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
                    onClick={() => {
                      handleEventCardClick(ev)
                      setDetailEvent(ev)
                    }}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        handleEventCardClick(ev)
                        setDetailEvent(ev)
                      }
                    }}
                  >
                    <div className="control-event-top">
                      <span>{fmtTime(ev.occurredAt)} · {ev.camId || '-'}</span>
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
          </div>
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

      <VehicleAlertPopup event={vehicleAlert} onFocus={handleVehicleAlertFocus} onDismiss={onDismissVehicleAlert} />
      <EventDetailModal event={detailEvent} onClose={() => setDetailEvent(null)} />
    </div>
  )
}