// [폴백 전용] 실제로 실시간 영상이 연결된 CCTV 4곳 (UTIC/서울교통정보센터 HLS 스트림).
// 이제 CctvGrid는 기본적으로 DB(camera 테이블, /api/cameras)에서 실시간 카메라 목록을
// 직접 불러온다("카메라 관리" 버튼에서 등록/수정). 이 파일은 마이그레이션을 아직 안 돌렸거나
// /api/cameras 호출이 실패했을 때만 쓰이는 안전망(폴백)이다 — 평소엔 DB 쪽이 우선.
// 값의 출처: e_tracking/SmartCCTV/web/data/utic-video-sources.json(영상 URL) +
//           utic-cameras-seoul.json(cam_id → 이름 매핑).
// camId는 이벤트 파이프라인이 쓰는 "CAM-01" 같은 임시 라벨과 다른 체계(UTIC cam_id)라서
// 이벤트와 자동으로 매칭되지는 않음 — 지금은 "실시간 영상 자체가 연결된 카메라"만 보여주는 용도.
export const REAL_CAMERAS = [
  {
    camId: 'L010263',
    name: '이수역',
    videoUrl: 'https://strm1.spatic.go.kr/live/76.stream/chunklist_w1824089310.m3u8',
  },
  {
    camId: 'L010117',
    name: '사당역',
    videoUrl: 'https://strm1.spatic.go.kr/live/75.stream/chunklist_w902267922.m3u8',
  },
  {
    camId: 'L010018',
    name: '경남아파트',
    videoUrl: 'https://strm2.spatic.go.kr/live/243.stream/chunklist_w575481354.m3u8',
  },
  {
    camId: 'L010055',
    name: '까치고개',
    videoUrl: 'https://strm1.spatic.go.kr/live/73.stream/chunklist_w2053157549.m3u8',
  },
]

export const REAL_CAMERA_BY_ID = Object.fromEntries(REAL_CAMERAS.map((c) => [c.camId, c]))
