import { EVENT_LABEL } from '../constants'
import Badge from './Badge'

// 아직 이벤트가 안 들어온 카메라도 그리드에 자리를 채워두기 위한 기본 목록.
// 실제 카메라 목록 API가 생기면 이 상수 대신 그걸 쓰면 됨.
const FALLBACK_CAMS = ['CAM-01', 'CAM-02', 'CAM-03', 'CAM-04', 'CAM-05', 'CAM-06']

function fmtTime(iso) {
  if (!iso) return '-'
  return iso.replace('T', ' ').split('.')[0]
}

export default function CctvGrid({ events, focusedEvent, onSelectCam }) {
  // 최근 이벤트가 있었던 카메라를 우선 채우고, 남는 칸은 기본 목록으로 채움 (최대 6칸, 2x3)
  const seenCams = [...new Set(events.map((ev) => ev.camId).filter(Boolean))]
  const camIds = [...new Set([...seenCams, ...FALLBACK_CAMS])].slice(0, 6)

  const latestByCam = {}
  events.forEach((ev) => {
    const prev = latestByCam[ev.camId]
    if (!prev || new Date(ev.occurredAt) > new Date(prev.occurredAt)) {
      latestByCam[ev.camId] = ev
    }
  })

  return (
    <section className="panel">
      <h2>CCTV 그리드 뷰어</h2>
      <div className="cctv-grid">
        {camIds.map((camId) => {
          const latest = latestByCam[camId]
          const isFocused = focusedEvent?.camId === camId

          return (
            <div
              key={camId}
              className={`cctv-cell ${isFocused ? 'active' : ''} ${latest ? '' : 'idle'}`}
              onClick={() => latest && onSelectCam(latest)}
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
    </section>
  )
}