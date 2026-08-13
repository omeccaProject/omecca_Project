"""모듈 A 탐지 클래스 정의 — 단일 진실 공급원(Single Source of Truth).
다른 파일에서 클래스 목록을 하드코딩하지 말고 반드시 여기서 import할 것."""

# road_hazard.pt (현재 v3) 가 출력하는 낙하물·방치물 클래스
DEBRIS_CLASSES = {
    "electric_scooter",
    "traffic_cone",
    "road_debris",
}

# 흉기 클래스 (모델 학습 예정 — 학습 완료 후 실제 클래스명으로 갱신)
WEAPON_CLASSES = {
    "knife",
    "blunt_weapon",
}

# ERD detected_class 필드 ↔ 화면 표시용 한글명
CLASS_DISPLAY_KO = {
    "electric_scooter": "공유 킥보드",
    "traffic_cone": "라바콘",
    "road_debris": "도로 낙하물",
    "knife": "칼",
    "blunt_weapon": "둔기",
}