-- omecca DB 스키마 (target / roi / event / report)
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