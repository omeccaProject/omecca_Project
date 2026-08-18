import { useEffect, useState } from 'react'
import { EVENT_LABEL } from '../constants'
import Badge from './Badge'
import FrameImage from './FrameImage'

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
  const camIds = [...new Set([...seenCams, ...FALLBACK_CAMS])].slice(camOffset, camOffset + effectiveCount)

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
        )}
      </div>

      <div className={`cctv-grid cctv-grid-${effectiveCount}`}>
        {camIds.map((camId) => {
          const latest = latestByCam[camId]
          const isFocused = focusedEvent?.camId === camId

          return (
            <div
              key={camId}
              className={`cctv-cell ${isFocused ? 'active' : ''} ${latest ? '' : 'idle'}`}
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

      {zoomedCamId && (
        <div className="cctv-zoom-overlay" onClick={() => setZoomedCamId(null)}>
          <div className="cctv-zoom-box" onClick={(e) => e.stopPropagation()}>
            <div className="cctv-zoom-head">
              <span className="cctv-zoom-cam">{zoomedCamId}</span>
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
            ) : (
              <div className="cctv-zoom-empty">신호 대기 중 — 아직 감지된 이벤트가 없습니다</div>
            )}
          </div>
        </div>
      )}
    </section>
  )
}