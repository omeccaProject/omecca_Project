-- =====================================================================
-- 오메카3 스마트 관제 시스템 - 박지원 담당 테이블 (vehicle / violation)
-- MySQL 8.0 기준
-- =====================================================================

CREATE DATABASE IF NOT EXISTS omeca
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE omeca;

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
-- 위반 이벤트 (신호위반 / 불법유턴 / 고위험 차량)
-- 장성혁 담당 event 테이블과 event_id 로 연결된다.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS violation (
    id               BIGINT AUTO_INCREMENT PRIMARY KEY,
    event_id         CHAR(16)     NOT NULL COMMENT '이벤트 고유 ID',
    violation_type   ENUM('red_light','illegal_uturn','high_risk_vehicle')
                     NOT NULL,
    cam_id           VARCHAR(32)  NOT NULL,
    track_id         INT          NOT NULL COMMENT 'ByteTrack 객체 ID',
    -- vehicle.plate_no 에 대한 FK를 걸지 않는다.
    -- 미등록 차량 감지가 핵심 기능이라 원장에 없는 번호판도 기록되어야 한다.
    plate_no         VARCHAR(16)      NULL,
    plate_confidence DECIMAL(4,3) NOT NULL DEFAULT 0.000,
    vehicle_status   VARCHAR(24)      NULL COMMENT '대조 시점의 차량 상태',
    risk_level       ENUM('normal','caution','high') NOT NULL DEFAULT 'normal',
    zone_id          VARCHAR(32)      NULL COMMENT '가상 라인/ROI 식별자',
    detail           VARCHAR(255)     NULL COMMENT '판정 근거 요약',
    occurred_at      DATETIME(3)  NOT NULL,
    lat              DECIMAL(10,7)    NULL,
    lon              DECIMAL(10,7)    NULL,
    report_path      VARCHAR(255)     NULL COMMENT 'PDF 증거 리포트 경로',
    created_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_violation_event (event_id),
    KEY idx_violation_time (occurred_at),
    KEY idx_violation_type_time (violation_type, occurred_at),
    KEY idx_violation_plate (plate_no),
    KEY idx_violation_cam (cam_id, occurred_at)
) ENGINE=InnoDB COMMENT='차량 위반 이벤트';

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

-- ---------------------------------------------------------------------
-- 통계용 뷰: 위반 유형별 일자 집계
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW v_violation_daily AS
SELECT DATE(occurred_at)        AS d,
       violation_type,
       COUNT(*)                 AS cnt,
       SUM(risk_level = 'high') AS high_risk_cnt
FROM violation
GROUP BY DATE(occurred_at), violation_type;
