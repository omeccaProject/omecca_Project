-- camera_catalog 테이블 추가 마이그레이션 (2026-08-19)
-- "UTIC 카메라 사전 등록" 고도화 - "카메라 관리"에서 cam_id/이름을 입력하면 자동완성으로
-- streamUrl을 채워주기 위한 참조 테이블. 실제 등록된 camera 테이블과는 별개다.
--
-- *** 이 테이블은 새 엔티티(CameraCatalog.java)라서 백엔드가 시작할 때 스키마 검증
-- (ddl-auto: validate)을 통과하려면, 반드시 백엔드를 재시작하기 전에 이 SQL을 먼저
-- 실행해야 한다 (target 컬럼 추가 때와 동일한 이유). ***
--
-- 사용법:
--   mysql -u root -p omecca < src/main/resources/migration_add_camera_catalog.sql
--   (실행 후 백엔드 재시작)
--
-- 이미 실행한 DB에서 다시 실행해도 안전함
-- (CREATE TABLE IF NOT EXISTS + INSERT IGNORE라 중복 실행돼도 에러 안 나고 그냥 아무 일도 안 일어남).

USE omecca;

CREATE TABLE IF NOT EXISTS camera_catalog (
    id              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    cam_id          VARCHAR(50)   NOT NULL,
    name            VARCHAR(100)  NOT NULL,
    stream_url      VARCHAR(500)  NOT NULL,
    stream_format   VARCHAR(20)   NULL,
    source_type     VARCHAR(50)   NULL COMMENT '영상을 실제로 제공하는 기관 (예: 서울교통정보센터)',
    created_at      DATETIME(3)   NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    UNIQUE KEY uk_camera_catalog_cam_id (cam_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO camera_catalog (cam_id, name, stream_url, stream_format, source_type) VALUES
    ('L010263', '이수역',       'https://strm1.spatic.go.kr/live/76.stream/chunklist_w1824089310.m3u8', 'HLS', '서울교통정보센터'),
    ('L010117', '사당역',       'https://strm1.spatic.go.kr/live/75.stream/chunklist_w902267922.m3u8',  'HLS', '서울교통정보센터'),
    ('L010018', '경남아파트',   'https://strm2.spatic.go.kr/live/243.stream/chunklist_w575481354.m3u8', 'HLS', '서울교통정보센터'),
    ('L010055', '까치고개',     'https://strm1.spatic.go.kr/live/73.stream/chunklist_w2053157549.m3u8', 'HLS', '서울교통정보센터'),
    ('L010139', '서울대입구R',  'https://strm1.spatic.go.kr/live/72.stream/chunklist_w997501396.m3u8',  'HLS', '서울교통정보센터'),
    ('L010417', '신림사거리',   'https://strm1.spatic.go.kr/live/71.stream/chunklist_w757045976.m3u8',  'HLS', '서울교통정보센터'),
    ('L010065', '당곡사거리',   'https://strm1.spatic.go.kr/live/70.stream/chunklist_w360269996.m3u8',  'HLS', '서울교통정보센터'),
    ('L010057', '남태령고개',   'https://strm1.spatic.go.kr/live/74.stream/chunklist_w1686001889.m3u8', 'HLS', '서울교통정보센터'),
    ('L010067', '대림삼거리',   'https://strm1.spatic.go.kr/live/67.stream/chunklist_w2027144219.m3u8', 'HLS', '서울교통정보센터'),
    ('L010059', '노량진삼거리', 'https://strm2.spatic.go.kr/live/257.stream/chunklist_w2016759099.m3u8','HLS', '서울교통정보센터'),
    ('L010200', '여의교남단',   'https://strm1.spatic.go.kr/live/84.stream/chunklist_w742801142.m3u8',  'HLS', '서울교통정보센터'),
    ('L010201', '여의교북단',   'https://strm1.spatic.go.kr/live/39.stream/chunklist_w1995291208.m3u8', 'HLS', '서울교통정보센터'),
    ('L010035', '거리공원오거리','https://strm3.spatic.go.kr/live/270.stream/chunklist_w483949893.m3u8','HLS', '서울교통정보센터'),
    ('L010034', '구로IC',       'https://strm1.spatic.go.kr/live/95.stream/chunklist_w1757989951.m3u8', 'HLS', '서울교통정보센터'),
    ('L010036', '구로역',       'https://strm1.spatic.go.kr/live/32.stream/chunklist_w792463215.m3u8',  'HLS', '서울교통정보센터'),
    ('L010025', '고척교',       'https://strm1.spatic.go.kr/live/23.stream/chunklist_w1287068082.m3u8', 'HLS', '서울교통정보센터'),
    ('L010609', '오금교',       'https://strm4.spatic.go.kr/live/347.stream/chunklist_w2022844708.m3u8','HLS', '서울교통정보센터'),
    ('L010222', '오금교서단',   'https://strm2.spatic.go.kr/live/249.stream/chunklist_w550956998.m3u8', 'HLS', '서울교통정보센터'),
    ('L010181', '신정교동단',   'https://strm2.spatic.go.kr/live/250.stream/chunklist_w767372825.m3u8', 'HLS', '서울교통정보센터'),
    ('L010175', '신도림역',     'https://strm1.spatic.go.kr/live/33.stream/chunklist_w693507665.m3u8',  'HLS', '서울교통정보센터'),
    ('L010098', '문래고가밑',   'https://strm2.spatic.go.kr/live/246.stream/chunklist_w954960516.m3u8', 'HLS', '서울교통정보센터'),
    ('L010218', '영등포시장',   'https://strm1.spatic.go.kr/live/96.stream/chunklist_w769630191.m3u8',  'HLS', '서울교통정보센터'),
    ('L010431', '영등포구청',   'https://strm1.spatic.go.kr/live/97.stream/chunklist_w1467383714.m3u8', 'HLS', '서울교통정보센터');
