import { useEffect, useRef } from 'react'

const CHANNEL_NAME = 'omecca-dashboard-sync'

// 같은 브라우저에서 창을 여러 개 열어(모니터별로 하나씩) 띄운 경우, 한 창에서
// 이벤트를 선택하면 다른 창에도 "지금 포커스된 이벤트"가 실시간으로 공유된다.
// BroadcastChannel은 같은 브라우저 안에서만 동작한다(다른 PC끼리는 안 됨,
// 그런 경우엔 서버를 거쳐야 하므로 범위 밖으로 남겨둠).
export function useCrossWindowSync(onRemoteFocus) {
  const channelRef = useRef(null)

  useEffect(() => {
    if (typeof BroadcastChannel === 'undefined') return undefined
    const channel = new BroadcastChannel(CHANNEL_NAME)
    channelRef.current = channel
    channel.onmessage = (e) => {
      if (e.data?.type === 'focus') onRemoteFocus(e.data.eventId)
    }
    return () => channel.close()
  }, [onRemoteFocus])

  const broadcastFocus = (eventId) => {
    channelRef.current?.postMessage({ type: 'focus', eventId })
  }

  return { broadcastFocus }
}