-- 카메라별로 낙하물(DEBRIS) 자동 감지를 켤지 여부.
-- true인 카메라는 a_core/camera_watcher.py가 자동으로 yolo_infer.py를 붙여서 돌린다.
ALTER TABLE camera
    ADD COLUMN debris_detection_enabled BOOLEAN NOT NULL DEFAULT FALSE;
