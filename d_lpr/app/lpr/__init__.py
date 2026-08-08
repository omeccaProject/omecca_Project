"""번호판 인식(LPR) 모듈."""
from .detector import PlateDetector
from .pipeline import LPRPipeline
from .recognizer import PlateRecognizer

__all__ = ["PlateDetector", "PlateRecognizer", "LPRPipeline"]
