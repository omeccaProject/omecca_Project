-- =====================================================================
-- V1 : 오메카3 통합 스키마 기준선(baseline)
--
-- b_gateway/src/main/resources/schema.sql 을 Flyway 규격으로 옮긴 것.
-- 원본에서 아래 두 가지를 뺐다.
--
--   CREATE DATABASE omecca ...   Flyway 는 이미 그 DB 에 접속한 상태로 돈다
--   USE omecca;                  같은 이유. 남겨 두면 마이그레이션이 깨진다
--
-- 테이블: camera, camera_catalog, target, roi, event, report, user
-- =====================================================================

DROP TABLE IF EXISTS report;

DROP TABLE IF EXISTS event;

DROP TABLE IF EXISTS roi;

DROP TABLE IF EXISTS target;

DROP TABLE IF EXISTS camera;

DROP TABLE IF EXISTS camera_catalog;


-- 카메라 마스터 데이터 (실제 설치된 카메라 목록/이름/실시간 영상 연결 여부).
-- event.cam_id / roi.cam_id는 지금도 자유 텍스트라 이 테이블을 참조하는 외래키는 걸지 않았음
-- (팀원 모듈이 여기 등록 안 된 cam_id를 보내면 이벤트 저장 자체가 막히기 때문 — 아래 참고).
CREATE TABLE camera (
    id              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    cam_id          VARCHAR(50)   NOT NULL,
    name            VARCHAR(100)  NOT NULL COMMENT '화면에 보여줄 이름/위치 (예: 이수역)',
    status          ENUM('ACTIVE', 'INACTIVE') NOT NULL DEFAULT 'ACTIVE',
    stream_url      VARCHAR(500)  NULL COMMENT '실시간 영상 URL. 없으면 NULL(=아직 실시간 연결 없음)',
    stream_format   VARCHAR(20)   NULL COMMENT 'HLS / MP4 등',
    created_at      DATETIME(3)   NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    UNIQUE KEY uk_camera_cam_id (cam_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- 실시간 영상이 확인된 카메라 시드 (e_tracking/SmartCCTV/web/data/utic-video-sources.json +
-- utic-cameras-seoul.json 기준. b_dashboard/src/realCameras.js에 프론트 하드코딩돼 있던 것과 동일한 값).
-- 앞의 4개는 처음부터 있던 것, 그 아래 19개는 utic-video-sources.json에 URL이 새로 확인돼서 추가한 것.
INSERT INTO camera (cam_id, name, status, stream_url, stream_format) VALUES
    ('L010263', '이수역',       'ACTIVE', 'https://strm1.spatic.go.kr/live/76.stream/chunklist_w1824089310.m3u8', 'HLS'),
    ('L010117', '사당역',       'ACTIVE', 'https://strm1.spatic.go.kr/live/75.stream/chunklist_w902267922.m3u8',  'HLS'),
    ('L010018', '경남아파트',   'ACTIVE', 'https://strm2.spatic.go.kr/live/243.stream/chunklist_w575481354.m3u8', 'HLS'),
    ('L010055', '까치고개',     'ACTIVE', 'https://strm1.spatic.go.kr/live/73.stream/chunklist_w2053157549.m3u8', 'HLS'),
    ('L010139', '서울대입구R',  'ACTIVE', 'https://strm1.spatic.go.kr/live/72.stream/chunklist_w997501396.m3u8',  'HLS'),
    ('L010417', '신림사거리',   'ACTIVE', 'https://strm1.spatic.go.kr/live/71.stream/chunklist_w757045976.m3u8',  'HLS'),
    ('L010065', '당곡사거리',   'ACTIVE', 'https://strm1.spatic.go.kr/live/70.stream/chunklist_w360269996.m3u8',  'HLS'),
    ('L010057', '남태령고개',   'ACTIVE', 'https://strm1.spatic.go.kr/live/74.stream/chunklist_w1686001889.m3u8', 'HLS'),
    ('L010067', '대림삼거리',   'ACTIVE', 'https://strm1.spatic.go.kr/live/67.stream/chunklist_w2027144219.m3u8', 'HLS'),
    ('L010059', '노량진삼거리', 'ACTIVE', 'https://strm2.spatic.go.kr/live/257.stream/chunklist_w2016759099.m3u8','HLS'),
    ('L010200', '여의교남단',   'ACTIVE', 'https://strm1.spatic.go.kr/live/84.stream/chunklist_w742801142.m3u8',  'HLS'),
    ('L010201', '여의교북단',   'ACTIVE', 'https://strm1.spatic.go.kr/live/39.stream/chunklist_w1995291208.m3u8', 'HLS'),
    ('L010035', '거리공원오거리','ACTIVE','https://strm3.spatic.go.kr/live/270.stream/chunklist_w483949893.m3u8', 'HLS'),
    ('L010034', '구로IC',       'ACTIVE', 'https://strm1.spatic.go.kr/live/95.stream/chunklist_w1757989951.m3u8', 'HLS'),
    ('L010036', '구로역',       'ACTIVE', 'https://strm1.spatic.go.kr/live/32.stream/chunklist_w792463215.m3u8',  'HLS'),
    ('L010025', '고척교',       'ACTIVE', 'https://strm1.spatic.go.kr/live/23.stream/chunklist_w1287068082.m3u8', 'HLS'),
    ('L010609', '오금교',       'ACTIVE', 'https://strm4.spatic.go.kr/live/347.stream/chunklist_w2022844708.m3u8','HLS'),
    ('L010222', '오금교서단',   'ACTIVE', 'https://strm2.spatic.go.kr/live/249.stream/chunklist_w550956998.m3u8', 'HLS'),
    ('L010181', '신정교동단',   'ACTIVE', 'https://strm2.spatic.go.kr/live/250.stream/chunklist_w767372825.m3u8', 'HLS'),
    ('L010175', '신도림역',     'ACTIVE', 'https://strm1.spatic.go.kr/live/33.stream/chunklist_w693507665.m3u8',  'HLS'),
    ('L010098', '문래고가밑',   'ACTIVE', 'https://strm2.spatic.go.kr/live/246.stream/chunklist_w954960516.m3u8', 'HLS'),
    ('L010218', '영등포시장',   'ACTIVE', 'https://strm1.spatic.go.kr/live/96.stream/chunklist_w769630191.m3u8',  'HLS'),
    ('L010431', '영등포구청',   'ACTIVE', 'https://strm1.spatic.go.kr/live/97.stream/chunklist_w1467383714.m3u8', 'HLS');

    -- ('L010610', '???',       'ACTIVE', 'https://strm4.spatic.go.kr/live/348.stream/chunklist_w2022844708.m3u8','HLS'),
    -- utic-video-sources.json엔 URL이 있지만 이름(위치)을 아직 안 알려줘서 보류 - 나중에 이름 확인되면
    -- 위 줄 주석 풀고 바로 위 줄 끝에 콤마(,) 다시 붙이면 됨.

-- UTIC 카메라 사전 등록 카탈로그 (고도화: "카메라 관리"에서 cam_id/이름 자동완성용).
-- camera 테이블과는 별개 - 실제로 켜져 있는 카메라(camera)가 아니라, "영상 URL이 확인돼서
-- 언제든 등록 가능한 카메라 후보 목록"이다. 지금은 camera에 등록된 것과 내용이 같지만,
-- 나중에 URL이 더 확인되는 대로 여기만 먼저 채워두고 실제 등록(camera)은 필요할 때 하면 됨.
CREATE TABLE camera_catalog (
    id              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    cam_id          VARCHAR(50)   NOT NULL,
    name            VARCHAR(100)  NOT NULL,
    stream_url      VARCHAR(500)  NOT NULL,
    stream_format   VARCHAR(20)   NULL,
    source_type     VARCHAR(50)   NULL COMMENT '영상을 실제로 제공하는 기관 (예: 서울교통정보센터)',
    created_at      DATETIME(3)   NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    UNIQUE KEY uk_camera_catalog_cam_id (cam_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


INSERT INTO camera_catalog (cam_id, name, stream_url, stream_format, source_type) VALUES
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


-- 관심 대상 (기능 ③ 관제요원이 등록하는 감시 대상)
CREATE TABLE target (
    id              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    target_type     ENUM('PERSON', 'VEHICLE') NOT NULL,
    plate_number    VARCHAR(20)   NULL,
    person_ref_id   VARCHAR(50)   NULL COMMENT '얼굴 임베딩/수배자 DB 참조 ID',
    label           VARCHAR(100)  NULL COMMENT '관제요원이 붙인 메모/별칭',
    color           VARCHAR(30)   NULL COMMENT '차량 색상 (VEHICLE 전용)',
    vehicle_model   VARCHAR(50)   NULL COMMENT '차종 - 브랜드/모델/트림 (VEHICLE 전용, 예: 아반떼CN7)',
    registered_by   VARCHAR(50)   NOT NULL COMMENT '등록한 관제요원 계정',
    status          ENUM('ACTIVE', 'CLOSED') NOT NULL DEFAULT 'ACTIVE',
    created_at      DATETIME(3)   NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    closed_at       DATETIME(3)   NULL,
    INDEX idx_target_plate (plate_number),
    INDEX idx_target_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- 감지 구역 / 가상 라인 (기능 ⑤ 낙하물, ⑦ 신호위반·유턴 판정 기준)
CREATE TABLE roi (
    id              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    cam_id          VARCHAR(50)   NOT NULL,
    roi_type        ENUM('ZONE', 'LINE') NOT NULL,
    name            VARCHAR(100)  NOT NULL,
    geometry_json   JSON          NOT NULL COMMENT '좌표 폴리곤/라인 정의',
    created_at      DATETIME(3)   NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    INDEX idx_roi_cam (cam_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- 탐지 이벤트 (핵심 테이블)
CREATE TABLE event (
    id                      BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    cam_id                  VARCHAR(50)   NOT NULL,
    track_id                VARCHAR(50)   NULL,
    event_type              ENUM(
                                'WANTED_PERSON',
                                'WEAPON',
                                'UNREGISTERED_VEHICLE',
                                'DEBRIS',
                                'DUI_PATTERN',
                                'SIGNAL_VIOLATION',
                                'UTURN_VIOLATION'
                            ) NOT NULL,
    object_class            ENUM('PERSON', 'VEHICLE', 'OBJECT') NOT NULL,
    bbox_x                  INT NULL,
    bbox_y                  INT NULL,
    bbox_w                  INT NULL,
    bbox_h                  INT NULL,
    confidence              DECIMAL(4,3) NULL,
    occurred_at             DATETIME(3)  NOT NULL,
    received_at             DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    lat                     DECIMAL(10,7) NULL,
    lng                     DECIMAL(10,7) NULL,
    is_registered_target    TINYINT(1)   NOT NULL DEFAULT 0,
    target_id               BIGINT UNSIGNED NULL,
    roi_id                  BIGINT UNSIGNED NULL,
    meta                    JSON NULL COMMENT 'plateNumber/matchedDbId/faceMatchScore/stationaryDurationSec/trajectoryFeatures 등',
    frame_ref_before        VARCHAR(255) NULL,
    frame_ref_after         VARCHAR(255) NULL,
    created_at              DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    CONSTRAINT fk_event_target FOREIGN KEY (target_id) REFERENCES target(id) ON DELETE SET NULL,
    CONSTRAINT fk_event_roi    FOREIGN KEY (roi_id)    REFERENCES roi(id)    ON DELETE SET NULL,
    INDEX idx_event_cam_time (cam_id, occurred_at),
    INDEX idx_event_type_time (event_type, occurred_at),
    INDEX idx_event_track (track_id),
    INDEX idx_event_target (target_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- 증거 리포트 (event 1건당 1건)
CREATE TABLE report (
    id              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    event_id        BIGINT UNSIGNED NOT NULL,
    pdf_path        VARCHAR(255) NOT NULL,
    status          ENUM('PENDING', 'GENERATED', 'FAILED') NOT NULL DEFAULT 'PENDING',
    generated_at    DATETIME(3)  NULL,
    created_at      DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    CONSTRAINT fk_report_event FOREIGN KEY (event_id) REFERENCES event(id) ON DELETE CASCADE,
    UNIQUE KEY uk_report_event (event_id),
    INDEX idx_report_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- 관제요원 계정 (회원가입 신청 -> 관리자 승인 -> 로그인)
DROP TABLE IF EXISTS user;


CREATE TABLE user (
    id              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    username        VARCHAR(50)   NOT NULL,
    password        VARCHAR(255)  NOT NULL COMMENT 'BCrypt 해시',
    name            VARCHAR(50)   NOT NULL,
    role            ENUM('USER', 'ADMIN') NOT NULL DEFAULT 'USER',
    status          ENUM('PENDING', 'APPROVED', 'REJECTED') NOT NULL DEFAULT 'PENDING',
    approved_by     BIGINT UNSIGNED NULL,
    approved_at     DATETIME(3)   NULL,
    created_at      DATETIME(3)   NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    UNIQUE KEY uk_user_username (username),
    INDEX idx_user_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- 최초 관리자 계정 시드 (아이디: admin / 비밀번호: admin1234 -- 로그인 후 꼭 변경할 것)
INSERT INTO user (username, password, name, role, status, approved_at)
VALUES ('admin', '$2a$10$p8JYOKgnKcXAv.THDHZk9OReP2DkXh3a4PJ6lwIjXLrpvNhUmA5ae', '관리자', 'ADMIN', 'APPROVED', NOW(3));
