-- 관심 대상(target) 등록 시 차량 색상/차종을 구체적으로(예: 아반떼CN7) 기록할 수 있도록
-- color, vehicle_model 컬럼을 추가한다. 이미 schema.sql로 처음부터 새로 만든 DB라면
-- 이 스크립트는 필요 없다 - 기존 DB에 이미 target 테이블이 있는 경우에만 실행.
ALTER TABLE target
    ADD COLUMN color VARCHAR(30) NULL COMMENT '차량 색상 (VEHICLE 전용)' AFTER label,
    ADD COLUMN vehicle_model VARCHAR(50) NULL COMMENT '차종 - 브랜드/모델/트림 (VEHICLE 전용, 예: 아반떼CN7)' AFTER color;
