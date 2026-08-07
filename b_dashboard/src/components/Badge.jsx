import { EVENT_COLOR, EVENT_LABEL } from '../constants'

export default function Badge({ eventType }) {
  const color = EVENT_COLOR[eventType] || '#888'
  return (
    <span className="badge" style={{ background: `${color}22`, color }}>
      {EVENT_LABEL[eventType] || eventType}
    </span>
  )
}
