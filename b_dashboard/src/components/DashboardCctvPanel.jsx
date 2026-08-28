import { useCallback, useEffect, useRef, useState } from 'react'
import { fetchCameras } from '../api'
import LiveHlsVideoWithDetections from './LiveHlsVideoWithDetections'

export default function DashboardCctvPanel({ requestedCamId }) {
  const [cameras, setCameras] = useState([])
  const [loading, setLoading] = useState(true)
  const [selectedCamId, setSelectedCamId] = useState(null)

  // 지도에서 전달된 requestedCamId를 마지막으로 적용한 값
  const lastAppliedRequestedCamId = useRef(null)

  // =========================================================
  // CCTV 목록 조회
  // =========================================================
  const load = useCallback(() => {
    fetchCameras()
      .then((list) => {
        setCameras(
          Array.isArray(list)
            ? list.filter(
                (c) => c.status === 'ACTIVE' && c.streamUrl
              )
            : []
        )
      })
      .catch((error) => {
        console.error('[CCTV] 카메라 목록 조회 실패:', error)
        setCameras([])
      })
      .finally(() => {
        setLoading(false)
      })
  }, [])

  // 최초 로딩 + 15초마다 카메라 목록 갱신
  useEffect(() => {
    load()

    const timer = setInterval(load, 15000)

    return () => clearInterval(timer)
  }, [load])

  // =========================================================
  // 지도에서 전달된 requestedCamId 처리
  //
  // 지도 카메라 아이콘 클릭
  //        ↓
  // map.js
  //        ↓
  // MainDashboard
  //        ↓
  // requestedCamId
  //        ↓
  // 해당 CCTV 선택
  //
  // 같은 requestedCamId가 cameras 갱신 때문에
  // 반복 적용되지 않도록 마지막 적용값을 기억한다.
  // =========================================================
  useEffect(() => {
    if (!requestedCamId) {
      return
    }

    // 이미 처리한 동일 요청이면 다시 처리하지 않는다.
    if (
      lastAppliedRequestedCamId.current === requestedCamId
    ) {
      return
    }

    const targetCamera = cameras.find(
      (camera) => camera.camId === requestedCamId
    )

    if (!targetCamera) {
      return
    }

    console.log(
      '[CCTV] 지도에서 CCTV 선택:',
      targetCamera.name,
      targetCamera.camId
    )

    setSelectedCamId(targetCamera.camId)

    // 요청 처리 완료
    lastAppliedRequestedCamId.current = requestedCamId
  }, [requestedCamId, cameras])

  // =========================================================
  // 지도 iframe에서 직접 cctv:select 메시지를 받는 경우
  // =========================================================
  useEffect(() => {
    const handleJourneyCctvMessage = (event) => {
      // 지도 서버에서 온 메시지만 처리
      if (event.origin !== 'http://localhost:4000') {
        return
      }

      if (event.data?.type !== 'cctv:select') {
        return
      }

      const camId = event.data?.camId

      if (!camId) {
        return
      }

      const targetCamera = cameras.find(
        (camera) => camera.camId === camId
      )

      if (!targetCamera) {
        console.warn(
          '[CCTV] 지도에서 요청한 CCTV를 현재 목록에서 찾을 수 없습니다:',
          camId
        )
        return
      }

      console.log(
        '[CCTV] 지도 CCTV 전환:',
        targetCamera.name,
        targetCamera.camId
      )

      setSelectedCamId(targetCamera.camId)

      // 동일한 지도 요청이 다시 적용되지 않도록 기록
      lastAppliedRequestedCamId.current = camId
    }

    window.addEventListener(
      'message',
      handleJourneyCctvMessage
    )

    return () => {
      window.removeEventListener(
        'message',
        handleJourneyCctvMessage
      )
    }
  }, [cameras])

  // =========================================================
  // CCTV 기본 선택 및 선택 상태 유지
  //
  // 최초 진입:
  //   이수역
  //
  // 사용자가 CCTV 선택:
  //   선택한 CCTV 유지
  //
  // 15초 후 cameras 갱신:
  //   기존 선택 CCTV가 존재하면 그대로 유지
  //
  // 선택한 CCTV가 목록에서 사라진 경우:
  //   이수역 → 없으면 첫 번째 CCTV
  // =========================================================
  useEffect(() => {
    if (cameras.length === 0) {
      return
    }

    // 현재 선택한 CCTV가 아직 목록에 존재하면
    // 다른 CCTV로 바꾸지 않는다.
    if (
      selectedCamId &&
      cameras.some(
        (camera) => camera.camId === selectedCamId
      )
    ) {
      return
    }

    // 현재 선택값이 없거나
    // 선택했던 CCTV가 목록에서 사라진 경우
    // 이수역을 기본 CCTV로 사용
    const defaultCamera = cameras.find(
      (camera) => camera.name === '이수역'
    )

    const fallbackCamId =
      defaultCamera?.camId ??
      cameras[0]?.camId ??
      null

    console.log(
      '[CCTV] 기본 CCTV 선택:',
      defaultCamera?.name ??
        cameras[0]?.name ??
        '없음',
      fallbackCamId
    )

    setSelectedCamId(fallbackCamId)
  }, [cameras, selectedCamId])

  // =========================================================
  // 현재 선택된 CCTV
  // =========================================================
  const selected =
    cameras.find(
      (camera) => camera.camId === selectedCamId
    ) || null

  // =========================================================
  // 로딩
  // =========================================================
  if (loading) {
    return (
      <div className="control-events-empty">
        불러오는 중...
      </div>
    )
  }

  // =========================================================
  // CCTV 없음
  // =========================================================
  if (cameras.length === 0) {
    return (
      <div className="control-events-empty">
        등록된 CCTV가 없습니다.
        <br />
        "CCTV" 메뉴의 카메라 관리에서 실시간 URL을 등록하거나
        동영상을 업로드하세요.
      </div>
    )
  }

  // =========================================================
  // CCTV 화면
  // =========================================================
  return (
    <div className="dash-cctv-panel">
      <select
        className="dash-cctv-select"
        value={selectedCamId || ''}
        onChange={(event) => {
          const camId = event.target.value

          console.log(
            '[CCTV] 사용자가 CCTV 선택:',
            camId
          )

          // 사용자가 직접 선택한 CCTV
          setSelectedCamId(camId)
        }}
      >
        {cameras.map((camera) => (
          <option
            key={camera.camId}
            value={camera.camId}
          >
            {camera.name}
          </option>
        ))}
      </select>

      {selected && (
        <>
          <div className="dash-cctv-video-wrap">
            <LiveHlsVideoWithDetections
              camId={selected.camId}
              videoUrl={selected.streamUrl}
              format={selected.streamFormat}
              className="dash-cctv-video"
            />
          </div>

          <div className="dash-cctv-name">
            {selected.name}

            {selected.debrisDetectionEnabled && (
              <span className="cam-tag-debris">
                (낙하물)
              </span>
            )}
          </div>
        </>
      )}
    </div>
  )
}