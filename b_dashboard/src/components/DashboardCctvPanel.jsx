import { useCallback, useEffect, useState } from 'react'
import { fetchCameras } from '../api'
import LiveHlsVideoWithDetections from './LiveHlsVideoWithDetections'

// 대시보드 오른쪽 패널의 "CCTV" 탭. CctvGrid(여러 칸 그리드)는 380px짜리 좁은 패널에
// 넣기엔 너무 빽빽해지므로, 여기서는 카메라 하나를 크게 보여주고 드롭다운으로 바꾸는
// 방식으로 따로 만든다 - 데이터 소스(카메라 관리에 등록된 목록)는 CctvGrid와 동일하다.
export default function DashboardCctvPanel({ focusedEvent }) {
  const [cameras, setCameras] = useState([])
  const [loading, setLoading] = useState(true)
  const [selectedCamId, setSelectedCamId] = useState(null)

  const load = useCallback(() => {
    fetchCameras()
      .then((list) => setCameras(Array.isArray(list) ? list.filter((c) => c.status === 'ACTIVE' && c.streamUrl) : []))
      .catch(() => setCameras([]))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    load()
    // 카메라 관리에서 새로 등록/수정한 게 바로 반영되도록 짧은 주기로 갱신한다
    // (CctvGrid처럼 실시간 소켓을 새로 만들 정도는 아니라서 폴링으로 충분).
    const timer = setInterval(load, 15000)
    return () => clearInterval(timer)
  }, [load])

  // 방금 클릭한 이벤트의 카메라가 목록에 있으면 그 카메라로 자동 전환 - "이벤트 눌렀다가
  // CCTV 탭으로 넘어가면 그 카메라가 바로 보인다"는 게 자연스러운 흐름이라서.
  useEffect(() => {
    if (!focusedEvent?.camId) return
    if (cameras.some((c) => c.camId === focusedEvent.camId)) {
      setSelectedCamId(focusedEvent.camId)
    }
  }, [focusedEvent, cameras])

  useEffect(() => {
    if (selectedCamId && cameras.some((c) => c.camId === selectedCamId)) return
    setSelectedCamId(cameras[0]?.camId ?? null)
  }, [cameras, selectedCamId])

  const selected = cameras.find((c) => c.camId === selectedCamId) || null

  if (loading) {
    return <div className="control-events-empty">불러오는 중...</div>
  }

  if (cameras.length === 0) {
    return (
      <div className="control-events-empty">
        등록된 CCTV가 없습니다.<br />
        "CCTV" 메뉴의 카메라 관리에서 실시간 URL을 등록하거나 동영상을 업로드하세요.
      </div>
    )
  }

  return (
    <div className="dash-cctv-panel">
      <select
        className="dash-cctv-select"
        value={selectedCamId || ''}
        onChange={(e) => setSelectedCamId(e.target.value)}
      >
        {cameras.map((c) => (
          <option key={c.camId} value={c.camId}>{c.name}</option>
        ))}
      </select>

      {selected && (
        <>
          <div className="dash-cctv-video-wrap">
            <LiveHlsVideoWithDetections camId={selected.camId} videoUrl={selected.streamUrl} format={selected.streamFormat} className="dash-cctv-video" />
          </div>
          <div className="dash-cctv-name">
            {selected.name}
            {selected.debrisDetectionEnabled && <span className="cam-tag-debris">(낙하물)</span>}
          </div>
        </>
      )}
    </div>
  )
}
