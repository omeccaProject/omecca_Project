import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from 'react'
import Hls from 'hls.js'

// UTIC 실시간 HLS(.m3u8) 스트림 재생 전용 <video>.
// Safari는 <video src="...m3u8">만으로 네이티브 재생이 되지만, Chrome/Edge/Firefox는
// hls.js가 붙어야 재생된다 — e_tracking/SmartCCTV/web/map.js의 VideoManager.switchVideo와
// 동일한 방식(카메라 전환/언마운트 시 반드시 hls.js 인스턴스를 destroy 해서 정리한다).

// 정부 실시간 스트림 서버는 종종 특정 연결만 응답 없이 멈춰버린다 — 메인 대시보드 창과
// 분할화면(?view=monitor2) 창은 같은 카메라라도 서로 완전히 독립된 hls.js 연결을 각자
// 새로 맺기 때문에, 한쪽 창은 정상 재생되는데 다른 쪽 창만 "연결 중…" 상태로 멈춰서
// 사실상 검은 화면으로 보이는 문제(예: 사당역)가 실제로 있었다. 아래 타임아웃/재시도
// 로직은 이런 "멈춘 연결"을 자동으로 감지하고 다시 붙여준다.
const LOADING_TIMEOUT_MS = 8000 // 이 시간 안에 재생이 시작 안 되면 멈춘 연결로 보고 재시도
const RETRY_DELAYS_MS = [2000, 4000, 8000, 8000, 8000] // 자동 재시도 간격(마지막 값 반복)
const MAX_AUTO_RETRIES = RETRY_DELAYS_MS.length

// [추가] videoEl 참조를 밖으로 내보낸다 - CctvOverlayCanvas(YOLO bbox 오버레이)가
// 이 <video>의 실제 렌더링 크기(getBoundingClientRect)와 원본 해상도(videoWidth/
// videoHeight)를 읽어서 박스 좌표를 스케일링하는 데 필요하다. forwardRef를 안 쓰던
// 기존 호출부는 ref를 안 넘기므로 전혀 영향받지 않는다(순수 추가).
const LiveHlsVideo = forwardRef(function LiveHlsVideo({ videoUrl, className = '', format = 'HLS' }, forwardedRef) {
  const videoRef = useRef(null)
  const hlsRef = useRef(null)
  useImperativeHandle(forwardedRef, () => videoRef.current, [])
  const timersRef = useRef({ loadingTimeout: null, retryTimeout: null })
  const retryCountRef = useRef(0)
  const [status, setStatus] = useState('loading') // loading | live | error
  const [retryToken, setRetryToken] = useState(0) // 값이 바뀌면 아래 useEffect가 재연결을 시도한다

  function clearTimers() {
    if (timersRef.current.loadingTimeout) clearTimeout(timersRef.current.loadingTimeout)
    if (timersRef.current.retryTimeout) clearTimeout(timersRef.current.retryTimeout)
    timersRef.current.loadingTimeout = null
    timersRef.current.retryTimeout = null
  }

  function scheduleRetry() {
    if (retryCountRef.current >= MAX_AUTO_RETRIES) return // 자동 재시도 한도 초과 - "다시 시도" 버튼만 남김
    const delay = RETRY_DELAYS_MS[Math.min(retryCountRef.current, RETRY_DELAYS_MS.length - 1)]
    retryCountRef.current += 1
    timersRef.current.retryTimeout = setTimeout(() => {
      setRetryToken((t) => t + 1)
    }, delay)
  }

  function handleManualRetry() {
    retryCountRef.current = 0
    setRetryToken((t) => t + 1)
  }

  // 카메라 자체가 바뀌면(다른 camId로 전환) 이전 카메라에서 쌓인 재시도 횟수를 리셋한다.
  useEffect(() => {
    retryCountRef.current = 0
  }, [videoUrl])

  useEffect(() => {
    const videoEl = videoRef.current
    if (!videoEl || !videoUrl) return

    setStatus('loading')
    clearTimers()

    timersRef.current.loadingTimeout = setTimeout(() => {
      setStatus('error')
      scheduleRetry()
    }, LOADING_TIMEOUT_MS)

    function onFatalError() {
      clearTimers()
      setStatus('error')
      scheduleRetry()
    }

    if (format === 'MP4') {
      // 업로드된 동영상 파일(카메라 관리에서 등록). hls.js는 m3u8 매니페스트 전용이라
      // 여기서는 아예 안 타고 <video src>로 네이티브 재생한다. loop를 걸어서 영상이 끝나도
      // 화면상으로는 CCTV처럼 계속 재생되는 것처럼 보이게 한다(실제 탐지 재시작은
      // a_core/camera_watcher.py가 서버 쪽에서 별도로 처리).
      videoEl.loop = true
      videoEl.src = videoUrl
      const onPlaying = () => {
        clearTimers()
        setStatus('live')
      }
      videoEl.addEventListener('playing', onPlaying)
      videoEl.addEventListener('error', onFatalError)
      videoEl.play().catch(() => {})
      return () => {
        videoEl.removeEventListener('playing', onPlaying)
        videoEl.removeEventListener('error', onFatalError)
        clearTimers()
      }
    }

    if (videoEl.canPlayType('application/vnd.apple.mpegurl')) {
      // Safari — hls.js 없이 네이티브 재생
      videoEl.src = videoUrl
      const onPlaying = () => {
        clearTimers()
        setStatus('live')
      }
      videoEl.addEventListener('playing', onPlaying)
      videoEl.addEventListener('error', onFatalError)
      videoEl.play().catch(() => {})
      return () => {
        videoEl.removeEventListener('playing', onPlaying)
        videoEl.removeEventListener('error', onFatalError)
        clearTimers()
      }
    }

    if (!Hls.isSupported()) {
      clearTimers()
      setStatus('error')
      return
    }

    const hls = new Hls()
    hlsRef.current = hls
    hls.on(Hls.Events.ERROR, (_evt, data) => {
      if (data.fatal) onFatalError()
    })
    hls.on(Hls.Events.MANIFEST_PARSED, () => {
      clearTimers()
      setStatus('live')
      videoEl.play().catch(() => {})
    })
    hls.loadSource(videoUrl)
    hls.attachMedia(videoEl)

    return () => {
      clearTimers()
      hls.destroy()
      hlsRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [videoUrl, retryToken, format])

  return (
    <div className={`live-hls-video ${className}`}>
      <video ref={videoRef} muted playsInline autoPlay />
      {status === 'loading' && <div className="live-hls-status">연결 중…</div>}
      {status === 'error' && (
        <div className="live-hls-status live-hls-status-error">
          <span>영상 연결 실패</span>
          <button type="button" className="live-hls-retry-btn" onClick={handleManualRetry}>
            다시 시도
          </button>
        </div>
      )}
    </div>
  )
})

export default LiveHlsVideo
