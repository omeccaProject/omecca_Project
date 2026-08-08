import { useCallback, useEffect, useMemo, useState } from 'react'
import Header from './components/Header'
import CctvGrid from './components/CctvGrid'
import EventList from './components/EventList'
import { fetchInitialEvents } from './api'
import { useEventSocket } from './hooks/useEventSocket'
import { EVENT_RISK } from './constants'
import './App.css'

// 위험도(높음→낮음) 우선, 같은 위험도면 최신순.
// 정의되지 않은 이벤트 유형은 위험도 0으로 취급해 맨 뒤로 밀림.
function compareByRiskThenTime(a, b) {
  const riskDiff = (EVENT_RISK[b.eventType] || 0) - (EVENT_RISK[a.eventType] || 0)
  if (riskDiff !== 0) return riskDiff
  return new Date(b.occurredAt) - new Date(a.occurredAt)
}

export default function App() {
  const [events, setEvents] = useState([])
  const [focusedId, setFocusedId] = useState(null)
  const [autoFocus, setAutoFocus] = useState(true)
  const [filterType, setFilterType] = useState('')
  const [filterCam, setFilterCam] = useState('')

  // 새 이벤트 하나를 목록에 반영 (중복 id는 최신 값으로 교체 후 위험도→시간순 정렬)
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
    }
  }, [])

  // WebSocket 훅 — 대시보드 입장에선 "새 이벤트가 오면 upsertEvent 호출해줘"만 넘기면 끝.
  // /topic/events 구독, 재연결 등은 훅 안에서 전부 처리됨. 이 컴포넌트는 WebSocket이 뭔지 몰라도 됨.
  const connected = useEventSocket((ev) => upsertEvent(ev, true))

  const loadInitial = useCallback(() => {
    fetchInitialEvents(30)
      .then((list) => {
        const sorted = [...list].sort(compareByRiskThenTime)
        setEvents(sorted)
        if (sorted.length > 0) setFocusedId((current) => current ?? sorted[0].id)
      })
      .catch(() => {})
  }, [])

  // 최초 진입 시 한 번, 게이트웨이에 이미 쌓여있던 이벤트를 불러온다.
  useEffect(() => {
    loadInitial()
  }, [loadInitial])

  const filtered = useMemo(() => {
    return events.filter((ev) => {
      if (filterType && ev.eventType !== filterType) return false
      if (filterCam && !(ev.camId || '').toLowerCase().includes(filterCam.toLowerCase())) return false
      return true
    })
  }, [events, filterType, filterCam])

  const focusedEvent = events.find((e) => e.id === focusedId) || null
  const targetCount = events.filter((e) => e.isRegisteredTarget).length

  return (
    <>
      <Header
        connected={connected}
        total={events.length}
        targetCount={targetCount}
        autoFocus={autoFocus}
        onAutoFocusChange={setAutoFocus}
        filterType={filterType}
        onFilterTypeChange={setFilterType}
        filterCam={filterCam}
        onFilterCamChange={setFilterCam}
        onRefresh={loadInitial}
      />
      <main>
        <div className="top-row">
          <CctvGrid events={filtered} focusedEvent={focusedEvent} onSelectCam={(ev) => setFocusedId(ev.id)} />
          <EventList events={filtered} focusedId={focusedId} onSelect={(ev) => setFocusedId(ev.id)} />
        </div>
      </main>
    </>
  )
}