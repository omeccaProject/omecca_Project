import { useCallback, useEffect, useMemo, useState } from 'react'
import Header from './components/Header'
import CctvGrid from './components/CctvGrid'
import EventList from './components/EventList'
import MainDashboard from './components/MainDashboard'
import LandingPage from './pages/LandingPage'
import LoginPage from './pages/LoginPage'
import SignupPage from './pages/SignupPage'
import AdminApprovalPage from './pages/AdminApprovalPage'
import { fetchInitialEvents, fetchActiveTargets } from './api'
import { useEventSocket } from './hooks/useEventSocket'
import { useCrossWindowSync } from './hooks/useCrossWindowSync'
import { useRouter } from './hooks/useRouter'
import { clearSession, getUser, isAdmin, isLoggedIn } from './auth'
import { EVENT_RISK, VEHICLE_TRACK_EVENT_TYPES } from './constants'
import { openSplitScreenMode } from './utils/splitScreen'
import './App.css'
import './pages/AuthPages.css'

function compareByRiskThenTime(a, b) {
  const riskDiff = (EVENT_RISK[b.eventType] || 0) - (EVENT_RISK[a.eventType] || 0)
  if (riskDiff !== 0) return riskDiff
  return new Date(b.occurredAt) - new Date(a.occurredAt)
}

// monitor1/2/3 = 3분할 모드 전용 뷰(Header의 "▦" 버튼이 여는 새 창들이 이 파라미터로 들어온다).
// monitor1: 평소의 통합 관제 대시보드 화면 그대로(아래 일반 렌더링으로 흘려보냄),
// monitor2/3: CCTV 그리드(카메라 1~9 / 10~18), 화면 전체를 채움.
const KIOSK_VIEWS = ['events', 'cctv', 'map', 'monitor1', 'monitor2', 'monitor3']
const DARK_MODE_KEY = 'omecca_dark_mode'

