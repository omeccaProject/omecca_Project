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
  const [view, setView] = useState('events')   // ← 추가: 'events' | 'map'

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
        view={view}                 // ← 추가
        onViewChange={setView}      // ← 추가
      />
      <main>
        {view === 'events' ? (
          <div className="top-row">
            <CctvGrid events={filtered} focusedEvent={focusedEvent} onSelectCam={(ev) => setFocusedId(ev.id)} />
            <EventList events={filtered} focusedId={focusedId} onSelect={(ev) => setFocusedId(ev.id)} />
          </div>
        ) : (
          <iframe
            src="http://localhost:4000"
            title="GIS 지도"
            style={{ width: '100%', height: 'calc(100vh - 120px)', border: 'none' }}
          />
        )}
      </main>
    </>
  )
}