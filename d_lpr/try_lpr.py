#!/usr/bin/env python3
"""사진·영상으로 번호판 인식 직접 확인하기.

전체 흐름을 그대로 태운다.
    번호판 검출 → 전처리(기울기 보정·이진화) → 자리별 2패스 OCR
        → 포맷 보정 → 차량 DB 대조 → 결과 그리기

사용법
    python try_lpr.py 사진.jpg                       # 사진 한 장
    python try_lpr.py 사진폴더/                      # 폴더 전체
    python try_lpr.py 영상.mp4                       # 동영상
    python try_lpr.py 사진.jpg --stages              # 전처리 단계별 이미지도 저장
    python try_lpr.py 영상.mp4 --every 5 --out 결과   # 5프레임마다, 결과 폴더 지정
    python try_lpr.py --webcam                       # 웹캠 실시간

결과는 기본적으로 `output/` 폴더에 저장된다.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    import cv2
    import numpy as np
except ImportError:
    print("OpenCV 가 필요합니다:  pip install opencv-python")
    raise SystemExit(1)

from app.core.config import settings
from app.core.schemas import RiskLevel
from app.lpr import plate_format as pf
from app.lpr import preprocess, visualize
from app.lpr.detector import PlateDetector
from app.lpr.visualize import imread_unicode, imwrite_unicode
from app.lpr.recognizer import PlateRecognizer, get_reader
from app.vehicle.matcher import VehicleMatcher
from app.vehicle.repository import get_repository

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}
VIDEO_EXT = {".mp4", ".avi", ".mov", ".mkv", ".wmv", ".m4v"}
LINE = "─" * 70

RISK_LABEL = {
    "high": "고위험", "caution": "주의", "normal": "정상", "unknown": "미조회",
}

STATUS_LABEL = {
    "registered": "정상 등록",
    "unregistered": "DB 미등록",
    "stolen": "도난 신고",
    "wanted": "수배 차량",
    "fake_plate": "대포차 의심",
    "impound": "영치 대상",
    "insurance_expired": "보험 만료",
}


# ==========================================================================
class PlateFinder:
    """번호판 영역을 찾는다. 가능한 방법을 순서대로 시도한다.

      1) YOLO 번호판 가중치 (--weights 로 지정 시)
      2) OCR 텍스트 검출 (EasyOCR 의 검출망 활용 - 실사진에 가장 잘 맞음)
      3) 모폴로지 기반 CV 폴백 (OCR 없이도 동작)
    """

    def __init__(self, reader=None, weights: str | None = None) -> None:
        self.reader = reader
        self.yolo = PlateDetector(weights=weights, mock=False) if weights else None
        self.cv = PlateDetector(mock=False)

    def find(self, frame) -> tuple[list, str]:
        if self.yolo is not None:
            boxes = self.yolo.detect(frame, None)
            if boxes:
                return boxes, "yolo"
        if self.reader is not None:
            boxes = self.cv.detect_by_text(frame, self.reader)
            if boxes:
                return boxes, "ocr-detect"
        boxes = self.cv.detect(frame, None)
        return boxes, "cv"


class Recognized:
    def __init__(self, box, plate_no="", conf=0.0, risk="unknown",
                 status="", owner="", engine="", stages=None, valid_format=False):
        self.box = box
        self.plate_no = plate_no
        self.conf = conf
        self.risk = risk
        self.status = status
        self.owner = owner
        self.engine = engine
        self.stages = stages or []
        self.valid_format = valid_format

    @property
    def ok(self) -> bool:
        return bool(self.plate_no)

    @property
    def reliable(self) -> bool:
        """실측 기준 (사진 50장, 2026-08-14, 번호판 전용 모델, `bench_lpr.py`)

            임계값 0.40  채택 50건 중 49건 정답  정밀도  98.0%   ← 현재 설정
            임계값 0.60  채택 45건 중 45건 정답  정밀도 100.0%
            임계값 0.80  채택 28건 중 28건 정답  정밀도 100.0%

        형식이 맞아도 틀린 숫자가 우연히 형식에 맞을 수 있어 신뢰도만 본다.
        오답을 아예 없애려면 0.60 으로 올린다. 채택이 50→45 로 줄 뿐이라
        비용이 크지 않다.
        """
        return self.ok and self.conf >= settings.lpr.min_plate_conf


# ==========================================================================
class Runner:
    def __init__(self, args) -> None:
        self.args = args
        self.reader = None
        self.n_recognized = 0
        self.n_reliable = 0
        if not args.no_ocr:
            print("OCR 모델 로딩 중... (최초 1회 가중치를 내려받습니다)")
            t0 = time.perf_counter()
            self.reader = get_reader(settings.lpr.ocr_lang, args.gpu)
            if self.reader is None:
                print("EasyOCR 를 쓸 수 없습니다. 검출까지만 확인합니다.")
                print("  설치: SETUP_OCR.md 참고")
            else:
                print(f"로딩 완료 ({time.perf_counter() - t0:.1f}초)\n")

        self.finder = PlateFinder(self.reader, args.weights)
        self.rec = PlateRecognizer(mock=False, gpu=args.gpu, structured=not args.no_structured)
        self.matcher = VehicleMatcher(repo=get_repository(), log_reads=False)

    # ------------------------------------------------------------------
    def process_frame(self, frame, want_stages: bool = False) -> tuple[list[Recognized], str]:
        boxes, method = self.finder.find(frame)
        out: list[Recognized] = []

        for box in boxes[: self.args.max_plates]:
            stages = []
            if want_stages:
                crop = preprocess.crop(frame, box.to_xyxy())
                stages.append(("① 검출 크롭", crop))

            result = preprocess.run(
                frame, bbox_xyxy=box.to_xyxy(),
                target_h=settings.lpr.upscale_height,
                deskew_limit=settings.lpr.deskew_limit,
                denoise_min_height=settings.lpr.denoise_min_height,
            )
            if want_stages:
                stages.append((f"② 전처리 (기울기 {-result.angle:+.1f}도 보정)", result.image))
                stages.append(("③ 이진화", result.binary))

            if self.reader is None or result.image is None:
                out.append(Recognized(box, stages=stages))
                continue

            r = self.rec.read(result.image, bbox=box)
            if r is None:
                out.append(Recognized(box, stages=stages))
                continue

            m = self.matcher.match(r)
            item = Recognized(
                box, r.plate_no, r.confidence,
                m.risk_level.value,          # 미등록이면 high 로 나온다
                m.status.value,
                (m.record.owner_name if m.record else ""),
                r.engine, stages, r.valid_format,
            )
            self.n_recognized += 1
            self.n_reliable += int(item.reliable)
            out.append(item)
        return out, method

    # ------------------------------------------------------------------
    def annotate(self, frame, items: list[Recognized], header: str = "") -> "np.ndarray":
        img = frame.copy()
        for it in items:
            extra = ""
            if it.ok:
                extra = RISK_LABEL.get(it.risk, it.risk)
                status_ko = STATUS_LABEL.get(it.status, it.status)
                if it.status and it.status != "registered":
                    extra += f" · {status_ko}"
                elif it.owner:
                    extra += f" · {it.owner}"
            img = visualize.annotate_detection(
                img, it.box.to_xyxy(), it.plate_no, it.conf,
                it.risk if it.ok else "unknown", extra,
                font_size=self.args.font_size,
                low_confidence=it.ok and not it.reliable,
            )
        if header:
            img = visualize.draw_banner(img, header, self.args.font_size)
        return img


# ==========================================================================
def run_image(runner: Runner, path: Path, outdir: Path) -> bool:
    img = imread_unicode(path)
    if img is None:
        print(f"  읽기 실패: {path.name}")
        return False

    t0 = time.perf_counter()
    items, method = runner.process_frame(img, want_stages=runner.args.stages)
    dt = time.perf_counter() - t0

    found = [i for i in items if i.ok]
    print(f"\n■ {path.name}  ({img.shape[1]}x{img.shape[0]}, 검출방식 {method}, {dt:.2f}초)")
    if not items:
        print("  번호판 후보를 찾지 못했습니다.")
    for it in items:
        if it.ok:
            mark = "✓" if it.reliable else "?"
            tail = "" if it.reliable else "  ← 신뢰도 낮음, 재확인 필요"
            print(f"  {mark} {it.plate_no}  신뢰도 {it.conf:.2f}  "
                  f"[{RISK_LABEL.get(it.risk, it.risk)}]"
                  f"{'  ' + STATUS_LABEL.get(it.status, it.status) if it.status else ''}"
                  f"{'  (' + it.engine + ')' if it.engine else ''}{tail}")
        else:
            x1, y1, x2, y2 = it.box.to_xyxy()
            print(f"  · 후보 ({x1},{y1})-({x2},{y2}) — 문자 인식 실패")

    header = f"{path.name}\n검출 {len(items)}건 / 인식 {len(found)}건"
    out = runner.annotate(img, items, header)
    dst = outdir / f"{path.stem}_결과.jpg"
    imwrite_unicode(dst, out)
    print(f"  저장: {dst}")

    if runner.args.stages:
        for n, it in enumerate(items, 1):
            tile = visualize.stack_stages(it.stages)
            if tile is not None:
                p = outdir / f"{path.stem}_단계{n}.jpg"
                imwrite_unicode(p, tile)
                print(f"  저장: {p}")
    return bool(found)


# ==========================================================================
def run_video(runner: Runner, path: Path, outdir: Path) -> bool:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        print(f"  영상을 열 수 없습니다: {path}")
        return False

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    every = max(1, runner.args.every)

    print(f"\n■ {path.name}  {w}x{h}, {fps:.0f}fps, {total}프레임 "
          f"({every}프레임마다 인식)")

    dst = outdir / f"{path.stem}_결과.mp4"
    writer = cv2.VideoWriter(str(dst), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))

    votes: dict[str, list[float]] = defaultdict(list)
    last_items: list[Recognized] = []
    idx = processed = 0
    t0 = time.perf_counter()

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % every == 0:
            last_items, _ = runner.process_frame(frame)
            processed += 1
            for it in last_items:
                if it.ok:
                    votes[pf.canonical(it.plate_no)].append(it.conf)
            if processed % 10 == 0:
                print(f"  {idx}/{total} 프레임 처리 중... 누적 후보 {len(votes)}종")

        best = _leading(votes)
        header = f"{path.name}\n프레임 {idx}/{total}"
        if best:
            header += f"\n확정: {best[0]}  ({best[1]}표, 평균 {best[2]:.2f})"
        writer.write(runner.annotate(frame, last_items, header))
        idx += 1

    cap.release()
    writer.release()
    dt = time.perf_counter() - t0

    print(f"\n  처리 완료: {idx}프레임 중 {processed}프레임 인식, {dt:.1f}초")
    if not votes:
        print("  인식된 번호판이 없습니다.")
    else:
        print("\n  번호판별 득표 (다수결 확정)")
        ranked = sorted(votes.items(), key=lambda kv: (len(kv[1]), sum(kv[1])), reverse=True)
        for plate, confs in ranked[:10]:
            rec = runner.matcher.repo.find(plate)
            info = ""
            if rec:
                info = ("  → DB: " + STATUS_LABEL.get(rec.status.value, rec.status.value)
                        + (f" ({rec.memo})" if rec.memo else ""))
            print(f"    {plate:12} {len(confs):3d}표  평균 신뢰도 {sum(confs)/len(confs):.2f}{info}")
    print(f"  저장: {dst}")
    return bool(votes)


def _leading(votes: dict[str, list[float]]):
    if not votes:
        return None
    plate, confs = max(votes.items(), key=lambda kv: (len(kv[1]), sum(kv[1])))
    return plate, len(confs), sum(confs) / len(confs)


# ==========================================================================
def run_webcam(runner: Runner, outdir: Path) -> bool:
    cap = cv2.VideoCapture(runner.args.camera)
    if not cap.isOpened():
        print("카메라를 열 수 없습니다.")
        return False
    print("\n웹캠 시작 — q 종료, s 현재 화면 저장\n")
    idx = 0
    items: list[Recognized] = []
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % max(1, runner.args.every) == 0:
            items, _ = runner.process_frame(frame)
            for it in items:
                if it.ok:
                    print(f"  {it.plate_no}  {it.conf:.2f}  "
                          f"[{RISK_LABEL.get(it.risk, it.risk)}] "
                          f"{STATUS_LABEL.get(it.status, it.status)}")
        shown = runner.annotate(frame, items, "웹캠 — q 종료 / s 저장")
        cv2.imshow("omeca LPR", shown)
        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break
        if key == ord("s"):
            p = outdir / f"webcam_{int(time.time())}.jpg"
            imwrite_unicode(p, shown)
            print(f"  저장: {p}")
        idx += 1
    cap.release()
    cv2.destroyAllWindows()
    return True


# ==========================================================================
def collect(target: Path) -> tuple[list[Path], list[Path]]:
    if target.is_file():
        ext = target.suffix.lower()
        if ext in IMAGE_EXT:
            return [target], []
        if ext in VIDEO_EXT:
            return [], [target]
        return [], []
    images = sorted(p for p in target.rglob("*") if p.suffix.lower() in IMAGE_EXT)
    videos = sorted(p for p in target.rglob("*") if p.suffix.lower() in VIDEO_EXT)
    return images, videos


def main() -> int:
    ap = argparse.ArgumentParser(
        description="사진·영상으로 번호판 인식 확인",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("target", nargs="?", help="이미지/영상 파일 또는 폴더")
    ap.add_argument("--out", default="output", help="결과 저장 폴더 (기본 output)")
    ap.add_argument("--stages", action="store_true", help="전처리 단계별 이미지도 저장")
    ap.add_argument("--every", type=int, default=5, help="영상: N프레임마다 인식 (기본 5)")
    ap.add_argument("--max-plates", type=int, default=6,
                    help="한 화면 최대 번호판 수 (교차로 CCTV는 차가 여러 대라 넉넉히)")
    ap.add_argument("--weights", help="YOLO 번호판 가중치 경로 (있으면 우선 사용)")
    ap.add_argument("--gpu", action="store_true", help="GPU 사용")
    ap.add_argument("--webcam", action="store_true", help="웹캠 실시간 인식")
    ap.add_argument("--camera", type=int, default=0, help="웹캠 번호 (기본 0)")
    ap.add_argument("--no-ocr", action="store_true", help="검출만 확인 (OCR 생략)")
    ap.add_argument("--no-structured", action="store_true", help="자리별 2패스 끄고 단일 패스")
    ap.add_argument("--font-size", type=int, default=20, help="라벨 글자 크기")
    args = ap.parse_args()

    if not args.webcam and not args.target:
        ap.print_help()
        return 1

    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)

    print(LINE)
    print("오메카3 LPR — 사진·영상 인식 확인")
    print(LINE)

    runner = Runner(args)

    if args.webcam:
        run_webcam(runner, outdir)
        return 0

    target = Path(args.target)
    if not target.exists():
        print(f"경로를 찾을 수 없습니다: {target}")
        return 1

    images, videos = collect(target)
    if not images and not videos:
        print(f"처리할 이미지/영상이 없습니다: {target}")
        return 1

    hit = 0
    for p in images:
        hit += run_image(runner, p, outdir)
    for p in videos:
        hit += run_video(runner, p, outdir)

    print("\n" + LINE)
    print(f"완료 — 이미지 {len(images)}장, 영상 {len(videos)}개 중 {hit}건에서 번호판 인식")
    if runner.n_recognized:
        print(f"  글자를 읽은 {runner.n_recognized}건 중 신뢰도 {settings.lpr.min_plate_conf:.0%} 이상 "
              f"{runner.n_reliable}건 (실측상 이 기준을 넘으면 대부분 정답)")
    st = runner.rec.stats
    if st["structured_ok"] or st["single_pass"]:
        print(f"자리별 2패스 성공 {st['structured_ok']}회 / 단일 패스 {st['single_pass']}회")
    print(f"결과 저장 위치: {outdir.resolve()}")
    print(LINE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
