"""설정 로더.

환경변수 > config.yaml > 기본값 순으로 적용된다.
PyYAML이 없거나 config.yaml이 없어도 기본값으로 동작한다.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[2]
CONFIG_PATH = Path(os.environ.get("OMECA_CONFIG", BASE_DIR / "config.yaml"))


def _load_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    if path.suffix in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore
        except ImportError:
            return _naive_yaml(text)
        return yaml.safe_load(text) or {}
    return json.loads(text)


def _naive_yaml(text: str) -> dict[str, Any]:
    """PyYAML 미설치 환경용 최소 파서 (1 depth key: value만 지원)."""
    out: dict[str, Any] = {}
    section: dict[str, Any] | None = None
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        key, _, raw = line.strip().partition(":")
        val = raw.strip()
        parsed: Any
        if val == "":
            parsed = {}
        elif val.lower() in ("true", "false"):
            parsed = val.lower() == "true"
        else:
            try:
                parsed = int(val)
            except ValueError:
                try:
                    parsed = float(val)
                except ValueError:
                    parsed = val.strip("\"'")
        if indent == 0:
            if isinstance(parsed, dict):
                section = parsed
                out[key] = section
            else:
                out[key] = parsed
                section = None
        elif section is not None:
            section[key] = parsed
    return out


def _env(key: str, default: Any) -> Any:
    raw = os.environ.get(key)
    if raw is None:
        return default
    if isinstance(default, bool):
        return raw.lower() in ("1", "true", "yes", "y", "on")
    if isinstance(default, int):
        return int(raw)
    if isinstance(default, float):
        return float(raw)
    return raw


@dataclass
class DBConfig:
    # driver: sqlite (로컬/모의) | mysql (실 운영)
    driver: str = "sqlite"
    sqlite_path: str = str(BASE_DIR / "data" / "omeca.db")
    host: str = "localhost"
    port: int = 3306
    user: str = "omeca"
    password: str = "omeca"
    database: str = "omeca"


@dataclass
class LPRConfig:
    # mock=True 이면 YOLO/EasyOCR 없이 더미 결과로 파이프라인 전체를 시연할 수 있다.
    mock: bool = True
    ocr_lang: list[str] = field(default_factory=lambda: ["ko", "en"])
    gpu: bool = False
    # 실측 신뢰도 분포 기준: 0.40 에서 통과율 82% / 통과분 정확도 0.957 / 놓친 정답 0건
    min_plate_conf: float = 0.40          # 최소 인식 신뢰도
    structured_ocr: bool = True           # 자리별 allowlist 2패스 인식 사용
    min_plate_area: int = 400             # 번호판 후보 최소 면적(px)
    # 한국 번호판은 규격이 여러 가지다. 실측(AI Hub 안양 CCTV 18,890개) 결과
    # 335형(가로/세로 약 2.1)이 74%로 가장 많고, 520형(4.7)은 13%뿐이었다.
    # 4.7만 가정하면 실제 번호판의 대부분을 놓친다.
    plate_ar_range: tuple[float, float] = (1.3, 6.5)
    # 전체 프레임에서 찾을 때 번호판이 차지할 수 있는 높이 비율 (프레임 높이 대비)
    frame_plate_h_range: tuple[float, float] = (0.004, 0.07)
    frame_plate_w_max: float = 0.12       # 프레임 폭 대비 최대
    # 아래 세 값은 합성 데이터 실측으로 정했다 (python bench_lpr.py 로 재현)
    upscale_height: int = 96              # OCR 입력 높이 정규화
    deskew_limit: float = 35.0            # 기울기 보정 최대 각도 (35도까지 실측 유효)
    denoise_min_height: int = 28          # 이보다 작은 번호판은 잡음 제거 생략
    min_plate_height: int = 24            # 신뢰할 만한 인식이 가능한 최소 높이
    fuzzy_match: bool = True              # 1글자 오차 유사 매칭 허용
    vote_window: int = 5                  # 동일 track에서 프레임 다수결 창 크기


@dataclass
class ViolationConfig:
    zones_path: str = str(BASE_DIR / "config_zones.json")
    track_history: int = 120              # track별 궤적 보관 프레임 수
    uturn_angle_deg: float = 150.0        # 유턴 판정 진입/진출 방향 최소 각도차
    uturn_min_points: int = 8             # 유턴 판정 최소 궤적 포인트
    uturn_min_speed: float = 1.0          # 정지 차량 오탐 방지용 최소 이동량(px/frame)
    redlight_grace_sec: float = 0.3       # 신호 전환 직후 유예 시간
    cooldown_sec: float = 10.0            # 동일 track 동일 위반 재발행 방지
    min_cross_speed: float = 0.5          # 라인 통과 인정 최소 이동량


@dataclass
class ServerConfig:
    host: str = "0.0.0.0"
    port: int = 8010
    cors_origins: str = "*"


@dataclass
class Settings:
    db: DBConfig = field(default_factory=DBConfig)
    lpr: LPRConfig = field(default_factory=LPRConfig)
    violation: ViolationConfig = field(default_factory=ViolationConfig)
    server: ServerConfig = field(default_factory=ServerConfig)

    @classmethod
    def load(cls, path: Path | None = None) -> "Settings":
        raw = _load_file(path or CONFIG_PATH)
        s = cls()
        for section_name, section in raw.items():
            target = getattr(s, section_name, None)
            if target is None or not isinstance(section, dict):
                continue
            for k, v in section.items():
                if hasattr(target, k):
                    setattr(target, k, v)

        # 환경변수 오버라이드
        s.lpr.mock = _env("OMECA_LPR_MOCK", s.lpr.mock)
        s.db.driver = _env("OMECA_DB_DRIVER", s.db.driver)
        s.db.host = _env("OMECA_DB_HOST", s.db.host)
        s.db.port = _env("OMECA_DB_PORT", s.db.port)
        s.db.user = _env("OMECA_DB_USER", s.db.user)
        s.db.password = _env("OMECA_DB_PASSWORD", s.db.password)
        s.db.database = _env("OMECA_DB_NAME", s.db.database)
        s.server.port = _env("OMECA_PORT", s.server.port)
        return s


settings = Settings.load()
