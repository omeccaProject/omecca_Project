"""차량 DB 대조 모듈."""
from .matcher import VehicleMatcher
from .repository import VehicleRepository, get_repository

__all__ = ["VehicleMatcher", "VehicleRepository", "get_repository"]
