# a_detector/hazard_classes.py
"""
낙하물 모델(road_hazard_v2)의 클래스 목록.
흉기는 별도 모델로 분리 → weapon_classes.py에서 관리 예정.
"""

DEBRIS_CLASSES = {"electric_scooter", "traffic_cone", "road_debris"}
WEAPON_CLASSES = {"knife", "blunt_weapon"}   # 별도 모델용, 유지