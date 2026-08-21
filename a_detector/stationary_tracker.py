import time
from hazard_classes import DEBRIS_CLASSES

def calc_iou(box1, box2):
    """두 박스가 얼마나 겹치는지 계산 (0~1). 같은 물체인지 판단하는 용도"""
    x1 = max(box1[0], box2[0])
    y1 = max(box1[1], box2[1])
    x2 = min(box1[2], box2[2])
    y2 = min(box1[3], box2[3])

    inter_area = max(0, x2 - x1) * max(0, y2 - y1)
    if inter_area == 0:
        return 0.0

    box1_area = (box1[2] - box1[0]) * (box1[3] - box1[1])
    box2_area = (box2[2] - box2[0]) * (box2[3] - box2[1])
    union_area = box1_area + box2_area - inter_area

    return inter_area / union_area


class StationaryObjectTracker:
    def __init__(self, threshold_sec=10, iou_threshold=0.5):
        self.threshold_sec = threshold_sec
        self.iou_threshold = iou_threshold
        self.candidates = {}  # {id: {"bbox": [...], "first_seen": ts, "last_seen": ts}}
        self.next_id = 0
        self.already_alerted = set()

    def update(self, detections, now, frame=None):
        """frame(선택): 현재 프레임 원본. 넘겨주면 후보가 처음 등록되는 순간의 프레임을
        "사건 발생 전" 이미지로 같이 저장해뒀다가, 이 후보가 실제 이벤트로 확정되는 시점에
        이벤트 dict에 "before_frame"으로 실어 반환한다(호출부가 파일로 저장해 frameRefBefore로
        쓸 수 있게) - 기존 호출부(frame 없이 부르던 코드)와도 그대로 호환된다."""
        events = []
        current_dets = [d for d in detections if d["class"] in DEBRIS_CLASSES]

        matched_ids = set()

        for det in current_dets:
            best_match_id = None
            best_iou = 0
            for cand_id, cand in self.candidates.items():
                iou = calc_iou(det["bbox"], cand["bbox"])
                if iou > self.iou_threshold and iou > best_iou:
                    best_iou = iou
                    best_match_id = cand_id

            if best_match_id is not None:
                self.candidates[best_match_id]["bbox"] = det["bbox"]
                self.candidates[best_match_id]["last_seen"] = now
                self.candidates[best_match_id]["class"] = det["class"]
                matched_ids.add(best_match_id)

                duration = now - self.candidates[best_match_id]["first_seen"]

                # ★추가: 진행 상황 로그 (2초 단위로만 찍어서 너무 시끄럽지 않게)
                if int(duration) % 2 == 0:
                    print(f"  ⏱️  후보 추적 중: {det['class']} · {duration:.1f}초 / {self.threshold_sec}초")

                if duration >= self.threshold_sec and best_match_id not in self.already_alerted:
                    self.already_alerted.add(best_match_id)
                    events.append({
                        "event": "abandoned_object",
                        "class": det["class"],
                        "bbox": det["bbox"],
                        "duration_sec": round(duration, 1),
                        "confidence": det["confidence"],
                        "before_frame": self.candidates[best_match_id].get("first_frame"),
                    })
            else:
                self.candidates[self.next_id] = {
                    "bbox": det["bbox"],
                    "class": det["class"],
                    "first_seen": now,
                    "last_seen": now,
                    "first_frame": frame.copy() if frame is not None else None,
                }
                print(f"  🆕 낙하물 후보 등록: {det['class']} (conf={det['confidence']})")
                matched_ids.add(self.next_id)
                self.next_id += 1

        stale_ids = [
            cid for cid, cand in self.candidates.items()
            if now - cand["last_seen"] > 3 and cid not in matched_ids
        ]
        for cid in stale_ids:
            print(f"  ❌ 후보 소멸: {self.candidates[cid]['class']} (화면에서 사라짐)")
            del self.candidates[cid]
            self.already_alerted.discard(cid)

        return events