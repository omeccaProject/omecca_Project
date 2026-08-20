-- =====================================================================
-- V2 : LPR 모듈 테이블 (박지원 / d_lpr)
--
-- d_lpr/sql/schema.sql 을 Flyway 규격으로 옮긴 것. CREATE DATABASE / USE 제거.
--
--   vehicle          차량 원장. 미등록·수배·대포차 판별의 기준
--   plate_read_log   번호판 인식 로그. 인식률 튜닝·오탐 분석용
--
-- violation 은 여기 없다 — ERD v1.0 결정 2번으로 event 테이블(V1)에 흡수됐다.
-- LPR 은 위반을 DB 가 아니라 b_gateway 로 HTTP 전송한다.
-- =====================================================================

-- ---------------------------------------------------------------------
-- 차량 원장 (수배/대포차 판별의 기준 테이블)
-- plate_no 는 지역명을 제외한 정규화 형태로 저장한다. 예) '12가3456'
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS vehicle (
    id             BIGINT AUTO_INCREMENT PRIMARY KEY,
    plate_no       VARCHAR(16)  NOT NULL COMMENT '정규화 번호판(지역명 제외)',
    owner_name     VARCHAR(64)      NULL COMMENT '소유자명',
    model          VARCHAR(64)      NULL COMMENT '차종',
    color          VARCHAR(24)      NULL COMMENT '색상',
    status         ENUM('registered','unregistered','stolen','wanted',
                        'fake_plate','impound','insurance_expired')
                   NOT NULL DEFAULT 'registered' COMMENT '차량 상태',
    registered_at  DATE             NULL COMMENT '등록일',
    memo           VARCHAR(255)     NULL COMMENT '비고(수배 사유 등)',
    created_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                       ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_vehicle_plate (plate_no),
    KEY idx_vehicle_status (status)
) ENGINE=InnoDB COMMENT='차량 원장';


-- ---------------------------------------------------------------------
-- 번호판 인식 로그 (인식률 튜닝 및 오탐 분석용)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS plate_read_log (
    id           BIGINT AUTO_INCREMENT PRIMARY KEY,
    cam_id       VARCHAR(32)  NOT NULL,
    track_id     INT          NOT NULL,
    plate_no     VARCHAR(16)      NULL COMMENT '보정 후',
    raw_text     VARCHAR(32)      NULL COMMENT 'OCR 원문',
    confidence   DECIMAL(4,3) NOT NULL DEFAULT 0.000,
    valid_format TINYINT(1)   NOT NULL DEFAULT 0,
    engine       VARCHAR(16)  NOT NULL DEFAULT 'easyocr',
    read_at      DATETIME(3)  NOT NULL,
    KEY idx_plate_log_time (read_at),
    KEY idx_plate_log_track (cam_id, track_id)
) ENGINE=InnoDB COMMENT='번호판 인식 로그';
