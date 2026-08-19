import { useCallback, useEffect, useState } from 'react'
import { EVENT_LABEL } from '../constants'
import { REAL_CAMERAS as FALLBACK_REAL_CAMERAS } from '../realCameras'
import { fetchCameras } from '../api'
import Badge from './Badge'
import FrameImage from './FrameImage'
import LiveHlsVideo from './LiveHlsVideo'
import CameraManagerModal from './CameraManagerModal'

// 아직 이벤트가 안 들어온 카메라도 그리드에 자리를 채워두기 위한 기본 목록.
// 실제 카메라 목록 API가 생기면 이 상수 대신 그걸 쓰면 됨. 3분할 모드(모니터
// 2/3에 9개씩, 총 18개)까지 커버해야 하므로 18개까지 준비해둠.
const FALLBACK_CAMS = [
  'CAM-01', 'CAM-02', 'CAM-03', 'CAM-04', 'CAM-05', 'CAM-06',
  'CAM-07', 'CAM-08', 'CAM-09', 'CAM-10', 'CAM-11', 'CAM-12',
  'CAM-13', 'CAM-14', 'CAM-15', 'CAM-16', 'CAM-17', 'CAM-18',
]

const CAM_COUNT_OPTIONS = [6, 9]
const CAM_COUNT_STORAGE_KEY = 'omecca_cctv_cam_count'

function fmtTime(iso) {
  if (!iso) return '-'
  return iso.replace('T', ' ').split('.')[0]
}

