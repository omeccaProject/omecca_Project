import { useEffect, useRef } from 'react'

/**
 * videoEl(실제 <video> DOM) 위에 절대위치로 겹쳐지는 <canvas>에 YOLO bbox를 그린다.
 *
 * [핵심] <video>가 object-fit:cover라서(App.css `.live-hls-video video`), 화면에
 * 보이는 영상이 원본 비율 그대로가 아니라 잘려서(cover) 표시된다. Python이 보내는
 * bbox는 원본 프레임(frameWidth x frameHeight) 좌표라서, 그대로 그리면 잘린 영역만큼
 * 어긋난다. e_tracking/SmartCCTV/web/map.js의 VideoManager._renderBoxOverlay()가
 * HLS 오버레이에서 이미 쓰고 있는 것과 동일한 계산식을 그대로 재사용한다.
 */
export default function CctvOverlayCanvas({ videoRef, tracks, frameSize }) {
  const canvasRef = useRef(null)
  const rafRef = useRef(null)

  useEffect(() => {
    function draw() {
      rafRef.current = requestAnimationFrame(draw)

      const videoEl = videoRef?.current
      const canvas = canvasRef.current
      if (!videoEl || !canvas || !frameSize) return

      const rect = videoEl.getBoundingClientRect()
      const cssW = rect.width
      const cssH = rect.height
      if (cssW === 0 || cssH === 0) return

      const dpr = window.devicePixelRatio || 1
      const pixelW = Math.round(cssW * dpr)
      const pixelH = Math.round(cssH * dpr)
      if (canvas.width !== pixelW || canvas.height !== pixelH) {
        canvas.width = pixelW
        canvas.height = pixelH
      }

      const ctx = canvas.getContext('2d')
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      ctx.clearRect(0, 0, cssW, cssH)

      // object-fit: cover 기준 스케일/오프셋 계산 (map.js의 _renderBoxOverlay와 동일 로직)
      const videoRatio = frameSize.width / frameSize.height
      const boxRatio = cssW / cssH
      let drawW, drawH, offsetX, offsetY
      if (boxRatio > videoRatio) {
        drawW = cssW
        drawH = cssW / videoRatio
        offsetX = 0
        offsetY = (cssH - drawH) / 2
      } else {
        drawH = cssH
        drawW = cssH * videoRatio
        offsetX = (cssW - drawW) / 2
        offsetY = 0
      }
      const scale = drawW / frameSize.width

      Object.entries(tracks).forEach(([trackId, info]) => {
        const b = info.bbox
        const x = offsetX + b.x1 * scale
        const y = offsetY + b.y1 * scale
        const w = (b.x2 - b.x1) * scale
        const h = (b.y2 - b.y1) * scale

        ctx.lineWidth = 2
        ctx.strokeStyle = '#00ff00' // 요구사항: Python 화면과 동일한 초록색, coasted 여부와 무관하게 항상 초록
        ctx.strokeRect(x, y, w, h)

        ctx.fillStyle = '#00ff00'
        ctx.font = 'bold 13px sans-serif'
        ctx.fillText(`Vehicle #${trackId}`, x, Math.max(y - 6, 12))
      })
    }

    draw()
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [videoRef, tracks, frameSize])

  return (
    <canvas
      ref={canvasRef}
      style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', pointerEvents: 'none' }}
    />
  )
}
