import { useRef } from 'react'
import LiveHlsVideo from './LiveHlsVideo'
import CctvOverlayCanvas from './CctvOverlayCanvas'
import { useCctvDetections } from '../hooks/useCctvDetections'

/**
 * 기존 <LiveHlsVideo videoUrl={..} format={..} className={..} /> 자리를
 * <LiveHlsVideoWithDetections camId={..} videoUrl={..} format={..} className={..} />
 * 로만 바꾸면 된다 - LiveHlsVideo 자체는 그대로 내부에서 재사용하고, 그 위에
 * YOLO bbox 오버레이만 얹는다. camId로 들어오는 실시간 검출 데이터가 없는
 * 카메라는 캔버스가 그냥 비어있을 뿐이라 완전히 안전하다(기존 동작 그대로).
 */
export default function LiveHlsVideoWithDetections({ camId, videoUrl, format, className }) {
  const videoElRef = useRef(null)
  const { tracks, frameSize } = useCctvDetections(camId)

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%' }}>
      <LiveHlsVideo ref={videoElRef} videoUrl={videoUrl} format={format} className={className} />
      <CctvOverlayCanvas videoRef={videoElRef} tracks={tracks} frameSize={frameSize} />
    </div>
  )
}
