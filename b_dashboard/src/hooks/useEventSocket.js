import { useEffect, useRef, useState } from 'react'
import { Client } from '@stomp/stompjs'
import SockJS from 'sockjs-client'

/**
 * b_gateway의 WebSocket(/ws, STOMP) 채널을 구독하는 훅.
 *
 * 이 훅을 쓰는 컴포넌트는 WebSocket이 뭔지 몰라도 됨 — onEvent 콜백에
 * "새 이벤트 dict 하나"가 들어올 때마다 호출된다는 것만 알면 됨.
 * (팀원 모듈이 POST /api/events로 보낸 이벤트가 저장되면, b_gateway가
 *  자동으로 /topic/events에 방송하고, 그걸 여기서 받는 것뿐)
 */
export function useEventSocket(onEvent) {
  const [connected, setConnected] = useState(false)
  const onEventRef = useRef(onEvent)
  onEventRef.current = onEvent // 매 렌더마다 최신 콜백을 참조하도록 (재연결 없이)

  useEffect(() => {
    const client = new Client({
      webSocketFactory: () => new SockJS('/ws'),
      reconnectDelay: 3000, // 연결 끊기면 3초마다 자동 재시도
      onConnect: () => {
        setConnected(true)
        client.subscribe('/topic/events', (message) => {
          onEventRef.current(JSON.parse(message.body))
        })
      },
      onWebSocketClose: () => setConnected(false),
      onStompError: () => setConnected(false),
    })

    client.activate()
    return () => client.deactivate()
  }, [])

  return connected
}
