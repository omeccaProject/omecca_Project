import Badge from './Badge'
import FrameImage from './FrameImage'

function fmtTime(iso) {
  if (!iso) return '-'
  return iso.replace('T', ' ').split('.')[0]
}

export default function Viewer({ event }) {
  if (!event) {
    return (
      <section className="panel">
        <h2>영상 뷰어 · 화면 전환</h2>
        <div className="viewer-empty">이벤트를 선택하면 해당 CCTV로 화면이 전환됩니다.</div>
      </section>
    )
  }

  return (
    <section className="panel">
      <h2>영상 뷰어 · 화면 전환</h2>
      <div className="viewer-head">
        <div className="cam">{event.camId}</div>
        <Badge eventType={event.eventType} />
      </div>

      <div className="frames">
        <FrameImage label="BEFORE" url={event.frameRefBefore} />
        <FrameImage label="AFTER" url={event.frameRefAfter} />
      </div>

      <div className="meta-grid">
        <div><span>발생 시각</span><br />{fmtTime(event.occurredAt)}</div>
        <div><span>추적 ID</span><br />{event.trackId || '-'}</div>
        <div><span>신뢰도</span><br />{event.confidence != null ? `${(event.confidence * 100).toFixed(1)}%` : '-'}</div>
        <div><span>번호판</span><br />{event.meta?.plateNumber || '-'}</div>
        <div><span>위치</span><br />{event.location ? `${event.location.lat.toFixed(4)}, ${event.location.lng.toFixed(4)}` : '-'}</div>
        <div><span>관심대상 여부</span><br />{event.isRegisteredTarget ? `예 (targetId ${event.targetId})` : '아니오'}</div>
      </div>
    </section>
  )
}
