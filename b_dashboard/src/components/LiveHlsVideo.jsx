import { useEffect, useRef, useState } from 'react'
import Hls from 'hls.js'

// UTIC 실시간 HLS(.m3u8) 스트림 재생 전용 <video>.
// Safari는 <video src="...m3u8">만으로 네이티브 재생이 되지만, Chrome/Edge/Firefox는
// hls.js가 붙어야 재생된다 — e_tracking/SmartCCTV/web/map.js의 VideoManager.switchVideo와
// 동일한 방식(카메라 전환/언마운트 시 반드시 hls.js 인스턴스를 destroy 해서 정리한다).
export default function LiveHlsVideo({ videoUrl, className = '' }) {
  const videoRef = useRef(null)
  const hlsRef = useRef(null)
  const [status, setStatus] = useState('loading') // loading | live | error

  useEffect(() => {
    const videoEl = videoRef.current
    if (!videoEl || !videoUrl) return

    setStatus('loading')

    if (videoEl.canPlayType('application/vnd.apple.mpegurl')) {
      // Safari — hls.js 없이 네이티브 재생
      videoEl.src = videoUrl
      const onPlaying = () => setStatus('live')
      const onError = () => setStatus('error')
      videoEl.addEventListener('playing', onPlaying)
      videoEl.addEventListener('error', onError)
      videoEl.play().catch(() => {})
      return () => {
        videoEl.removeEventListener('playing', onPlaying)
        videoEl.removeEventListener('error', onError)
      }
    }

    if (!Hls.isSupported()) {
      setStatus('error')
      return
    }

    const hls = new Hls()
    hlsRef.current = hls
    hls.on(Hls.Events.ERROR, (_evt, data) => {
      if (data.fatal) setStatus('error')
    })
    hls.on(Hls.Events.MANIFEST_PARSED, () => {
      setStatus('live')
      videoEl.play().catch(() => {})
    })
    hls.loadSource(videoUrl)
    hls.attachMedia(videoEl)

    return () => {
      hls.destroy()
      hlsRef.current = null
    }
  }, [videoUrl])

  return (
    <div className={`live-hls-video ${className}`}>
      <video ref={videoRef} muted playsInline autoPlay />
      {status === 'loading' && <div className="live-hls-status">연결 중…</div>}
      {status === 'error' && <div className="live-hls-status live-hls-status-error">영상 연결 실패</div>}
    </div>
  )
}
