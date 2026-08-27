-- 카메라별로 불법유턴/신호위반 감지를 각각 켤 수 있도록 분리.
-- true인 카메라는 a_core/camera_watcher.py가 해당 위반 모드로 d_lpr/run_uturn.py를 실행한다.
ALTER TABLE camera
    ADD COLUMN uturn_detection_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN signal_detection_enabled BOOLEAN NOT NULL DEFAULT FALSE;

UPDATE camera
SET uturn_detection_enabled = TRUE,
    signal_detection_enabled = TRUE
WHERE violation_detection_enabled = TRUE;