export default function App() {
  const [events, setEvents] = useState([])
  const [targets, setTargets] = useState([])
  const [focusedId, setFocusedId] = useState(null)
  const [autoFocus, setAutoFocus] = useState(true)
  const [filterType, setFilterType] = useState('')
  const [filterCam, setFilterCam] = useState('')
  const [darkMode, setDarkMode] = useState(() => localStorage.getItem(DARK_MODE_KEY) === '1')
  // 왼쪽 사이드바 네비게이션: 대시보드(현재 상태) / 지도(GIS 전체화면) / cctv(그리드뷰어) / events(전체 이벤트 목록)
  const [activeView, setActiveView] = useState('dashboard')
  // 실시간으로 새 차량 이벤트가 들어왔을 때 화면 중앙에 띄우는 알림 팝업 대상(없으면 null).
  // 어느 화면을 보고 있든 이 상태 하나로 MainDashboard가 팝업을 그린다.
  const [vehicleAlert, setVehicleAlert] = useState(null)
  const { pathname, navigate } = useRouter()

  useEffect(() => {
    localStorage.setItem(DARK_MODE_KEY, darkMode ? '1' : '0')
  }, [darkMode])

  const initialParam = new URLSearchParams(window.location.search).get('view')
  const kioskView = KIOSK_VIEWS.includes(initialParam) ? initialParam : null

  const upsertEvent = useCallback((ev, focusIfNew) => {
    setEvents((prev) => {
      const next = [ev, ...prev.filter((e) => e.id !== ev.id)]
      next.sort(compareByRiskThenTime)
      return next
    })
    if (focusIfNew) {
      setAutoFocus((current) => {
        if (current) setFocusedId(ev.id)
        return current
      })
      // 실시간으로 새로 들어온 차량 이벤트는 리스트에 조용히 쌓이는 대신, 어느 화면을
      // 보고 있든 바로 알아챌 수 있게 화면 중앙 알림 팝업을 띄운다(가장 최신 것 하나만 유지).
      if (VEHICLE_TRACK_EVENT_TYPES.has(ev.eventType)) {
        setVehicleAlert(ev)
      }
    }
  }, [])

  // [버그 수정: "새로고침해도 이벤트가 안 사라지는 문제"] 게이트웨이가 이벤트를 지울 때
  // /topic/events/deleted로 실시간 방송해주면, 그 trackId와 일치하는 항목을 화면에서
  // 바로 제거한다. 이전에는 지워졌다는 신호를 받을 방법이 없어서, 페이지 로드 시점에
  // GET으로 가져온 옛날 항목이 실제로는 DB에서 지워졌어도 화면엔 계속 남아있었다
  // (그 GET이 삭제보다 먼저 끝났는지에 따라 결과가 매번 달라지던 원인).
  const removeEventsByTrackId = useCallback((payload) => {
    const trackId = payload && payload.trackId
    if (!trackId) return
    setEvents((prev) => prev.filter((e) => e.trackId !== trackId))
  }, [])

  const connected = useEventSocket((ev) => upsertEvent(ev, true), removeEventsByTrackId)

  // 새로고침 버튼(Header "⟳") 클릭 시 스피너를 돌려서 "눌러도 아무 반응이 없어 보이는"
  // 문제를 없앤다. 원래도 loadInitial/loadTargets 자체는 정상 동작했지만(재조회는 됨),
  // 성공/실패와 무관하게 화면에 아무 시각적 피드백이 없어서 고장난 것처럼 보였던 것 —
  // 특히 웹소켓이 이미 실시간으로 최신 이벤트를 계속 밀어주고 있어서, 수동 새로고침을
  // 눌러도 화면에 "새로 추가되는 게" 거의 없어 더더욱 눌러도 티가 안 났다.
  const [refreshing, setRefreshing] = useState(false)

  const loadInitial = useCallback(() => {
    return fetchInitialEvents(30)
      .then((list) => {
        const sorted = [...list].sort(compareByRiskThenTime)
        setEvents(sorted)
        if (sorted.length > 0) setFocusedId((current) => current ?? sorted[0].id)
      })
      .catch((err) => {
        // 예전엔 실패해도 조용히 무시해서, 만약 인증 만료 등으로 조회 자체가 실패해도
        // 화면엔 아무 신호가 없었다 - 최소한 콘솔에는 남겨서 디버깅 가능하게 함.
        console.error('이벤트 목록 새로고침 실패:', err)
        throw err
      })
  }, [])

  const loadTargets = useCallback(() => {
    return fetchActiveTargets()
      .then((list) => setTargets(Array.isArray(list) ? list : []))
      .catch((err) => {
        console.error('관심 대상 목록 새로고침 실패:', err)
        throw err
      })
  }, [])

  useEffect(() => {
    loadInitial().catch(() => {})
    loadTargets().catch(() => {})
  }, [loadInitial, loadTargets])

  // 웹소켓(/topic/events)은 "새로 생긴" 이벤트만 밀어준다 - 누군가 HeidiSQL 등에서
  // DB 행을 직접 지워도 그 사실은 알려주지 않으므로, 지운 이벤트가 화면에서 안 사라지고
  // 계속 남아있게 된다(낙하물 반복 테스트 중 발견됨). loadInitial()은 매번 서버 목록으로
  // 통째로 교체(setEvents(sorted))하는 방식이라 그 자체로 "지금 DB에 있는 것만 남기기"가
  // 되므로, 짧은 주기로 백그라운드에서 다시 불러와 화면을 DB 상태와 계속 맞춰준다.
  useEffect(() => {
    const timer = setInterval(() => {
      loadInitial().catch(() => {})
    }, 5000)
    return () => clearInterval(timer)
  }, [loadInitial])

  const handleRefresh = useCallback(() => {
    if (refreshing) return
    setRefreshing(true)
    // 새로고침이 순식간에 끝나도(로컬 네트워크라 보통 100ms 이내) 스피너가 최소
    // 400ms는 돌게 해서 "눌렀다"는 게 눈에 보이게 한다.
    const minSpin = new Promise((resolve) => setTimeout(resolve, 400))
    Promise.allSettled([loadInitial(), loadTargets(), minSpin]).then((results) => {
      setRefreshing(false)
      const failed = results.slice(0, 2).some((r) => r.status === 'rejected')
      if (failed) {
        alert('새로고침 중 일부 데이터를 불러오지 못했습니다. 게이트웨이 서버 연결 상태를 확인해주세요.')
      }
    })
  }, [refreshing, loadInitial, loadTargets])

  // "▦" 버튼(Header) - 지금 이 창은 그대로 두고(=1번 모니터), 새 창 2개(?view=monitor2/3)만
  // 열어 나머지 모니터 2대에 배치한다. 실제 모니터 좌표에 자동으로 배치하지 못한 경우
  // (권한 거부/미지원 브라우저) 사용자에게 직접 드래그해달라고 안내한다.
  const handleSplitScreen = useCallback(async () => {
    const result = await openSplitScreenMode()
    if (result.blocked) {
      alert(
        '팝업 차단으로 창을 하나도 열지 못했습니다.\n' +
          '브라우저 주소창의 팝업 차단 아이콘을 눌러 이 사이트의 팝업을 허용한 뒤 다시 시도해주세요.'
      )
    } else if (!result.placed) {
      alert(
        '창 2개를 열었습니다.\n' +
          '이 브라우저에서는 모니터를 자동으로 인식하지 못해 화면 왼쪽부터 나란히 띄웠어요.\n' +
          '각 창을 원하는 모니터로 한 번만 드래그해서 옮겨주세요(2번=CCTV 1~9, 3번=CCTV 10~18). ' +
          '지금 이 창(대시보드 화면)은 그대로 1번 모니터로 두시면 됩니다.'
      )
    }
  }, [])

  const { broadcastFocus } = useCrossWindowSync(useCallback((remoteId) => {
    setFocusedId(remoteId)
  }, []))

  const handleFocus = useCallback((ev) => {
    setFocusedId(ev.id)
    broadcastFocus(ev.id)
  }, [broadcastFocus])

  const filtered = useMemo(() => {
    return events.filter((ev) => {
      if (filterType && ev.eventType !== filterType) return false
      if (filterCam && !(ev.camId || '').toLowerCase().includes(filterCam.toLowerCase())) return false
      return true
    })
  }, [events, filterType, filterCam])

  const focusedEvent = events.find((e) => e.id === focusedId) || null

  // 사이드바 "추적 차량"/"관심 대상" 카운트: 개별 이벤트가 아니라 target 레지스트리(status=ACTIVE) 기준.
  // target_type === 'VEHICLE' → 다중 CCTV로 추적 중인 차량, 'PERSON' → 추적 중인 인물(관심 대상).
  const vehicleTargetCount = targets.filter((t) => t.targetType === 'VEHICLE').length
  const personTargetCount = targets.filter((t) => t.targetType === 'PERSON').length

  const latestEvent = filtered[0] || null

  if (kioskView === 'cctv') {
    return (
      <main className="kiosk">
        <CctvGrid events={filtered} focusedEvent={focusedEvent} onSelectCam={handleFocus} />
      </main>
    )
  }
  if (kioskView === 'events') {
    return (
      <main className="kiosk">
        <EventList events={filtered} focusedId={focusedId} onSelect={handleFocus} />
      </main>
    )
  }
  if (kioskView === 'map') {
    return (
      <main className="kiosk">
        <iframe src="http://localhost:4000" title="GIS 지도" style={{ width: '100%', height: '100vh', border: 'none' }} />
      </main>
    )
  }

  // ---- 3분할 모드 전용 뷰 (Header "▦" 버튼이 여는 3개의 새 창) ----
  // 1번 모니터: "이 화면을 그대로" 요청 - 즉 로그인 후 보이는 평소의 통합 관제 대시보드
  // (사이드바 + GIS 지도 + AI 관제 이벤트) 그 자체다. 그래서 여기서 별도로 그리지 않고
  // kioskView === 'monitor1'인 경우 그냥 아무것도 하지 않고 아래로 흘려보내서, 맨 아래
  // 있는 평소의 로그인 화면 렌더링(Header + MainDashboard)이 그대로 나오게 한다.
  // (activeView 기본값이 이미 'dashboard'라서 새 창을 열면 항상 이 화면부터 시작한다.)

  // 2번 모니터: CCTV 1~9, 3번 모니터: CCTV 10~18 - 같은 카메라 목록을 앞/뒤로 나눠서
  // 두 창이 서로 겹치지 않게 한다(둘 다 fixedCount=9로 6/9 토글은 숨기고 화면 전체를 채운다).
  if (kioskView === 'monitor2') {
    return (
      <main className="kiosk kiosk-cctv-fill">
        <CctvGrid events={filtered} focusedEvent={focusedEvent} onSelectCam={handleFocus} camOffset={0} fixedCount={9} />
      </main>
    )
  }
  if (kioskView === 'monitor3') {
    return (
      <main className="kiosk kiosk-cctv-fill">
        <CctvGrid events={filtered} focusedEvent={focusedEvent} onSelectCam={handleFocus} camOffset={9} fixedCount={9} />
      </main>
    )
  }

  if (pathname === '/login') return <LoginPage navigate={navigate} />
  if (pathname === '/signup') return <SignupPage navigate={navigate} />
  if (pathname === '/landing') return <LandingPage navigate={navigate} />
  if (pathname.startsWith('/admin')) return <AdminApprovalPage navigate={navigate} />

  // "/"(주소만 치고 들어온 경우)나 그 외 정의되지 않은 경로는 로그인 여부와 상관없이
  // 항상 랜딩페이지부터 보여준다. 실제 관제 대시보드는 "/dashboard"에서만 렌더링하며,
  // 로그인 성공(LoginPage)했을 때만 그쪽으로 이동시킨다.
  if (pathname !== '/dashboard') {
    return <LandingPage navigate={navigate} />
  }

  if (!isLoggedIn()) {
    navigate('/login')
    return null
  }

  const user = getUser()
  const handleLogout = () => {
    clearSession()
    navigate('/login')
  }

  return (
    <div className="app-shell" data-theme={darkMode ? 'dark' : 'light'}>
      <Header
        connected={connected}
        onRefresh={handleRefresh}
        refreshing={refreshing}
        darkMode={darkMode}
        onToggleDarkMode={() => setDarkMode((d) => !d)}
        user={user}
        onLogout={handleLogout}
        onGoAdmin={isAdmin() ? () => navigate('/admin/users') : null}
        onSplitScreen={handleSplitScreen}
      />
      <main className="control-main">
        <MainDashboard
          events={filtered}
          focusedEvent={focusedEvent}
          onSelectCam={handleFocus}
          total={events.length}
          vehicleTargetCount={vehicleTargetCount}
          personTargetCount={personTargetCount}
          targets={targets}
          darkMode={darkMode}
          activeView={activeView}
          onChangeView={setActiveView}
          onTargetsChanged={loadTargets}
          vehicleAlert={vehicleAlert}
          onDismissVehicleAlert={() => setVehicleAlert(null)}
        />
      </main>
    </div>
  )
}