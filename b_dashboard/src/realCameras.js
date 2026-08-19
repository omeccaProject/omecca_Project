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
  { camId: 'L010139', name: '서울대입구R', videoUrl: 'https://strm1.spatic.go.kr/live/72.stream/chunklist_w997501396.m3u8' },
  { camId: 'L010417', name: '신림사거리', videoUrl: 'https://strm1.spatic.go.kr/live/71.stream/chunklist_w757045976.m3u8' },
  { camId: 'L010065', name: '당곡사거리', videoUrl: 'https://strm1.spatic.go.kr/live/70.stream/chunklist_w360269996.m3u8' },
  { camId: 'L010057', name: '남태령고개', videoUrl: 'https://strm1.spatic.go.kr/live/74.stream/chunklist_w1686001889.m3u8' },
  { camId: 'L010067', name: '대림삼거리', videoUrl: 'https://strm1.spatic.go.kr/live/67.stream/chunklist_w2027144219.m3u8' },
  { camId: 'L010059', name: '노량진삼거리', videoUrl: 'https://strm2.spatic.go.kr/live/257.stream/chunklist_w2016759099.m3u8' },
  { camId: 'L010200', name: '여의교남단', videoUrl: 'https://strm1.spatic.go.kr/live/84.stream/chunklist_w742801142.m3u8' },
  { camId: 'L010201', name: '여의교북단', videoUrl: 'https://strm1.spatic.go.kr/live/39.stream/chunklist_w1995291208.m3u8' },
  { camId: 'L010035', name: '거리공원오거리', videoUrl: 'https://strm3.spatic.go.kr/live/270.stream/chunklist_w483949893.m3u8' },
  { camId: 'L010034', name: '구로IC', videoUrl: 'https://strm1.spatic.go.kr/live/95.stream/chunklist_w1757989951.m3u8' },
  { camId: 'L010036', name: '구로역', videoUrl: 'https://strm1.spatic.go.kr/live/32.stream/chunklist_w792463215.m3u8' },
  { camId: 'L010025', name: '고척교', videoUrl: 'https://strm1.spatic.go.kr/live/23.stream/chunklist_w1287068082.m3u8' },
  { camId: 'L010609', name: '오금교', videoUrl: 'https://strm4.spatic.go.kr/live/347.stream/chunklist_w2022844708.m3u8' },
  { camId: 'L010222', name: '오금교서단', videoUrl: 'https://strm2.spatic.go.kr/live/249.stream/chunklist_w550956998.m3u8' },
  { camId: 'L010181', name: '신정교동단', videoUrl: 'https://strm2.spatic.go.kr/live/250.stream/chunklist_w767372825.m3u8' },
  { camId: 'L010175', name: '신도림역', videoUrl: 'https://strm1.spatic.go.kr/live/33.stream/chunklist_w693507665.m3u8' },
  { camId: 'L010098', name: '문래고가밑', videoUrl: 'https://strm2.spatic.go.kr/live/246.stream/chunklist_w954960516.m3u8' },
  { camId: 'L010218', name: '영등포시장', videoUrl: 'https://strm1.spatic.go.kr/live/96.stream/chunklist_w769630191.m3u8' },
  { camId: 'L010431', name: '영등포구청', videoUrl: 'https://strm1.spatic.go.kr/live/97.stream/chunklist_w1467383714.m3u8' },
  // L010610 - utic-video-sources.json엔 URL이 있지만 위치 이름 미확인이라 보류.
  // { camId: 'L010610', name: '???', videoUrl: 'https://strm4.spatic.go.kr/live/348.stream/chunklist_w2022844708.m3u8' },
]

export const REAL_CAMERA_BY_ID = Object.fromEntries(REAL_CAMERAS.map((c) => [c.camId, c]))
