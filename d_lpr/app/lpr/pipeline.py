"""LPR 파이프라인.

    차량 탐지(Detection) → 번호판 검출 → 전처리 → OCR → 보정
        → track_id별 다중 프레임 다수결 → 확정 번호판 발행

단일 프레임 OCR은 흔들린다. 같은 차량(track_id)에서 여러 프레임을 모아
가중 다수결로 확정하면 인식률이 눈에 띄게 올라간다.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Deque, Optional

from ..core.bus import TOPIC_PLATE, bus
from ..core.config import settings
from ..core.schemas import BBox, Detection, PlateResult
from . import plate_format as pf
from . import preprocess
from .detector import PlateDetector
from .recognizer import PlateRecognizer

log = logging.getLogger("omeca.lpr.pipeline")


@dataclass
class TrackVote:
    """track 하나에 대한 프레임별 인식 결과 누적."""

    votes: Deque[PlateResult] = field(default_factory=lambda: deque(maxlen=16))
    confirmed: Optional[str] = None
    confirmed_conf: float = 0.0
    last_seen: float = field(default_factory=time.time)

    def add(self, r: PlateResult) -> None:
        self.votes.append(r)
        self.last_seen = r.timestamp


class LPRPipeline:
    def __init__(
        self,
        detector: Optional[PlateDetector] = None,
        recognizer: Optional[PlateRecognizer] = None,
        vote_window: Optional[int] = None,
        publish: bool = True,
    ) -> None:
        cfg = settings.lpr
        self.detector = detector or PlateDetector()
        self.recognizer = recognizer or PlateRecognizer()
        self.vote_window = vote_window or cfg.vote_window
        self.min_conf = cfg.min_plate_conf
        self.publish = publish
        self._tracks: dict[tuple[str, int], TrackVote] = defaultdict(TrackVote)
        self.stats = {"frames": 0, "read": 0, "confirmed": 0, "rejected": 0, "too_small": 0}

    # ------------------------------------------------------------------
    def process(
        self,
        detection: Detection,
        frame: Any = None,
        hint: Optional[str] = None,
    ) -> Optional[PlateResult]:
        """차량 탐지 1건 처리. 확정된 번호판이 생기면 그 결과를 반환한다."""
        if not detection.is_vehicle():
            return None

        self.stats["frames"] += 1
        key = (detection.cam_id, detection.track_id)

        boxes = self.detector.detect(frame, detection.bbox)
        plate_bbox: Optional[BBox] = boxes[0] if boxes else None

        image = None
        if frame is not None and plate_bbox is not None:
            if plate_bbox.height < settings.lpr.min_plate_height:
                # 실측상 이보다 작으면 확대해도 자리정확도가 크게 떨어진다.
                # 차량이 더 가까워진 프레임에서 다시 시도하는 편이 낫다.
                self.stats["too_small"] = self.stats.get("too_small", 0) + 1
                return None
            image = preprocess.run(
                frame,
                plate_bbox.to_xyxy(),
                target_h=settings.lpr.upscale_height,
                deskew_limit=settings.lpr.deskew_limit,
                denoise_min_height=settings.lpr.denoise_min_height,
            ).image

        result = self.recognizer.read(
            image,
            bbox=plate_bbox,
            cam_id=detection.cam_id,
            track_id=detection.track_id,
            hint=hint,
        )
        if result is None:
            return None

        result.timestamp = detection.timestamp
        self.stats["read"] += 1

        if result.confidence < self.min_conf and not result.valid_format:
            self.stats["rejected"] += 1
            return None

        track = self._tracks[key]
        track.add(result)
        return self._try_confirm(key, track)

    # ------------------------------------------------------------------
    def _try_confirm(self, key: tuple[str, int], track: TrackVote) -> Optional[PlateResult]:
        """가중 다수결로 번호판 확정.

        - 포맷이 유효한 결과에 가산점
        - 신뢰도를 가중치로 사용
        - 같은 track에서 이미 확정된 값과 같으면 재발행하지 않는다
        """
        if len(track.votes) < min(self.vote_window, 2):
            return None

        recent = list(track.votes)[-self.vote_window:]
        scores: dict[str, float] = defaultdict(float)
        best_by_plate: dict[str, PlateResult] = {}

        for r in recent:
            canon = pf.canonical(r.plate_no)
            if not canon:
                continue
            w = r.confidence * (1.6 if r.valid_format else 0.7)
            scores[canon] += w
            prev = best_by_plate.get(canon)
            if prev is None or r.confidence > prev.confidence:
                best_by_plate[canon] = r

        if not scores:
            return None

        winner, score = max(scores.items(), key=lambda kv: kv[1])
        total = sum(scores.values())
        ratio = score / total if total else 0.0

        # 과반 지지 + 최소 득표 가중치를 넘어야 확정
        if ratio < 0.5 or score < self.min_conf * 2:
            return None
        if track.confirmed == winner:
            return None

        # 확정 신뢰도 = 승자 표들의 평균 OCR 신뢰도 × 득표 비율
        # (가중 점수를 그대로 쓰면 1.0을 넘어 확률로 해석할 수 없다)
        winner_votes = [r for r in recent if pf.canonical(r.plate_no) == winner]
        avg_conf = sum(r.confidence for r in winner_votes) / len(winner_votes)

        best = best_by_plate[winner]
        track.confirmed = winner
        track.confirmed_conf = round(min(1.0, avg_conf * (0.6 + 0.4 * ratio)), 4)
        self.stats["confirmed"] += 1

        final = PlateResult(
            plate_no=winner,
            confidence=track.confirmed_conf,
            bbox=best.bbox,
            raw_text=best.raw_text,
            valid_format=pf.is_valid(winner),
            plate_type=best.plate_type,
            cam_id=key[0],
            track_id=key[1],
            timestamp=best.timestamp,
            engine=best.engine,
        )
        if self.publish:
            bus.publish(TOPIC_PLATE, final.as_dict())
        return final

    # ------------------------------------------------------------------
    def confirmed_plate(self, cam_id: str, track_id: int) -> Optional[str]:
        """위반 감지 모듈이 track에 붙은 번호판을 조회할 때 사용."""
        t = self._tracks.get((cam_id, track_id))
        return t.confirmed if t else None

    def confidence_of(self, cam_id: str, track_id: int) -> float:
        t = self._tracks.get((cam_id, track_id))
        return t.confirmed_conf if t else 0.0

    def prune(self, ttl_sec: float = 300.0, now: Optional[float] = None) -> int:
        """오래된 track 정리. 장시간 운용 시 메모리 누수를 막는다."""
        now = now or time.time()
        stale = [k for k, v in self._tracks.items() if now - v.last_seen > ttl_sec]
        for k in stale:
            del self._tracks[k]
        return len(stale)

    def reset(self) -> None:
        self._tracks.clear()
        for k in self.stats:
            self.stats[k] = 0
