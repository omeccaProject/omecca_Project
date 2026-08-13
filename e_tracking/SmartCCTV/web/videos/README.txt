경로 안내
====================================================
  SMARTCCTV/
  ├── anomaly_detection.py     (기존 AI 탐지/추적/판정 스크립트, 실시간 로컬 창)
  ├── export_track_log.py      (신규 - 사전 분석 배치 스크립트, anomaly_detection.py를 import해서 재사용)
  ├── videos/
  │   ├── 0805.mp4     (이상운전 AI 테스트용)
  │   ├── 0807.mp4     (현재 미사용 - 삭제하지 않고 보관)
  │   └── traffic.mp4  (일반 CCTV 영상)
  └── web/
      ├── index.html
      ├── map.js
      └── data/
          ├── anomaly-track-log.json   (export_track_log.py가 만드는 결과물)
          └── event.json               (실시간 Python 연동용, 이번 방식과는 별개 채널)

현재 영상 연결 (cam_id 고정 매핑, 순환 배정 없음)
====================================================
const TEST_VIDEO_OVERRIDES = {
  J7878: { videoUrl: "../videos/traffic.mp4", purpose: "GENERAL_CCTV" },
  H4642: { videoUrl: "../videos/0805.mp4",   purpose: "ANOMALY_DETECTION_TEST" },
};

브라우저에서 "이상 주행 감지" 빨간 박스가 뜨는 방식 (신규)
====================================================
1. 터미널에서 딱 한 번(0805.mp4가 바뀌지 않는 한 다시 실행할 필요 없음):

     python export_track_log.py

   이 스크립트는 anomaly_detection.py의 detect/update_track/
   evaluate_anomaly_rules/is_abnormal_active/get_vehicle_plate를 그대로
   호출해서 0805.mp4를 처음부터 끝까지 한 번 분석하고,
   web/data/anomaly-track-log.json 에 프레임별 차량 박스 좌표와
   "이상운전 에피소드 시작 시각" 목록을 저장합니다.
   (결과 영상 mp4를 만들지 않습니다. cv2 창도 뜨지 않습니다.)

2. 그 다음부터는 Python을 켜둘 필요 없이, GIS에서 H4642(이수어린이집 앞)를
   클릭하면:
     - 0805.mp4가 재생되고
     - 영상 위에 canvas로 차량 박스가 실시간으로 그려지고
       (평소엔 하늘색 얇은 박스, 이상운전 중이면 빨간 박스 + "이상 주행 감지" 라벨)
     - 영상이 "이상운전 에피소드 시작 시각"을 지나갈 때마다 자동으로
       AI 관제 이벤트 카드 / 토스트 알림 / 상단 통계가 함께 반응합니다.
     - 영상은 loop 재생이라 매 반복마다 같은 에피소드가 다시 재현됩니다.

3. anomaly-track-log.json이 아직 없으면(export_track_log.py를 실행하지
   않았으면) 영상만 재생되고 박스는 그려지지 않습니다. 콘솔에
   "[ANOMALY OVERLAY] ... export_track_log.py를 먼저 실행했는지 확인" 경고가 뜹니다.
   (web/data/anomaly-track-log.json에 미리 빈 스텁 파일을 넣어뒀으니
    실행 전에도 에러 없이 영상만 정상 재생됩니다.)

기존 실시간 event.json 채널과의 관계
====================================================
data/event.json 폴링 방식(AiEventListener)은 그대로 남아있습니다.
실제 라이브 카메라를 붙이게 되면 그때는 event.json 방식(또는 WebSocket)이
필요합니다. 지금 H4642 데모는 위 사전 분석 방식만으로 완결되므로,
같은 카메라에 대해 두 채널을 동시에 켜두면 이벤트가 중복으로 뜰 수 있습니다.
데모할 때는 anomaly_detection.py(실시간)를 굳이 같이 켜지 않아도 됩니다.

주의: 0805.mp4의 실제 촬영 장소는 "이수어린이집 앞"이 아닙니다.
H4642는 AI 이상운전 테스트를 위한 "테스트 슬롯"입니다.

다른 카메라 연결하기
====================================================
TEST_VIDEO_OVERRIDES 객체에 아래 형태로 한 줄만 추가하면 됩니다.

  "카메라관리번호": { videoUrl: "../videos/파일명.mp4", purpose: "GENERAL_CCTV" }

카메라관리번호는 브라우저 콘솔에서 찾을 수 있습니다.

  trafficCameraManager.allRecords.filter(r => r.설치장소.includes('검색어'))