// camOffset: 카메라 목록에서 몇 번째부터 보여줄지 (3분할 모드에서 모니터2=0, 모니터3=9로
//            넘겨서 두 창이 서로 겹치지 않는 9개씩을 나눠 보여준다).
// fixedCount: 지정되면 6/9 토글 UI를 숨기고 이 개수로 고정한다 (3분할 모드는 항상 9개 고정,
//             화면을 꽉 채워서 보여준다 - App.css의 .kiosk-cctv-fill 참고).
export default function CctvGrid({ events, focusedEvent, onSelectCam, camOffset = 0, fixedCount = null }) {
  // 화면에 몇 개 카메라를 보여줄지(6 또는 9). localStorage에 저장해서
  // 3분할 모니터의 CCTV 창을 새로고침해도 마지막에 고른 개수가 유지되게 함.
  const [camCount, setCamCount] = useState(() => {
    if (fixedCount) return fixedCount
    const saved = Number(localStorage.getItem(CAM_COUNT_STORAGE_KEY))
    return CAM_COUNT_OPTIONS.includes(saved) ? saved : 6
  })

  // 클릭해서 확대한 카메라 ID. null이면 확대 화면 없음.
  const [zoomedCamId, setZoomedCamId] = useState(null)

  // 카메라 마스터 데이터 관리 모달. 3분할 모드(fixedCount)에서는 안 띄운다(운영 화면이라).
  const [showCameraManager, setShowCameraManager] = useState(false)

  // 실시간 영상이 연결된 카메라 목록. 이제 하드코딩된 realCameras.js가 아니라
  // "카메라 관리"에서 등록한 DB(camera 테이블) 데이터를 직접 불러온다 — 등록 즉시
  // 그리드뷰어에 반영되게 하기 위함. /api/cameras가 아직 없거나(마이그레이션 전) 응답이
  // 비어있으면 realCameras.js를 폴백으로 써서 화면이 깨지지 않게 한다.
  const [liveCameras, setLiveCameras] = useState(FALLBACK_REAL_CAMERAS)

  // "카메라 관리" API가 실제로 응답해서 진짜 등록된 카메라 목록을 알려준 적이 있다면,
  // 그 camId들을 처음 등장한 순서 그대로 여기 누적 보관한다. camIds 그리드 계산에서
  // 이 목록을 맨 앞에 고정해두면, 카메라를 삭제해도 그 칸의 "자리"는 그대로 유지되고
  // (realCameraById에 더 이상 없으니 idle로만 바뀜) 뒤에 있던 다른 카메라가 그 자리로
  // 당겨져 들어오는 현상(reflow)이 없어진다.
  // 주의: 초기값/폴백값(FALLBACK_REAL_CAMERAS)은 절대 여기 섞지 않는다 - 섞으면 아직 API가
  // 응답하기 전의 임시 목록이 "진짜 등록된 카메라"보다 먼저 자리를 선점해버려서, 실제로
  // 등록·활성화된 카메라가 뒤로 밀려나 그리드 화면 밖으로 벗어나는 회귀가 생긴다.
  const [knownCamIds, setKnownCamIds] = useState([])

  const loadLiveCameras = useCallback(() => {
    fetchCameras()
      .then((list) => {
        const withStream = (Array.isArray(list) ? list : [])
          .filter((c) => c.status === 'ACTIVE' && c.streamUrl)
          .map((c) => ({ camId: c.camId, name: c.name, videoUrl: c.streamUrl }))
        setLiveCameras(withStream.length > 0 ? withStream : FALLBACK_REAL_CAMERAS)

        // API가 실제로 응답했을 때만(설령 withStream이 아직 비어있더라도) 그 결과를
        // knownCamIds에 반영한다 - 폴백 목록은 절대 반영하지 않는다.
        setKnownCamIds((prev) => {
          const currentRealIds = withStream.map((c) => c.camId)
          const existing = new Set(prev)
          const appended = currentRealIds.filter((id) => !existing.has(id))
          return appended.length ? [...prev, ...appended] : prev
        })
      })
      .catch(() => {
        // API 자체가 아직 없거나(구버전 서버) 실패하면 기존 하드코딩 목록을 그대로 유지.
        // knownCamIds는 건드리지 않는다 - 아직 뭐가 진짜 등록된 카메라인지 알 수 없으므로.
        setLiveCameras(FALLBACK_REAL_CAMERAS)
      })
  }, [])

  useEffect(() => {
    loadLiveCameras()
  }, [loadLiveCameras])

  useEffect(() => {
    if (fixedCount) return // 3분할 모드는 항상 9개 고정이므로 저장/동기화할 필요가 없다
    localStorage.setItem(CAM_COUNT_STORAGE_KEY, String(camCount))
  }, [camCount, fixedCount])

  // 다른 모니터(다른 창)에서 카메라 개수를 바꾸면 이 창도 같이 맞춘다 (localStorage는 같은 origin 창끼리 공유됨).
  useEffect(() => {
    if (fixedCount) return
    function onStorage(e) {
      if (e.key !== CAM_COUNT_STORAGE_KEY) return
      const next = Number(e.newValue)
      if (CAM_COUNT_OPTIONS.includes(next)) setCamCount(next)
    }
    window.addEventListener('storage', onStorage)
    return () => window.removeEventListener('storage', onStorage)
  }, [fixedCount])

  // ESC로 확대 화면 닫기
  useEffect(() => {
    function onKeyDown(e) {
      if (e.key === 'Escape') setZoomedCamId(null)
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])

  const effectiveCount = fixedCount || camCount
  const seenCams = [...new Set(events.map((ev) => ev.camId).filter(Boolean))]
  // 실제로 실시간 영상이 연결된 카메라(liveCameras, DB "카메라 관리"에서 등록된 것)는
  // 항상 그리드 맨 앞에 고정 노출한다.
  const realCameraById = Object.fromEntries(liveCameras.map((c) => [c.camId, c]))
  // knownCamIds(진짜 등록된 적 있는 카메라, 순서 고정)를 맨 앞에 둬서 삭제 시 뒤 카메라가
  // 앞으로 당겨지지 않게 하고, 그 다음 liveCameras의 현재 camId(API 응답 전/실패 시의
  // 폴백 목록을 화면에 그대로 보여주기 위함 - knownCamIds가 비어있는 그 순간에도 화면이
  // 안 깨지게), seenCams, FALLBACK_CAMS 순서로 채운다.
  const camIds = [...new Set([
    ...knownCamIds,
    ...liveCameras.map((c) => c.camId),
    ...seenCams,
    ...FALLBACK_CAMS,
  ])].slice(camOffset, camOffset + effectiveCount)

  const latestByCam = {}
  events.forEach((ev) => {
    const prev = latestByCam[ev.camId]
    if (!prev || new Date(ev.occurredAt) > new Date(prev.occurredAt)) {
      latestByCam[ev.camId] = ev
    }
  })

  function handleCellClick(camId) {
    const latest = latestByCam[camId]
    if (latest) onSelectCam(latest) // 기존 동작 유지: 이벤트가 있으면 다른 모니터 창에도 포커스 전파
    setZoomedCamId(camId) // 확대는 이벤트 유무와 상관없이 항상 가능
  }

  const zoomedLatest = zoomedCamId ? latestByCam[zoomedCamId] : null

  return (
    <section className="panel cctv-panel">
      <div className="cctv-panel-head">
        <h2>CCTV 그리드 뷰어{fixedCount ? ` (${camOffset + 1}~${camOffset + effectiveCount})` : ''}</h2>
        {!fixedCount && (
          <div className="cctv-panel-head-right">
            <button type="button" className="cam-manage-btn" onClick={() => setShowCameraManager(true)}>
              카메라 관리
            </button>
            <div className="cam-count-toggle">
              {CAM_COUNT_OPTIONS.map((n) => (
                <button
                  key={n}
                  className={camCount === n ? 'active' : ''}
                  onClick={() => setCamCount(n)}
                >
                  {n}개
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className={`cctv-grid cctv-grid-${effectiveCount}`}>
        {camIds.map((camId) => {
          const latest = latestByCam[camId]
          const isFocused = focusedEvent?.camId === camId
          const realCam = realCameraById[camId]

          return (
            <div
              key={camId}
              className={`cctv-cell ${isFocused ? 'active' : ''} ${latest ? '' : 'idle'} ${realCam ? 'cctv-cell-live' : ''}`}
              onClick={() => handleCellClick(camId)}
            >
              {isFocused && focusedEvent ? (
                <div className="cctv-cell-detail">
                  <div className="frames-mini">
                    {focusedEvent.frameRefBefore && <img src={focusedEvent.frameRefBefore} alt="before" />}
                    {focusedEvent.frameRefAfter && <img src={focusedEvent.frameRefAfter} alt="after" />}
                  </div>
                  <div className="cctv-cell-foot">
                    <Badge eventType={focusedEvent.eventType} />
                    <span className="cctv-cell-cam">{camId}</span>
                  </div>
                </div>
              ) : realCam ? (
                <div className="cctv-cell-live-wrap">
                  <LiveHlsVideo videoUrl={realCam.videoUrl} className="cctv-cell-live-video" />
                  <div className="cctv-cell-foot cctv-cell-foot-live">
                    <span className="cctv-cell-live-dot" />
                    <span className="cctv-cell-cam">{realCam.name}</span>
                  </div>
                </div>
              ) : (
                <div className="cctv-cell-idle">
                  <span className="cctv-cell-cam">{camId}</span>
                  {latest ? (
                    <span className="cctv-cell-sub">
                      {EVENT_LABEL[latest.eventType] || latest.eventType} · {fmtTime(latest.occurredAt)}
                    </span>
                  ) : (
                    <span className="cctv-cell-sub">신호 대기 중</span>
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>

      {zoomedCamId && (() => {
        const zoomedRealCam = realCameraById[zoomedCamId]
        return (
        <div className="cctv-zoom-overlay" onClick={() => setZoomedCamId(null)}>
          <div className="cctv-zoom-box" onClick={(e) => e.stopPropagation()}>
            <div className="cctv-zoom-head">
              <span className="cctv-zoom-cam">{zoomedRealCam ? zoomedRealCam.name : zoomedCamId}</span>
              {zoomedLatest && <Badge eventType={zoomedLatest.eventType} />}
              <button className="cctv-zoom-close" onClick={() => setZoomedCamId(null)}>닫기 ✕</button>
            </div>

            {zoomedLatest ? (
              <>
                <div className="frames-zoom">
                  <FrameImage label="이전" url={zoomedLatest.frameRefBefore} />
                  <FrameImage label="이후" url={zoomedLatest.frameRefAfter} />
                </div>
                <div className="cctv-zoom-meta">
                  {EVENT_LABEL[zoomedLatest.eventType] || zoomedLatest.eventType} · {fmtTime(zoomedLatest.occurredAt)}
                </div>
              </>
            ) : zoomedRealCam ? (
              <LiveHlsVideo videoUrl={zoomedRealCam.videoUrl} className="cctv-zoom-live-video" />
            ) : (
              <div className="cctv-zoom-empty">신호 대기 중 — 아직 감지된 이벤트가 없습니다</div>
            )}
          </div>
        </div>
        )
      })()}

      {showCameraManager && (
        <CameraManagerModal
          onClose={() => setShowCameraManager(false)}
          onChanged={loadLiveCameras}
        />
      )}
    </section>
  )
}