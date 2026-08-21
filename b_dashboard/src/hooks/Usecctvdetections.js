import { useEffect, useRef, useState } from 'react'
import { Client } from '@stomp/stompjs'
import SockJS from 'sockjs-client'

// 감지 결과가 이 시간(ms) 동안 갱신되지 않으면 화면에서 지운다 - Python이 죽거나
// 연결이 끊겼을 때 마지막 박스가 화면에 얼어붙은 채로 계속 남는 것을 방지한다.
const STALE_TIMEOUT_MS = 2000

/**
 * 특정 camId의 실시간 YOLO/ByteTrack 검출 결과를 구독한다.
 *
 * useEventSocket.js(사건 이벤트, /topic/events)와는 완전히 별개의 채널
 * (/topic/cctv/detections)이다 - 초당 여러 번 오는 "지금 이 순간의 화면 위치"
 * 데이터라서, 영구 저장되는 사건 목록과 같은 곳에 섞이면 안 된다. 같은 STOMP
 * 브로커(/ws)에 새 STOMP 클라이언트로 별도 연결한다 - 이 컴포넌트가 렌더링될
 * 때만 연결되고, 언마운트되면(다른 카메라로 전환 등) 함께 정리된다.
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

    const client = new Client({
      webSocketFactory: () => new SockJS('/ws'),
      reconnectDelay: 3000,
      onConnect: () => {
        client.subscribe('/topic/cctv/detections', (message) => {
          const payload = JSON.parse(message.body)
          if (!payload || payload.camId !== camIdRef.current) return // 다른 카메라 것은 무시

          if (payload.frameWidth && payload.frameHeight) {
            setFrameSize({ width: payload.frameWidth, height: payload.frameHeight })
          }

          const now = Date.now()
          const next = {}
          ;(payload.detections || []).forEach((d) => {
            next[d.trackId] = { bbox: d.bbox, updatedAt: now }
          })
          setTracks(next) // 이번 프레임 것으로 완전히 교체(누적 아님) - Python이 이미 코스팅까지 끝낸 최종 목록이라서
        })
      },
    })

    client.activate()
    return () => client.deactivate()
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