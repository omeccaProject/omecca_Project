"""ROI(가상 라인) 그리기 도구.

영상의 첫 프레임을 띄워 놓고 마우스로 두 점을 찍으면 가상 라인이 만들어지고,
`config_zones.json` 에 저장된다. 좌표는 화면 축소와 무관하게 **원본 해상도**로
저장하므로, 4K 영상을 노트북 화면에서 그려도 그대로 쓸 수 있다.

사용법
    python draw_roi.py --video 영상.mp4 --cam CAM-TEST
    python draw_roi.py --image 첫프레임.jpg --cam CAM-TEST

조작
    1  중앙선 · 유턴 금지   (line_type=center, uturn_allowed=false)
    2  중앙선 · 유턴 허용   (line_type=center, uturn_allowed=true)
    3  정지선               (line_type=stop)
    4  진출선               (line_type=exit)
    마우스 좌클릭 2번  →  선 하나 완성
    z  마지막 선 취소
    r  전부 지우기
    w  저장하고 종료
    q  저장하지 않고 종료

유턴만 볼 거라면 1번(또는 2번) 하나만 그으면 된다.
중앙선은 **차량이 넘어가는 그 노란 실선** 위에 긋는다. 길게 그을수록 좋다.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
ZONES = BASE / "config_zones.json"

# 화면에 띄울 최대 크기 (원본이 크면 축소해서 보여준다)
MAX_W, MAX_H = 1280, 720

LINE_KINDS = {
    ord("1"): ("center", False, "중앙선 · 유턴 금지", (0, 215, 255)),
    ord("2"): ("center", True, "중앙선 · 유턴 허용", (0, 255, 255)),
    ord("3"): ("stop", False, "정지선", (255, 255, 255)),
    ord("4"): ("exit", False, "진출선", (180, 180, 180)),
}


def imread_unicode(path: str):
    """한글 경로 대응 이미지 읽기 (cv2.imread 는 Windows 한글 경로에서 실패한다)."""
    import cv2
    import numpy as np

    buf = np.fromfile(path, dtype=np.uint8)
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)


def first_frame(video: str):
    import cv2

    cap = cv2.VideoCapture(video)
    if not cap.isOpened():
        sys.exit(f"영상을 열 수 없습니다: {video}")
    ok, frame = cap.read()
    cap.release()
    if not ok:
        sys.exit("첫 프레임을 읽지 못했습니다.")
    return frame


# --------------------------------------------------------------------------
class Drawer:
    def __init__(self, frame, cam_id: str) -> None:
        import cv2

        self.cv2 = cv2
        self.frame = frame
        self.cam_id = cam_id
        h, w = frame.shape[:2]
        self.scale = min(MAX_W / w, MAX_H / h, 1.0)
        self.view = (cv2.resize(frame, None, fx=self.scale, fy=self.scale)
                     if self.scale < 1.0 else frame.copy())
        self.kind = LINE_KINDS[ord("1")]      # 기본값: 중앙선 · 유턴 금지
        self.pending: list[tuple[int, int]] = []
        self.hover: tuple[int, int] = (0, 0)
        self.lines: list[dict] = []
        print(f"원본 해상도 {w}x{h} / 표시 배율 {self.scale:.2f}")

    # ------------------------------------------------------------------
    def to_origin(self, pt) -> list[int]:
        return [int(round(pt[0] / self.scale)), int(round(pt[1] / self.scale))]

    def on_mouse(self, event, x, y, flags, param) -> None:
        cv2 = self.cv2
        if event == cv2.EVENT_MOUSEMOVE:
            self.hover = (x, y)
        elif event == cv2.EVENT_LBUTTONDOWN:
            self.pending.append((x, y))
            if len(self.pending) == 2:
                self.add_line()

    def add_line(self) -> None:
        line_type, allowed, label, color = self.kind
        prefix = {"center": "center", "stop": "stop", "exit": "exit"}[line_type]
        n = sum(1 for l in self.lines if l["line_type"] == line_type) + 1
        self.lines.append({
            "line_id": f"{prefix}_{n}",
            "name": label,
            "p1": self.to_origin(self.pending[0]),
            "p2": self.to_origin(self.pending[1]),
            "direction": "both",
            "line_type": line_type,
            "uturn_allowed": allowed,
            "signal_id": "SIG-1",
            "_view": [self.pending[0], self.pending[1]],
            "_color": color,
        })
        print(f"  + {self.lines[-1]['line_id']}  {label}  "
              f"{self.lines[-1]['p1']} → {self.lines[-1]['p2']}")
        self.pending = []

    # ------------------------------------------------------------------
    def render(self):
        cv2 = self.cv2
        img = self.view.copy()
        for l in self.lines:
            a, b = l["_view"]
            cv2.line(img, a, b, l["_color"], 3)
            cv2.circle(img, a, 5, l["_color"], -1)
            cv2.circle(img, b, 5, l["_color"], -1)
            mid = ((a[0] + b[0]) // 2, (a[1] + b[1]) // 2)
            cv2.putText(img, l["line_id"], mid, cv2.FONT_HERSHEY_SIMPLEX,
                        0.6, l["_color"], 2)
        if len(self.pending) == 1:
            cv2.line(img, self.pending[0], self.hover, self.kind[3], 2)
            cv2.circle(img, self.pending[0], 5, self.kind[3], -1)

        # 상단 안내 (OpenCV 는 한글을 못 그리므로 영문으로 표기한다)
        mode = {"center": "CENTER LINE", "stop": "STOP LINE", "exit": "EXIT LINE"}[self.kind[0]]
        if self.kind[0] == "center":
            mode += " (U-turn ALLOWED)" if self.kind[1] else " (U-turn FORBIDDEN)"
        cv2.rectangle(img, (0, 0), (img.shape[1], 58), (0, 0, 0), -1)
        cv2.putText(img, f"[{mode}]  lines={len(self.lines)}", (12, 24),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, self.kind[3], 2)
        cv2.putText(img, "1/2/3/4 mode   z undo   r reset   w save+quit   q quit",
                    (12, 48), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        return img

    # ------------------------------------------------------------------
    def loop(self) -> bool:
        cv2 = self.cv2
        win = "ROI - draw virtual lines"
        cv2.namedWindow(win)
        cv2.setMouseCallback(win, self.on_mouse)
        while True:
            cv2.imshow(win, self.render())
            k = cv2.waitKey(20) & 0xFF
            if k == 255:
                continue
            if k in LINE_KINDS:
                self.kind = LINE_KINDS[k]
                self.pending = []
            elif k == ord("z"):
                if self.pending:
                    self.pending = []
                elif self.lines:
                    print(f"  - 취소: {self.lines.pop()['line_id']}")
            elif k == ord("r"):
                self.lines, self.pending = [], []
            elif k == ord("w"):
                cv2.destroyAllWindows()
                return True
            elif k in (ord("q"), 27):
                cv2.destroyAllWindows()
                return False


# --------------------------------------------------------------------------
def save(cam_id: str, lines: list[dict], location) -> None:
    data = {"cameras": []}
    if ZONES.exists():
        data = json.loads(ZONES.read_text(encoding="utf-8"))

    clean = []
    for l in lines:
        d = {k: v for k, v in l.items() if not k.startswith("_")}
        clean.append(d)

    cams = data.setdefault("cameras", [])
    entry = next((c for c in cams if c["cam_id"] == cam_id), None)
    if entry is None:
        entry = {"cam_id": cam_id, "name": cam_id, "lines": [], "zones": [],
                 "intersections": []}
        cams.append(entry)
    entry["lines"] = clean
    if location:
        entry["location"] = list(location)

    # 정지선이 있으면 교차로 정의도 같이 채워 준다 (신호위반 판정용)
    stop = next((l["line_id"] for l in clean if l["line_type"] == "stop"), "")
    if stop:
        exit_l = next((l["line_id"] for l in clean if l["line_type"] == "exit"), "")
        entry["intersections"] = [{"intersection_id": f"INT-{cam_id}",
                                   "stop_line": stop, "exit_line": exit_l,
                                   "signal_id": "SIG-1"}]
    else:
        entry["intersections"] = []

    ZONES.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                     encoding="utf-8")
    print(f"\n저장 완료 → {ZONES}  (cam_id={cam_id}, 라인 {len(clean)}개)")


def main() -> None:
    ap = argparse.ArgumentParser(description="가상 라인(ROI) 그리기")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--video", help="영상 파일 (첫 프레임을 사용)")
    src.add_argument("--image", help="이미지 파일")
    ap.add_argument("--cam", default="CAM-TEST", help="카메라 ID")
    ap.add_argument("--lat", type=float, help="위도 (선택)")
    ap.add_argument("--lng", type=float, help="경도 (선택)")
    a = ap.parse_args()

    try:
        import cv2  # noqa: F401
    except ImportError:
        sys.exit("OpenCV 가 필요합니다:  pip install opencv-python")

    frame = first_frame(a.video) if a.video else imread_unicode(a.image)
    if frame is None:
        sys.exit("이미지를 읽지 못했습니다. 경로를 확인하세요.")

    d = Drawer(frame, a.cam)
    print(__doc__.split("조작")[1].split("유턴만")[0])
    if d.loop():
        loc = (a.lat, a.lng) if a.lat is not None and a.lng is not None else None
        save(a.cam, d.lines, loc)
    else:
        print("저장하지 않고 종료했습니다.")


if __name__ == "__main__":
    main()
