"""임시 차량 검출기 + 추적기.

정식 파이프라인에서 차량 검출·추적은 김관용(detector/)·김준호(tracking/) 담당이다.
이 모듈은 **그 모듈이 붙기 전에 혼자 위반 판정을 검증하기 위한 임시 대역**이다.
출력이 공통 규격(`Detection`)이므로, 나중에 팀 모듈로 갈아 끼울 때
`ViolationEngine` 쪽은 한 줄도 고치지 않아도 된다.

동작
    ultralytics YOLO 기본 모델(yolo11n.pt)로 차량을 잡고,
    가능하면 ByteTrack(내장)으로 ID를 유지한다.
    ByteTrack 을 못 쓰는 환경이면 IoU 기반 간이 추적기로 자동 대체한다.
"""

from __future__ import annotations

import logging
from typing import Any, Iterator, Optional

from ..core.schemas import BBox, Detection, ObjectClass

log = logging.getLogger("omeca.violation.vehicle_track")

# COCO 클래스 번호 → 우리 규격
COCO_VEHICLE = {2: ObjectClass.CAR, 5: ObjectClass.BUS,
                7: ObjectClass.TRUCK, 3: ObjectClass.MOTORCYCLE}


# ==========================================================================
class IoUTracker:
    """IoU 기반 간이 추적기.

    프레임 간 겹침이 가장 큰 박스끼리 이어 붙인다. 교차로 정지 영상처럼
    프레임률이 안정적이고 가림이 심하지 않은 구간에서는 충분히 쓸 만하다.
    가림이 잦으면 ByteTrack 쪽이 낫다.
    """

    def __init__(self, iou_threshold: float = 0.3, max_missing: int = 12) -> None:
        self.iou_threshold = iou_threshold
        self.max_missing = max_missing
        self._next_id = 1
        # track_id -> [bbox, 마지막으로 본 프레임]
        self._alive: dict[int, list[Any]] = {}

    def update(self, boxes: list[BBox], frame_no: int) -> list[int]:
        for tid in [t for t, (_, seen) in self._alive.items()
                    if frame_no - seen > self.max_missing]:
            del self._alive[tid]

        assigned: dict[int, int] = {}       # box index -> track_id
        used: set[int] = set()
        pairs = []
        for bi, b in enumerate(boxes):
            for tid, (tb, _) in self._alive.items():
                iou = b.iou(tb)
                if iou >= self.iou_threshold:
                    pairs.append((iou, bi, tid))
        for iou, bi, tid in sorted(pairs, key=lambda x: -x[0]):
            if bi in assigned or tid in used:
                continue
            assigned[bi] = tid
            used.add(tid)

        out = []
        for bi, b in enumerate(boxes):
            tid = assigned.get(bi)
            if tid is None:
                tid = self._next_id
                self._next_id += 1
            self._alive[tid] = [b, frame_no]
            out.append(tid)
        return out


# ==========================================================================
class VehicleSource:
    """영상 파일 → `Detection` 스트림."""

    def __init__(
        self,
        video: str,
        cam_id: str = "CAM-TEST",
        weights: str = "yolo11n.pt",
        conf: float = 0.35,
        stride: int = 1,
        use_bytetrack: bool = True,
        imgsz: int = 960,
    ) -> None:
        self.video = video
        self.cam_id = cam_id
        self.conf = conf
        self.stride = max(1, stride)
        self.imgsz = imgsz
        self.fps = 30.0
        self.size = (0, 0)
        self.total = 0
        self.tracker_name = ""
        self._fallback = IoUTracker()

        from ultralytics import YOLO      # 지연 임포트 (없어도 다른 기능은 돈다)

        self.model = YOLO(weights)
        self.use_bytetrack = use_bytetrack

    # ------------------------------------------------------------------
    def frames(self) -> Iterator[tuple[int, float, Any, list[Detection]]]:
        """(frame_no, ts, frame, detections) 를 순서대로 내보낸다.

        ts 는 영상 시작을 0초로 하는 상대 시각이다. 신호 타임라인과 맞춘다.
        """
        import cv2

        cap = cv2.VideoCapture(self.video)
        if not cap.isOpened():
            raise RuntimeError(f"영상을 열 수 없습니다: {self.video}")
        self.fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        self.size = (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                     int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
        self.total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        frame_no = -1
        try:
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                frame_no += 1
                if frame_no % self.stride:
                    continue
                ts = frame_no / self.fps
                yield frame_no, ts, frame, self._detect(frame, frame_no, ts)
        finally:
            cap.release()

    # ------------------------------------------------------------------
    def _detect(self, frame, frame_no: int, ts: float) -> list[Detection]:
        if self.use_bytetrack:
            try:
                res = self.model.track(frame, persist=True, verbose=False,
                                       conf=self.conf, imgsz=self.imgsz,
                                       classes=list(COCO_VEHICLE),
                                       tracker="bytetrack.yaml")[0]
                self.tracker_name = "bytetrack"
                return self._from_result(res, frame_no, ts, tracked=True)
            except Exception as e:
                log.warning("ByteTrack 사용 불가(%s) → IoU 간이 추적기로 대체", e)
                self.use_bytetrack = False

        res = self.model.predict(frame, verbose=False, conf=self.conf,
                                 imgsz=self.imgsz, classes=list(COCO_VEHICLE))[0]
        self.tracker_name = "iou"
        return self._from_result(res, frame_no, ts, tracked=False)

    def _from_result(self, res, frame_no: int, ts: float, tracked: bool) -> list[Detection]:
        boxes = getattr(res, "boxes", None)
        if boxes is None or len(boxes) == 0:
            return []

        xyxy = boxes.xyxy.tolist()
        clses = [int(c) for c in boxes.cls.tolist()]
        confs = [float(c) for c in boxes.conf.tolist()]

        bbs = [BBox(*map(float, b)) for b in xyxy]
        if tracked and getattr(boxes, "id", None) is not None:
            ids = [int(i) for i in boxes.id.tolist()]
        else:
            ids = self._fallback.update(bbs, frame_no)

        out = []
        for bb, cls, cf, tid in zip(bbs, clses, confs, ids):
            oc = COCO_VEHICLE.get(cls)
            if oc is None:
                continue
            out.append(Detection(cam_id=self.cam_id, track_id=tid, cls=oc,
                                 bbox=bb, timestamp=ts, confidence=cf,
                                 frame_no=frame_no))
        return out
