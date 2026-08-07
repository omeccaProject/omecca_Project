"""공통 데이터 규격.

팀 전체가 공유하는 탐지 결과 규격(cam_id, track_id, class, bbox, timestamp)을
기준으로 하며, 여기에 LPR / 위반 감지 결과 타입을 추가로 정의한다.

의존성: 표준 라이브러리만 사용 (pydantic 없이도 동작하도록 dataclass 기반)
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Optional, Sequence


# --------------------------------------------------------------------------
# 공통 탐지 규격 (김관용 담당 detector/ 모듈에서 넘어오는 입력)
# --------------------------------------------------------------------------

class ObjectClass(str, Enum):
    PERSON = "person"
    CAR = "car"
    BUS = "bus"
    TRUCK = "truck"
    MOTORCYCLE = "motorcycle"
    PLATE = "plate"
    UNKNOWN = "unknown"


VEHICLE_CLASSES = {
    ObjectClass.CAR,
    ObjectClass.BUS,
    ObjectClass.TRUCK,
    ObjectClass.MOTORCYCLE,
}


@dataclass
class BBox:
    """좌상단(x1, y1) / 우하단(x2, y2) 픽셀 좌표."""

    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def width(self) -> float:
        return max(0.0, self.x2 - self.x1)

    @property
    def height(self) -> float:
        return max(0.0, self.y2 - self.y1)

    @property
    def area(self) -> float:
        return self.width * self.height

    @property
    def center(self) -> tuple[float, float]:
        return ((self.x1 + self.x2) / 2.0, (self.y1 + self.y2) / 2.0)

    @property
    def bottom_center(self) -> tuple[float, float]:
        """차량 접지점. 궤적 판정은 바닥 중심을 쓰는 편이 왜곡이 적다."""
        return ((self.x1 + self.x2) / 2.0, self.y2)

    def to_xyxy(self) -> tuple[int, int, int, int]:
        return int(self.x1), int(self.y1), int(self.x2), int(self.y2)

    def iou(self, other: "BBox") -> float:
        ix1, iy1 = max(self.x1, other.x1), max(self.y1, other.y1)
        ix2, iy2 = min(self.x2, other.x2), min(self.y2, other.y2)
        inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
        union = self.area + other.area - inter
        return inter / union if union > 0 else 0.0

    def contains(self, point: Sequence[float]) -> bool:
        x, y = point[0], point[1]
        return self.x1 <= x <= self.x2 and self.y1 <= y <= self.y2


@dataclass
class Detection:
    """전 모듈 공통 탐지 결과 규격."""

    cam_id: str
    track_id: int
    cls: ObjectClass
    bbox: BBox
    timestamp: float = field(default_factory=time.time)
    confidence: float = 1.0
    frame_no: int = 0

    def is_vehicle(self) -> bool:
        return self.cls in VEHICLE_CLASSES


# --------------------------------------------------------------------------
# LPR 결과
# --------------------------------------------------------------------------

@dataclass
class PlateResult:
    """번호판 인식 결과."""

    plate_no: str                       # 정규화된 번호판 문자열 ("12가3456")
    confidence: float                   # 0.0 ~ 1.0
    bbox: Optional[BBox] = None         # 원본 프레임 기준 번호판 영역
    raw_text: str = ""                  # OCR 원문 (보정 전)
    valid_format: bool = False          # 한국형 번호판 포맷 통과 여부
    plate_type: str = "unknown"         # 신형/구형/영업용 등
    cam_id: str = ""
    track_id: int = -1
    timestamp: float = field(default_factory=time.time)
    engine: str = "easyocr"             # easyocr | mock

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["bbox"] = self.bbox.to_xyxy() if self.bbox else None
        return d


# --------------------------------------------------------------------------
# 차량 DB 대조 결과
# --------------------------------------------------------------------------

class RiskLevel(str, Enum):
    NORMAL = "normal"        # 정상 등록 차량
    CAUTION = "caution"      # 주의 (보험 만료, 검사 미필 등)
    HIGH = "high"            # 고위험 (대포차, 수배, 미등록)


class VehicleStatus(str, Enum):
    REGISTERED = "registered"        # 정상 등록
    UNREGISTERED = "unregistered"    # DB 미등록
    STOLEN = "stolen"                # 도난 신고
    WANTED = "wanted"                # 수배 차량
    FAKE_PLATE = "fake_plate"        # 대포차 (명의 불일치)
    IMPOUND = "impound"              # 압류/영치 대상
    INSURANCE_EXPIRED = "insurance_expired"


HIGH_RISK_STATUS = {
    VehicleStatus.UNREGISTERED,
    VehicleStatus.STOLEN,
    VehicleStatus.WANTED,
    VehicleStatus.FAKE_PLATE,
}


@dataclass
class VehicleRecord:
    """vehicle 테이블 레코드."""

    plate_no: str
    owner_name: str = ""
    model: str = ""
    color: str = ""
    status: VehicleStatus = VehicleStatus.REGISTERED
    registered_at: str = ""
    memo: str = ""

    @property
    def risk_level(self) -> RiskLevel:
        if self.status in HIGH_RISK_STATUS:
            return RiskLevel.HIGH
        if self.status in (VehicleStatus.IMPOUND, VehicleStatus.INSURANCE_EXPIRED):
            return RiskLevel.CAUTION
        return RiskLevel.NORMAL


@dataclass
class VehicleMatch:
    """번호판 → DB 대조 결과."""

    plate_no: str
    matched: bool
    record: Optional[VehicleRecord]
    status: VehicleStatus
    risk_level: RiskLevel
    fuzzy: bool = False          # 유사 매칭(1글자 오차 보정)으로 찾았는지
    matched_plate: str = ""      # fuzzy 매칭 시 실제 DB 번호판
    cam_id: str = ""
    track_id: int = -1
    timestamp: float = field(default_factory=time.time)


# --------------------------------------------------------------------------
# 위반 이벤트
# --------------------------------------------------------------------------

class ViolationType(str, Enum):
    RED_LIGHT = "red_light"           # 신호 위반
    ILLEGAL_UTURN = "illegal_uturn"   # 불법 유턴
    HIGH_RISK_VEHICLE = "high_risk_vehicle"   # 고위험(대포차/수배) 차량 감지


VIOLATION_LABEL_KO = {
    ViolationType.RED_LIGHT: "신호 위반",
    ViolationType.ILLEGAL_UTURN: "불법 유턴",
    ViolationType.HIGH_RISK_VEHICLE: "고위험 차량",
}


@dataclass
class ViolationEvent:
    """관제 화면 / 증거 리포트로 전달되는 위반 이벤트."""

    violation_type: ViolationType
    cam_id: str
    track_id: int
    timestamp: float = field(default_factory=time.time)
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    plate_no: str = ""
    plate_confidence: float = 0.0
    risk_level: RiskLevel = RiskLevel.NORMAL
    vehicle_status: VehicleStatus = VehicleStatus.REGISTERED
    zone_id: str = ""
    detail: str = ""
    evidence_frames: list[int] = field(default_factory=list)
    trajectory: list[tuple[float, float]] = field(default_factory=list)
    location: Optional[tuple[float, float]] = None   # (lat, lon)

    @property
    def label(self) -> str:
        return VIOLATION_LABEL_KO.get(self.violation_type, self.violation_type.value)

    def to_payload(self) -> dict[str, Any]:
        """WebSocket / REST 전송용 직렬화.

        장성혁 담당 gateway/ 모듈의 event 테이블 규격에 맞춘 평면 구조.
        """
        return {
            "event_id": self.event_id,
            "type": self.violation_type.value,
            "label": self.label,
            "cam_id": self.cam_id,
            "track_id": self.track_id,
            "timestamp": self.timestamp,
            "plate_no": self.plate_no,
            "plate_confidence": round(self.plate_confidence, 3),
            "risk_level": self.risk_level.value,
            "vehicle_status": self.vehicle_status.value,
            "zone_id": self.zone_id,
            "detail": self.detail,
            "evidence_frames": self.evidence_frames,
            "trajectory": [[round(x, 1), round(y, 1)] for x, y in self.trajectory],
            "location": list(self.location) if self.location else None,
        }
