#!/usr/bin/env python3
"""영상에서 중앙선·정지선을 **자동으로 찾아** config_zones.json 에 넣는다.

왜 만들었나
    `draw_roi.py` 는 사람이 마우스로 두 점을 찍어야 한다. 영상이 한두 개면
    괜찮은데, 카메라가 늘어나면 매번 창을 띄우고 클릭하는 게 일이 된다.
    노란 중앙선은 색이 뚜렷해서 기계가 찾는 편이 빠르고 정확하다.

어떻게 찾나
    1) 프레임을 20장쯤 뽑아 **중앙값 합성**한다.
       움직이는 차가 지워지고 노면만 남는다. 차가 선을 가려도 문제없다.
    2) HSV 로 노란색만 남긴다 (중앙선). 흰색은 정지선 후보.
    3) 남은 픽셀에 직선을 맞춘다 (x = a·y + b).
       원근 때문에 화면에서는 비스듬하지만 **직선**이라 1차식으로 충분하다.

한계 — 확인은 사람이 한다
    노란 간판·낙엽·조명이 노랗게 잡히면 선이 엉뚱해진다. 그래서 결과를 그린
    미리보기 PNG 를 항상 같이 저장한다. **그 그림을 보고** 이상하면
    `draw_roi.py` 로 직접 그으면 된다.

    실측으로 확인된 되는 경우 / 안 되는 경우 (2026-08-21)

        되는 것   낮, 직선 도로, 노란 중앙선이 화면을 가로지름
                  → 「불법유턴 영상.mp4」 에서 복선 사이를 정확히 통과 (행 540개로 맞춤)

        안 되는 것  밤 교차로
                  → 「신호위반 영상.mp4」 에서 가로등·간판의 노란 빛을 이어
                    하늘을 가로지르는 엉뚱한 선을 만들었다. 애초에 그 화면에는
                    중앙선이 없다(교차로 한복판).
                  → 정지선도 못 찾았다. 노면 밝기 중앙값이 75, 최대 148 이라
                    흰 차선이 배경에 묻힌다. 밝기 임계값을 낮추면 이번엔 가게
                    불빛이 잡힌다.

    즉 **밤 교차로는 draw_roi.py 로 직접 긋는다.** 클릭 4번이면 끝나므로
    억지로 자동화할 이유가 없다.

사용법
    python auto_roi.py --video "불법유턴 영상.mp4" --cam UTURN3
    python auto_roi.py --video "신호위반 영상.mp4" --cam SIGNAL2 --stop
    python auto_roi.py --video ... --cam ... --preview-only   # 저장 안 함
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

import cv2                                    # noqa: E402
import numpy as np                            # noqa: E402

from app.lpr.visualize import imwrite_unicode  # noqa: E402

LINE = "─" * 66


def median_background(path: str, n: int = 20):
    """움직이는 물체를 지운 노면 이미지."""
    cap = cv2.VideoCapture(path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    frames = []
    for i in np.linspace(0, total - 1, n).astype(int):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(i))
        ok, im = cap.read()
        if ok:
            frames.append(im)
    cap.release()
    if not frames:
        return None
    return np.median(np.stack(frames), axis=0).astype(np.uint8)


def fit_line(mask, top_ratio=0.25):
    """마스크 픽셀에 직선을 맞춰 (p1, p2) 를 낸다.

    행마다 픽셀의 **중앙값 x** 를 구해 점을 모은 뒤 1차식을 맞춘다.
    중앙선은 두 줄(황색 복선)이라 평균을 내면 그 사이를 지나간다 — 의도한 것이다.
    """
    h, w = mask.shape
    mask = mask.copy()
    mask[:int(h * top_ratio), :] = 0        # 하늘·건물 제외

    pts = []
    for y in range(int(h * top_ratio), h):
        xs = np.nonzero(mask[y])[0]
        if len(xs) >= 2:
            pts.append((float(np.median(xs)), float(y)))
    if len(pts) < 20:
        return None, 0

    xs = np.array([p[0] for p in pts])
    ys = np.array([p[1] for p in pts])
    a, b = np.polyfit(ys, xs, 1)            # x = a*y + b

    # 맞춘 구간만 쓰면 선이 짧아진다. 차가 노란선을 가리면 중앙값 합성에도 잔상이
    # 남아 그 구간의 픽셀이 사라지기 때문이다(실측: 30행만 잡힌 적 있음).
    # 차는 **카메라에 가까운 아래쪽**에서 선을 넘으므로, 거기까지 닿지 않으면
    # 통과 자체를 놓친다. 노면 표시는 직선이라 아래로 늘려도 안전하다.
    y1 = float(int(h * top_ratio))
    y2 = float(h - 1)
    return ((int(a * y1 + b), int(y1)), (int(a * y2 + b), int(y2))), len(pts)


def main() -> int:
    ap = argparse.ArgumentParser(description="중앙선/정지선 자동 검출")
    ap.add_argument("--video", required=True)
    ap.add_argument("--cam", required=True)
    ap.add_argument("--zones", default=str(BASE / "config_zones.json"))
    ap.add_argument("--stop", action="store_true",
                    help="정지선(흰 가로선)도 찾는다 — 신호위반용")
    ap.add_argument("--preview-only", action="store_true", help="저장하지 않는다")
    ap.add_argument("--out", default=str(BASE / "output"))
    a = ap.parse_args()

    print(f"{LINE}\n중앙선 자동 검출\n{LINE}")
    print(f"  영상: {a.video}\n  카메라: {a.cam}")

    bg = median_background(a.video)
    if bg is None:
        print("영상을 읽지 못했습니다."); return 1
    h, w = bg.shape[:2]
    print(f"  해상도: {w}x{h}")

    hsv = cv2.cvtColor(bg, cv2.COLOR_BGR2HSV)
    prev = bg.copy()
    lines = []

    # ---------------------------------------------------------- 중앙선(노랑)
    ymask = cv2.inRange(hsv, (15, 60, 90), (40, 255, 255))
    seg, n = fit_line(ymask)
    if seg is None:
        print("\n[실패] 노란 중앙선을 찾지 못했습니다.")
        print("       draw_roi.py 로 직접 그으세요.")
        return 1
    p1, p2 = seg
    print(f"\n  중앙선  {p1} → {p2}   (노란 픽셀 행 {n}개로 맞춤)")
    cv2.line(prev, p1, p2, (0, 0, 255), 3)
    cv2.putText(prev, "CENTER", (p1[0] + 8, p1[1] + 24),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
    lines.append({
        "line_id": "center_auto",
        "name": "중앙선(노란 실선) - 유턴 금지 [자동 검출]",
        "p1": list(p1), "p2": list(p2),
        "direction": "both",
        "line_type": "center",
        "uturn_allowed": False,
    })

    # ---------------------------------------------------------- 정지선(흰 가로선)
    if a.stop:
        # 흰색은 차선·건물에도 많다. 아래쪽 절반에서 **가로로 긴** 성분만 본다.
        wmask = cv2.inRange(hsv, (0, 0, 190), (180, 45, 255))
        wmask[:int(h * 0.55), :] = 0
        wmask = cv2.morphologyEx(wmask, cv2.MORPH_OPEN,
                                 cv2.getStructuringElement(cv2.MORPH_RECT, (61, 3)))
        rows = np.nonzero(wmask.sum(axis=1) > w * 0.18)[0]
        if len(rows):
            ys = int(np.median(rows))
            xs = np.nonzero(wmask[ys])[0]
            sp1, sp2 = (int(xs.min()), ys), (int(xs.max()), ys)
            print(f"  정지선  {sp1} → {sp2}")
            cv2.line(prev, sp1, sp2, (0, 200, 255), 3)
            cv2.putText(prev, "STOP", (sp1[0] + 8, ys - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 200, 255), 2)
            lines.append({
                "line_id": "stop_auto", "name": "정지선 [자동 검출]",
                "p1": list(sp1), "p2": list(sp2),
                "direction": "both", "line_type": "stop",
            })
            # 진출선은 정지선보다 더 아래(카메라 쪽). 교차로를 통과했다는 판정용.
            ey = min(h - 5, ys + int(h * 0.18))
            lines.append({
                "line_id": "exit_auto", "name": "진출선 [자동 검출]",
                "p1": [sp1[0], ey], "p2": [sp2[0], ey],
                "direction": "both", "line_type": "exit",
            })
            cv2.line(prev, (sp1[0], ey), (sp2[0], ey), (255, 200, 0), 3)
            cv2.putText(prev, "EXIT", (sp1[0] + 8, ey - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 200, 0), 2)
        else:
            print("  정지선  찾지 못함 (흰 가로선이 뚜렷하지 않음)")

    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    pv = out / f"roi_{a.cam}.png"
    imwrite_unicode(str(pv), prev)
    print(f"\n  미리보기 → {pv}")
    print("  **이 그림을 먼저 확인하세요.** 선이 엉뚱하면 draw_roi.py 로 직접 긋습니다.")

    if a.preview_only:
        print("\n(--preview-only 라 저장하지 않았습니다)")
        return 0

    # ---------------------------------------------------------- 저장
    zp = Path(a.zones)
    data = json.loads(zp.read_text(encoding="utf-8"))
    cams = data.setdefault("cameras", [])
    cam = next((c for c in cams if c.get("cam_id") == a.cam), None)
    if cam is None:
        cam = {"cam_id": a.cam, "name": f"{a.cam} [자동]", "location": [37.5665, 126.978]}
        cams.append(cam)
    # 자동 검출분만 갈아끼운다. 사람이 그은 선은 건드리지 않는다.
    keep = [l for l in cam.get("lines", []) if not l.get("line_id", "").endswith("_auto")]
    cam["lines"] = keep + lines
    zp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n  {zp.name} 에 {len(lines)}개 저장 (기존 수동 선 {len(keep)}개는 유지)")
    print(f"\n다음:\n  python run_uturn.py --video \"{a.video}\" --cam {a.cam} \\\n"
          f"      --weights ..\\omecca_Project\\e_tracking\\SmartCCTV\\yolo11m.pt --lpr")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
