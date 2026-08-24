import { useEffect, useState } from 'react'
import { Client } from '@stomp/stompjs'
import SockJS from 'sockjs-client'

// [설계] useCctvDetections.js와 똑같은 이유로 STOMP 클라이언트를 모듈 스코프에 하나만
// 만들어 공유한다 - 지도 화면이 여러 곳에 동시에 떠 있어도(예: 대시보드 미니맵 +
// "지도" 전체화면) 실제 WebSocket 연결은 항상 1개로 고정된다. useCctvDetections.js의
// sharedClient와는 별개의 인스턴스다(구독 topic이 다르므로 함께 묶지 않았다 - 필요하면
// 나중에 하나로 합칠 수 있지만, 지금은 각자 독립적으로 두는 쪽이 두 파일을 서로
// 건드리지 않아 더 안전하다).

let sharedJourneyClient = null
let sharedJourneyRefCount = 0
const journeyListeners = new Set() // Set<(payload) => void> - 구독자가 여러 명이어도 모두에게 같은 이벤트 전달

function ensureSharedJourneyClient() {
  sharedJourneyRefCount += 1
  if (sharedJourneyClient) return sharedJourneyClient

  const client = new Client({
    webSocketFactory: () => new SockJS('/ws'),
    reconnectDelay: 3000,
    onConnect: () => {
      client.subscribe('/topic/cctv/journey', (message) => {
        const payload = JSON.parse(message.body)
        journeyListeners.forEach((fn) => fn(payload))
      })
    },
  })
  client.activate()
  sharedJourneyClient = client
  return client
}

function releaseSharedJourneyClient() {
  sharedJourneyRefCount -= 1
  if (sharedJourneyRefCount > 0) return
  if (sharedJourneyClient) {
    sharedJourneyClient.deactivate()
    sharedJourneyClient = null
  }
}

/**
 * 실시간 "관제용 차량 이동 경로(Journey)"를 구독한다.
 * test_suspicious_driving.py의 VehicleJourney가 카메라 전환을 감지할 때마다
 * VehicleJourneyController(/api/cctv/journey)를 거쳐 이 훅으로 전달된다.
 *
 * 반환값:
 *   active     : 지금 여정이 진행 중인지 (false면 지도에서 마커/Polyline을 지울 것)
 *   currentPos : 차량이 지금 있는 위치 {lat, lng} | null
 *   points     : 지금까지 누적된 전체 경로 [{lat,lng}, ...] - 이 배열 그대로
 *                Leaflet의 L.polyline(points.map(p => [p.lat, p.lng]))에 넣으면
 *                기존 map.js의 RouteManager.trajectoryPolyline과 동일한 결과가 된다.
 */
export function useVehicleJourney() {
  const [journey, setJourney] = useState({ active: false, currentPos: null, currentCamName: null, points: [] })

  useEffect(() => {
    ensureSharedJourneyClient()

    const handlePayload = (payload) => {
      setJourney({
        active: !!payload.active,
        currentPos:
          payload.currentLat != null && payload.currentLng != null
            ? { lat: payload.currentLat, lng: payload.currentLng }
            : null,
        currentCamName: payload.currentCamName || null,
        points: payload.points || [],
      })
    }

    journeyListeners.add(handlePayload)

    return () => {
      journeyListeners.delete(handlePayload)
      releaseSharedJourneyClient()
    }
  }, [])

  return journey
}