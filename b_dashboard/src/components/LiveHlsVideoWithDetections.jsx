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

  // [주의] 이 컴포넌트는 3곳(그리드 셀 / 확대 모달 / 대시보드 CCTV 패널)에서 쓰이는데,
  // 각자 레이아웃이 다르다 - 그리드 셀은 flex:1로 footer와 공간을 나눠 가져야 하고,
  // 확대 모달/대시보드 패널은 aspect-ratio로 크기가 이미 정해진 박스를 그냥 꽉 채우면
  // 된다. 예전엔 이 wrapper div에 flex:1을 하드코딩해서 그리드 셀은 고쳤지만 확대
  // 모달이 끝없이 늘어나 화면 중앙에 안 뜨고 잘려 보이는 새 버그가 생겼었다.
  // 그래서 레이아웃 결정은 각 호출부가 넘겨준 className(cctv-cell-live-video /
  // cctv-zoom-live-video / dash-cctv-video)에 App.css가 그대로 위임하고, 여기서는
  // "안쪽 video/canvas가 이 박스를 꽉 채운다"는 것만 보장한다(.cctv-live-detections-wrap
  // 규칙 참고). className을 예전처럼 안쪽 <LiveHlsVideo>가 아니라 이 wrapper 자체에 준다.
  return (
    <div className={`cctv-live-detections-wrap ${className || ''}`}>
      <LiveHlsVideo ref={videoElRef} videoUrl={videoUrl} format={format} />
      <CctvOverlayCanvas videoRef={videoElRef} tracks={tracks} frameSize={frameSize} />
    </div>
  )
}
