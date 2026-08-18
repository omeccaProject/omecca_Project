import { useEffect, useState } from 'react'

function fmtClock(date) {
  const p = (n) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${p(date.getMonth() + 1)}-${p(date.getDate())} ${p(date.getHours())}:${p(date.getMinutes())}:${p(date.getSeconds())} KST`
}

export default function Header({
  connected,
  onRefresh,
  darkMode, onToggleDarkMode,
  user, onLogout, onGoAdmin,
  onSplitScreen,
}) {
  const [now, setNow] = useState(() => new Date())

  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(t)
  }, [])

  return (
    <header className="top-bar">
      <div className="top-bar-left">
        <span className="top-bar-dots">
          <span /><span /><span />
        </span>
        <span className={`top-bar-live ${connected ? 'on' : 'off'}`}>
          <span className="top-bar-live-dot" />
          {connected ? 'LIVE' : 'OFFLINE'}
        </span>
        <span className="top-bar-sep">/</span>
        <span className="top-bar-title">통합 관제 대시보드</span>
        <span className="top-bar-sep">·</span>
        <span className="top-bar-clock">{fmtClock(now)}</span>
      </div>

      <div className="top-bar-right">
        {onSplitScreen && (
          <button
            type="button"
            className="top-bar-icon-btn"
            title="3분할 모드 (1번 모니터=지금 화면 그대로, 2·3번 모니터에 CCTV 9개씩)"
            onClick={onSplitScreen}
          >
            ▦
          </button>
        )}
        <button type="button" className="top-bar-icon-btn" title="새로고침" onClick={onRefresh}>
          ⟳
        </button>
        <button
          type="button"
          className="top-bar-icon-btn"
          title={darkMode ? '라이트 모드로 전환' : '다크 모드로 전환'}
          onClick={onToggleDarkMode}
        >
          {darkMode ? '☾' : '☀'}
        </button>
        {onGoAdmin && (
          <button type="button" className="top-bar-icon-btn" title="회원 승인" onClick={onGoAdmin}>
            👤
          </button>
        )}
        {user && (
          <button type="button" className="top-bar-icon-btn" title={`로그아웃 (${user.name})`} onClick={onLogout}>
            ⏻
          </button>
        )}
      </div>
    </header>
  )
}