"""테스트 공통 픽스처.

모든 테스트는 인메모리 SQLite를 쓰므로 실제 DB나 파일을 건드리지 않는다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.bus import bus  # noqa: E402
from app.lpr.pipeline import LPRPipeline  # noqa: E402
from app.lpr.recognizer import PlateRecognizer  # noqa: E402
from app.vehicle.matcher import VehicleMatcher  # noqa: E402
from app.vehicle.repository import VehicleRepository, reset_repository  # noqa: E402
from app.violation.engine import ViolationEngine  # noqa: E402
from app.violation.roi import ZoneRegistry, default_registry  # noqa: E402
from app.violation.signal_state import ManualSignal, SignalPhase  # noqa: E402


@pytest.fixture
def repo():
    r = VehicleRepository(driver="sqlite", sqlite_path=":memory:")
    reset_repository(r)
    yield r
    reset_repository(None)


@pytest.fixture
def matcher(repo):
    return VehicleMatcher(repo=repo)


@pytest.fixture
def signal():
    return ManualSignal(default=SignalPhase.GREEN)


@pytest.fixture
def zones():
    return ZoneRegistry.load(Path(__file__).resolve().parents[1] / "config_zones.json")


@pytest.fixture
def engine(repo, signal, zones):
    bus.clear()
    lpr = LPRPipeline(recognizer=PlateRecognizer(mock=True), publish=False)
    e = ViolationEngine(
        zones=zones, signal_provider=signal, lpr=lpr,
        matcher=VehicleMatcher(repo=repo), repo=repo,
    )
    e.lpr.recognizer.set_mock_plates(repo.all_plates())
    return e


@pytest.fixture(autouse=True)
def _clear_bus():
    bus.clear()
    yield
    bus.clear()
