import { useEffect, useRef } from 'react'

/**
 * videoEl(실제 <video> DOM) 위에 절대위치로 겹쳐지는 <canvas>에 YOLO bbox를 그린다.
 *
 * [핵심] <video>가 object-fit:cover라서(App.css `.live-hls-video video`), 화면에
 * 보이는 영상이 원본 비율 그대로가 아니라 잘려서(cover) 표시된다. Python이 보내는
 * bbox는 원본 프레임(frameWidth x frameHeight) 좌표라서, 그대로 그리면 잘린 영역만큼
 * 어긋난다. e_tracking/SmartCCTV/web/map.js의 VideoManager._renderBoxOverlay()가
 * HLS 오버레이에서 이미 쓰고 있는 것과 동일한 계산식을 그대로 재사용한다.
 *
 * [수정: 관제 UI 개선] 기존 "Vehicle #ID" / "SUSPICIOUS" 텍스트만 있던 이상운전
 * 차량 표시를, test_suspicious_driving.py의 Python 화면 UI(Glow/모서리강조/한글
 * 텍스트)와 같은 느낌으로 바꿨다. 데이터 흐름(useCctvDetections.js, tracks/frameSize
 * props, canvas 크기 계산, object-fit:cover 스케일 계산, requestAnimationFrame
 * 루프 구조)은 전혀 건드리지 않았다 - Object.entries(tracks).forEach(...) 안에서
 * 그리는 내용만 바꿨다.
 *
 * [번호판] tracks의 각 항목(info)에 실제 LPR 결과가 있다면 info.plate를 그대로
 * 쓴다 - 지금은 useCctvDetections.js/Python이 이 필드를 보내주지 않으므로
 * info.plate는 항상 undefined이고, 그 경우 절대 번호를 지어내지 않고
 * PLATE_UNKNOWN_LABEL("차량번호 확인 중")을 그대로 표시한다. 나중에 파이프라인에
 * plate 필드가 추가되면 코드 수정 없이 자동으로 실제 번호가 표시된다.
 */

const PLATE_UNKNOWN_LABEL = '차량번호 확인 중'

// Canvas 2D의 fillText/font는 브라우저 시스템 폰트를 그대로 쓰므로(파이썬의
// cv2.putText와 달리 한글 렌더링에 별도 우회가 필요 없음) 한글이 있는 폰트를
// 우선순위로 지정해두기만 하면 된다.
const KOREAN_FONT_STACK = '"Malgun Gothic", "Apple SD Gothic Neo", "Noto Sans KR", sans-serif'

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

      // object-fit: cover 기준 스케일/오프셋 계산 (map.js의 _renderBoxOverlay와 동일 로직) - 변경 없음
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

      // [신규] 이상운전 차량의 Glow/Corner Accent가 은은하게 Pulse 되도록, 이번
      // 프레임에서 공용으로 쓸 위상값을 한 번만 계산한다(test_suspicious_driving.py의
      // pulse_phase와 같은 목적) - 과하지 않게 아주 약한 진폭만 준다.
      const pulsePhase = performance.now() / 500 // 프레임마다 값이 계속 흐름(Date.now()류의 잦은 GC 없이 가벼움)

      Object.entries(tracks).forEach(([trackId, info]) => {
        const b = info.bbox
        const x = offsetX + b.x1 * scale
        const y = offsetY + b.y1 * scale
        const w = (b.x2 - b.x1) * scale
        const h = (b.y2 - b.y1) * scale

        const isAlert = !!info.alert

        if (!isAlert) {
          // ---- 일반 차량: 기존 그대로(초록 박스 + Vehicle #ID) ----
          ctx.shadowBlur = 0
          ctx.lineWidth = 2
          ctx.strokeStyle = '#00ff00'
          ctx.strokeRect(x, y, w, h)

          ctx.fillStyle = '#00ff00'
          ctx.font = 'bold 13px sans-serif'
          ctx.fillText(`Vehicle #${trackId}`, x, Math.max(y - 6, 12))
          return
        }

        // ---- 이상운전 차량: 관제 UI ----
        const color = '#ff3b3b'

        // 1) 은은한 Glow - Canvas의 shadowBlur를 이용한다(파이썬처럼 별도 알파
        //    블렌딩 오버레이를 만들 필요 없이 Canvas가 기본 지원). Pulse로 블러
        //    반경만 아주 약하게 출렁이게 해서 차량을 가리지 않는 선에서 유지한다.
        const glowRadius = 6 + 3 * (0.5 + 0.5 * Math.sin(pulsePhase))
        ctx.save()
        ctx.shadowColor = color
        ctx.shadowBlur = glowRadius
        ctx.lineWidth = 3
        ctx.strokeStyle = color
        ctx.strokeRect(x, y, w, h)
        ctx.restore() // shadowBlur를 여기서 리셋해서 아래 모서리선/텍스트까지 번지지 않게 한다

        // 2) 모서리 강조(Corner Accent) - 관제 시스템의 Detection Box 느낌
        const cornerLen = Math.min(16, w / 4, h / 4)
        ctx.lineWidth = 3
        ctx.strokeStyle = color
        ;[
          [x, y, 1, 1],
          [x + w, y, -1, 1],
          [x, y + h, 1, -1],
          [x + w, y + h, -1, -1],
        ].forEach(([cx, cy, dx, dy]) => {
          ctx.beginPath()
          ctx.moveTo(cx, cy)
          ctx.lineTo(cx + dx * cornerLen, cy)
          ctx.moveTo(cx, cy)
          ctx.lineTo(cx, cy + dy * cornerLen)
          ctx.stroke()
        })

        // 3) 한글 관제 텍스트 - Canvas는 cv2.putText와 달리 한글을 바로 그릴 수
        //    있어서(브라우저 폰트 렌더러 사용) 별도 변환 과정이 필요 없다.
        //    박스 바깥쪽(위/아래)에 배치해서 차량 자체는 가리지 않는다.
        ctx.fillStyle = color
        ctx.font = `bold 13px ${KOREAN_FONT_STACK}`
        ctx.fillText('🔴 이상운전 차량', x, Math.max(y - 8, 14))

        const plateLabel = info.plate ? `차량번호 ${info.plate}` : PLATE_UNKNOWN_LABEL
        ctx.fillStyle = '#ffffff'
        ctx.font = `12px ${KOREAN_FONT_STACK}`
        ctx.fillText(plateLabel, x, y + h + 16)

        ctx.fillStyle = color
        ctx.font = `bold 12px ${KOREAN_FONT_STACK}`
        ctx.fillText('⚠ 이상운전 감지', x, y + h + 32)
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
