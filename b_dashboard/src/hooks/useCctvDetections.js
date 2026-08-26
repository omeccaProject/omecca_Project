import { useEffect, useRef, useState } from 'react'
import { Client } from '@stomp/stompjs'
import SockJS from 'sockjs-client'

// 감지 결과가 이 시간(ms) 동안 갱신되지 않으면 화면에서 지운다 - Python이 죽거나
// 연결이 끊겼을 때 마지막 박스가 화면에 얼어붙은 채로 계속 남는 것을 방지한다.
const STALE_TIMEOUT_MS = 2000

// [버그 수정: "CCTV 그리드에서 박스가 안 뜸 / vite ws proxy error: ECONNRESET·EPIPE"]
// 예전에는 이 훅이 호출될 때마다(=카메라 그리드 셀 하나당 하나씩, 9분할이면 9번)
// 매번 새 SockJS+STOMP 커넥션을 따로 만들었다. 즉 그리드를 9개로 보고 있으면
// "/ws"로 가는 raw WebSocket이 동시에 9개(+대시보드 이벤트용 useEventSocket까지
// 합치면 10개)가 열렸는데, 개발 모드(vite dev server)의 프록시가 이렇게 많은
// WebSocket 업그레이드/재연결을 동시에 감당하지 못해 계속 끊기고(ECONNRESET),
// 끊긴 소켓에 STOMP가 하트비트를 쓰려다 EPIPE가 나는 상황이 반복됐다.
//
// 카메라가 몇 개 보이든 "/topic/cctv/detections" 구독은 논리적으로 하나면 충분하다
// (서버가 보내는 매 프레임 페이로드에 camId가 이미 들어있어서, 클라이언트에서
// camId별로 나눠주기만 하면 됨) - 그래서 STOMP 클라이언트를 모듈 스코프에 하나만
// 만들어 모든 그리드 셀이 공유하고, 각 훅은 그 위에 자기 camId용 리스너만 등록한다.
// 화면에 카메라가 몇 개든 실제 WebSocket 연결은 항상 1개로 고정된다.

let sharedClient = null
let sharedRefCount = 0
const listenersByCamId = new Map() // camId -> Set<(payload) => void>

function ensureSharedClient() {
  sharedRefCount += 1
  if (sharedClient) return sharedClient

  const client = new Client({
    webSocketFactory: () => new SockJS('/ws'),
    reconnectDelay: 3000,
    onConnect: () => {
      client.subscribe('/topic/cctv/detections', (message) => {
        const payload = JSON.parse(message.body)
        if (!payload || !payload.camId) return
        const listeners = listenersByCamId.get(payload.camId)
        if (!listeners) return // 지금 화면에 없는 카메라 것 - 조용히 무시
        listeners.forEach((fn) => fn(payload))
      })
    },
  })
  client.activate()
  sharedClient = client
  return client
}

function releaseSharedClient() {
  sharedRefCount -= 1
  if (sharedRefCount > 0) return
  // 마지막 사용처가 언마운트되면(예: CCTV 화면을 완전히 벗어남) 연결도 같이 정리한다.
  if (sharedClient) {
    sharedClient.deactivate()
    sharedClient = null
  }
}

/**
 * 특정 camId의 실시간 YOLO/ByteTrack 검출 결과를 구독한다.
 *
 * useEventSocket.js(사건 이벤트, /topic/events)와는 완전히 별개의 채널
 * (/topic/cctv/detections)이다 - 초당 여러 번 오는 "지금 이 순간의 화면 위치"
 * 데이터라서, 영구 저장되는 사건 목록과 같은 곳에 섞이면 안 된다. 다만 실제
 * WebSocket 연결 자체는 위 sharedClient 하나를 그리드의 모든 카메라가 함께 쓴다
 * (연결 개수가 화면에 보이는 카메라 수와 무관하게 항상 1개).
 *
 * camId가 없거나(아직 카메라 미확정) 서버가 그 camId로 아무것도 안 보내면
 * frameSize/tracks는 그냥 빈 상태로 유지된다 - 아무 영향 없음(안전).
 */
export function useCctvDetections(camId) {
  const [tracks, setTracks] = useState({}) // { [trackId]: {bbox:{x1,y1,x2,y2}, updatedAt} }
  const [frameSize, setFrameSize] = useState(null) // { width, height } - Python 원본 프레임 해상도
  const camIdRef = useRef(camId)
  camIdRef.current = camId

  useEffect(() => {
    if (!camId) return undefined

    ensureSharedClient()

    const handlePayload = (payload) => {
      if (payload.frameWidth && payload.frameHeight) {
        setFrameSize({ width: payload.frameWidth, height: payload.frameHeight })
      }
      const now = Date.now()
      const next = {}
      ;(payload.detections || []).forEach((d) => {
        // [신규] d.alert(음주운전/지그재그 의심 확정 여부)도 같이 넘겨야
        // CctvOverlayCanvas.jsx가 빨간 박스로 그릴 수 있다 - 예전엔 bbox만
        // 넘기고 alert는 버려서, Python/컨트롤러가 다 고쳐져도 화면은 계속 초록색이었다.
        next[d.trackId] = { bbox: d.bbox, alert: d.alert, updatedAt: now }
      })
      setTracks(next) // 이번 프레임 것으로 완전히 교체(누적 아님) - Python이 이미 코스팅까지 끝낸 최종 목록이라서
    }

    let listeners = listenersByCamId.get(camId)
    if (!listeners) {
      listeners = new Set()
      listenersByCamId.set(camId, listeners)
    }
    listeners.add(handlePayload)

    return () => {
      listeners.delete(handlePayload)
      if (listeners.size === 0) listenersByCamId.delete(camId)
      releaseSharedClient()
    }
  }, [camId])

  // 일정 시간 갱신이 없으면(연결 끊김 등) 화면에서 전부 지운다.
  useEffect(() => {
    const timer = setInterval(() => {
      setTracks((prev) => {
        const now = Date.now()
        const stale = Object.values(prev).some((t) => now - t.updatedAt > STALE_TIMEOUT_MS)
        return stale ? {} : prev
      })
    }, 1000)
    return () => clearInterval(timer)
  }, [])

  return { tracks, frameSize }
}
