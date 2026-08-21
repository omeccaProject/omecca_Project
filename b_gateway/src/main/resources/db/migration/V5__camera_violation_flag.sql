-- 카메라별로 위반감지(신호위반/불법유턴)를 켤지 여부.
-- true인 카메라는 a_core/camera_watcher.py가 자동으로 d_lpr/run_uturn.py를 붙여서 돌린다.
ALTER TABLE camera
    ADD COLUMN violation_detection_enabled BOOLEAN NOT NULL DEFAULT FALSE;