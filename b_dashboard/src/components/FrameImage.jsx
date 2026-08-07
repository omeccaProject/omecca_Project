import { useState } from 'react'

// 이벤트 전/후 캡쳐 이미지 하나를 보여준다. 아직 실제 캡쳐 파이프라인이 안 붙은 이벤트(mock 등)는
// 경로가 가짜라 로드가 실패하는데, 그때는 에러 문구로 자연스럽게 대체한다.
export default function FrameImage({ label, url }) {
  const [failed, setFailed] = useState(false)

  return (
    <div className="frame-box">
      <span className="frame-label">{label}</span>
      {!url || failed ? (
        <div className="fallback">
          {!url ? '캡쳐 이미지 없음' : <>이미지 로드 실패<br />{url}</>}
        </div>
      ) : (
        <img src={url} alt={label} onError={() => setFailed(true)} />
      )}
    </div>
  )
}
