-- C파트(수배자/흉기) 자동 감지 사용 여부 컬럼 추가.
-- camera_watcher.py가 이 값을 보고 test_run.py를 자동으로 켜고 끈다
-- (V6__camera_violation_split.sql의 uturn/signal 분리와 동일한 패턴).
ALTER TABLE camera
    ADD COLUMN person_risk_detection_enabled BOOLEAN NOT NULL DEFAULT FALSE;