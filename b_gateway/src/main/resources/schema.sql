-- omecca DB 스키마 (target / roi / event / report / user)
-- 원래 설계(이벤트 스키마 규격서 / DB 스키마 설계서) 기준으로 복원됨
-- 사용: mysql -u root -p < src/main/resources/schema.sql

CREATE DATABASE IF NOT EXISTS omecca
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE omecca;

DROP TABLE IF EXISTS report;
DROP TABLE IF EXISTS event;
DROP TABLE IF EXISTS roi;
DROP TABLE IF EXISTS target;
DROP TABLE IF EXISTS camera;

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

-- 실시간 영상이 이미 확인된 4곳 시드 (e_tracking/SmartCCTV/web/data/utic-video-sources.json +
-- utic-cameras-seoul.json 기준. b_dashboard/src/realCameras.js에 프론트 하드코딩돼 있던 것과 동일한 값).
INSERT INTO camera (cam_id, name, status, stream_url, stream_format) VALUES
    ('L010263', '이수역',     'ACTIVE', 'https://strm1.spatic.go.kr/live/76.stream/chunklist_w1824089310.m3u8', 'HLS'),
    ('L010117', '사당역',     'ACTIVE', 'https://strm1.spatic.go.kr/live/75.stream/chunklist_w902267922.m3u8',  'HLS'),
    ('L010018', '경남아파트', 'ACTIVE', 'https://strm2.spatic.go.kr/live/243.stream/chunklist_w575481354.m3u8', 'HLS'),
    ('L010055', '까치고개',   'ACTIVE', 'https://strm1.spatic.go.kr/live/73.stream/chunklist_w2053157549.m3u8', 'HLS');

-- 관심 대상 (기능 ③ 관제요원이 등록하는 감시 대상)
CREATE TABLE target (
    id              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    target_type     ENUM('PERSON', 'VEHICLE') NOT NULL,
    plate_number    VARCHAR(20)   NULL,
    person_ref_id   VARCHAR(50)   NULL COMMENT '얼굴 임베딩/수배자 DB 참조 ID',
    label           VARCHAR(100)  NULL COMMENT '관제요원이 붙인 메모/별칭',
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