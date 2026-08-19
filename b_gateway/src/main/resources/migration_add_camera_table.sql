-- camera 테이블 추가 마이그레이션 (2026-08-18)
-- 이미 실행 중인 DB에 기존 데이터를 안 지우고 camera 테이블만 추가한다.
-- schema.sql은 DROP TABLE부터 실행하기 때문에 절대 재실행하지 말고, 이 파일만 실행할 것.
--
-- 사용법:
--   mysql -u root -p omecca < src/main/resources/migration_add_camera_table.sql
--
-- 이미 이 마이그레이션을 실행한 DB에서 다시 실행해도 안전함
-- (CREATE TABLE IF NOT EXISTS + INSERT IGNORE라 중복 실행돼도 에러 안 나고 그냥 아무 일도 안 일어남).

USE omecca;

CREATE TABLE IF NOT EXISTS camera (
    id              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    cam_id          VARCHAR(50)   NOT NULL,
    name            VARCHAR(100)  NOT NULL COMMENT '화면에 보여줄 이름/위치 (예: 이수역)',
    status          ENUM('ACTIVE', 'INACTIVE') NOT NULL DEFAULT 'ACTIVE',
    stream_url      VARCHAR(500)  NULL COMMENT '실시간 영상 URL. 없으면 NULL(=아직 실시간 연결 없음)',
    stream_format   VARCHAR(20)   NULL COMMENT 'HLS / MP4 등',
    created_at      DATETIME(3)   NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    UNIQUE KEY uk_camera_cam_id (cam_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO camera (cam_id, name, status, stream_url, stream_format) VALUES
    ('L010263', '이수역',     'ACTIVE', 'https://strm1.spatic.go.kr/live/76.stream/chunklist_w1824089310.m3u8', 'HLS'),
    ('L010117', '사당역',     'ACTIVE', 'https://strm1.spatic.go.kr/live/75.stream/chunklist_w902267922.m3u8',  'HLS'),
    ('L010018', '경남아파트', 'ACTIVE', 'https://strm2.spatic.go.kr/live/243.stream/chunklist_w575481354.m3u8', 'HLS'),
    ('L010055', '까치고개',   'ACTIVE', 'https://strm1.spatic.go.kr/live/73.stream/chunklist_w2053157549.m3u8', 'HLS');
