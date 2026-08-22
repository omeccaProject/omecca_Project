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
 *
 * [추가] onDeleted(payload) - 이벤트가 "삭제"됐을 때 호출된다({ trackId, deletedCount }).
 * -----------------------------------------------------------------------
 * [버그 수정: "새로고침해도 이벤트가 안 사라지는 문제"] 지금까지 이 훅은 "새로 생긴
 * 이벤트"만 알 수 있었고, "지워진 이벤트"는 전혀 알 방법이 없었다. 그래서 Forza DEMO처럼
 * 반복 재생되는 시나리오에서 이전 이벤트가 게이트웨이 DB에서 지워져도, 대시보드는 자기가
 * 페이지 로드 시점에 한 번 GET해 온 옛날 목록을 계속 화면에 들고 있었다 - 그 GET이
 * 삭제보다 먼저 끝났는지 나중에 끝났는지에 따라 결과가 들쭉날쭉했다(타이밍 경쟁).
 * 이제 b_gateway가 삭제할 때 /topic/events/deleted로 직접 방송해주므로, 그 신호를
 * 실시간으로 받아서 화면에서 바로 제거할 수 있다 - 더 이상 GET 타이밍에 의존하지 않는다.
 */
export function useEventSocket(onEvent, onDeleted) {
  const [connected, setConnected] = useState(false)
  const onEventRef = useRef(onEvent)
  const onDeletedRef = useRef(onDeleted)
  onEventRef.current = onEvent // 매 렌더마다 최신 콜백을 참조하도록 (재연결 없이)
  onDeletedRef.current = onDeleted

  useEffect(() => {
    const client = new Client({
      webSocketFactory: () => new SockJS('/ws'),
      reconnectDelay: 3000, // 연결 끊기면 3초마다 자동 재시도
      onConnect: () => {
        setConnected(true)
        client.subscribe('/topic/events', (message) => {
          onEventRef.current(JSON.parse(message.body))
        })
        // [추가] 삭제 신호 구독 - onDeleted가 전달되지 않았으면(다른 화면에서 이 훅을
        // 재사용하는 경우 등) 구독 자체를 생략해서 불필요한 트래픽을 만들지 않는다.
        if (onDeletedRef.current) {
          client.subscribe('/topic/events/deleted', (message) => {
            onDeletedRef.current(JSON.parse(message.body))
          })
        }
      },
      onWebSocketClose: () => setConnected(false),
      onStompError: () => setConnected(false),
    })

    client.activate()
    return () => client.deactivate()
  }, [])

  return connected
}