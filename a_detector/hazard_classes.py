# a_detector/hazard_classes.py
"""
통합 낙하물/흉기 모델(road_hazard_v1)의 클래스 목록.
yolo_infer.py, stationary_tracker.py가 공통으로 참조.
"""

DEBRIS_CLASSES = {"electric_scooter", "car_tire", "box", "traffic_cone", "fallen_tree"}
WEAPON_CLASSES = {"knife", "blunt_weapon"}