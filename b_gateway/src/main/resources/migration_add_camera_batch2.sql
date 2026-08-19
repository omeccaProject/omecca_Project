-- camera 테이블에 실시간 영상 URL이 새로 확인된 19개 카메라 추가 (2026-08-19)
-- e_tracking/SmartCCTV/web/data/utic-video-sources.json에 URL이 최신화된 cam_id들 중,
-- 위치 이름까지 확인된 19개를 등록한다. (기존 4개: 이수역/사당역/경남아파트/까치고개는 이미
-- migration_add_camera_table.sql로 등록돼있어서 여기 다시 안 넣음 - INSERT IGNORE라 넣어도 안전하긴 함)
--
-- L010610은 utic-video-sources.json엔 URL이 있지만 위치 이름을 아직 안 받아서 보류(주석 처리).
-- 나중에 이름 확인되면 맨 아래 주석 풀고 실행하면 됨.
--
-- 사용법:
--   mysql -u root -p omecca < src/main/resources/migration_add_camera_batch2.sql
--
-- 이미 실행한 DB에서 다시 실행해도 안전함(INSERT IGNORE라 cam_id 중복이면 그냥 스킵됨).

USE omecca;

INSERT IGNORE INTO camera (cam_id, name, status, stream_url, stream_format) VALUES
    ('L010139', '서울대입구R',   'ACTIVE', 'https://strm1.spatic.go.kr/live/72.stream/chunklist_w997501396.m3u8',  'HLS'),
    ('L010417', '신림사거리',    'ACTIVE', 'https://strm1.spatic.go.kr/live/71.stream/chunklist_w757045976.m3u8',  'HLS'),
    ('L010065', '당곡사거리',    'ACTIVE', 'https://strm1.spatic.go.kr/live/70.stream/chunklist_w360269996.m3u8',  'HLS'),
    ('L010057', '남태령고개',    'ACTIVE', 'https://strm1.spatic.go.kr/live/74.stream/chunklist_w1686001889.m3u8', 'HLS'),
    ('L010067', '대림삼거리',    'ACTIVE', 'https://strm1.spatic.go.kr/live/67.stream/chunklist_w2027144219.m3u8', 'HLS'),
    ('L010059', '노량진삼거리',  'ACTIVE', 'https://strm2.spatic.go.kr/live/257.stream/chunklist_w2016759099.m3u8','HLS'),
    ('L010200', '여의교남단',    'ACTIVE', 'https://strm1.spatic.go.kr/live/84.stream/chunklist_w742801142.m3u8',  'HLS'),
    ('L010201', '여의교북단',    'ACTIVE', 'https://strm1.spatic.go.kr/live/39.stream/chunklist_w1995291208.m3u8', 'HLS'),
    ('L010035', '거리공원오거리','ACTIVE', 'https://strm3.spatic.go.kr/live/270.stream/chunklist_w483949893.m3u8', 'HLS'),
    ('L010034', '구로IC',        'ACTIVE', 'https://strm1.spatic.go.kr/live/95.stream/chunklist_w1757989951.m3u8', 'HLS'),
    ('L010036', '구로역',        'ACTIVE', 'https://strm1.spatic.go.kr/live/32.stream/chunklist_w792463215.m3u8',  'HLS'),
    ('L010025', '고척교',        'ACTIVE', 'https://strm1.spatic.go.kr/live/23.stream/chunklist_w1287068082.m3u8', 'HLS'),
    ('L010609', '오금교',        'ACTIVE', 'https://strm4.spatic.go.kr/live/347.stream/chunklist_w2022844708.m3u8','HLS'),
    ('L010222', '오금교서단',    'ACTIVE', 'https://strm2.spatic.go.kr/live/249.stream/chunklist_w550956998.m3u8', 'HLS'),
    ('L010181', '신정교동단',    'ACTIVE', 'https://strm2.spatic.go.kr/live/250.stream/chunklist_w767372825.m3u8', 'HLS'),
    ('L010175', '신도림역',      'ACTIVE', 'https://strm1.spatic.go.kr/live/33.stream/chunklist_w693507665.m3u8',  'HLS'),
    ('L010098', '문래고가밑',    'ACTIVE', 'https://strm2.spatic.go.kr/live/246.stream/chunklist_w954960516.m3u8', 'HLS'),
    ('L010218', '영등포시장',    'ACTIVE', 'https://strm1.spatic.go.kr/live/96.stream/chunklist_w769630191.m3u8',  'HLS'),
    ('L010431', '영등포구청',    'ACTIVE', 'https://strm1.spatic.go.kr/live/97.stream/chunklist_w1467383714.m3u8', 'HLS');

-- 이름 확인되면 위 VALUES 마지막 줄 끝에 콤마(,) 붙이고 아래 주석 풀 것:
-- INSERT IGNORE INTO camera (cam_id, name, status, stream_url, stream_format) VALUES
--     ('L010610', '???', 'ACTIVE', 'https://strm4.spatic.go.kr/live/348.stream/chunklist_w2022844708.m3u8', 'HLS');
