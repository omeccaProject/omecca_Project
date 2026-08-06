"""b_report CLI — 캡쳐 → PDF 생성 → 게이트웨이 등록."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from .capture import capture_before_after_from_video, ensure_image
from .generate_pdf import generate_evidence_pdf
from .register_report import register_report


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Omecca evidence report generator")
    p.add_argument("--event-id", type=int, required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--event-type", required=True)
    p.add_argument("--occurred-at", required=True, help="ISO datetime string")
    p.add_argument("--location", required=True)
    p.add_argument("--plate", default=None)
    p.add_argument("--cam-id", default=None, help="카메라 ID (예: CAM-01)")
    p.add_argument("--track-id", default=None, help="추적 ID (예: trk-1234)")
    p.add_argument("--confidence", type=float, default=None, help="탐지 신뢰도 (0~1)")
    p.add_argument("--bbox", type=int, nargs=4, default=None, metavar=("X", "Y", "W", "H"),
                    help="탐지 bbox 좌표 4개 (증거 이미지에 빨간 박스로 표시됨)")
    p.add_argument("--before", help="기존 before 이미지 경로")
    p.add_argument("--after", help="기존 after 이미지 경로")
    p.add_argument("--video", help="영상 경로 (before/after 없을 때 사용)")
    p.add_argument("--event-sec", type=float, default=0.0, help="영상 내 이벤트 시각(초)")
    p.add_argument("--margin-sec", type=float, default=1.0)
    p.add_argument("--output-dir", default="./output")
    p.add_argument("--gateway-url", default="http://localhost:8080")
    p.add_argument("--skip-register", action="store_true")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    out_dir = Path(args.output_dir) / f"event_{args.event_id}"
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.before and args.after:
        before = ensure_image(args.before)
        after = ensure_image(args.after)
    elif args.video:
        before, after = capture_before_after_from_video(
            args.video,
            args.event_sec,
            out_dir / "frames",
            margin_sec=args.margin_sec,
        )
    else:
        raise SystemExit("--before/--after 또는 --video 중 하나를 지정하세요.")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    pdf_path = out_dir / f"report_{args.event_id}_{stamp}.pdf"
    generate_evidence_pdf(
        pdf_path,
        title=args.title,
        event_type=args.event_type,
        occurred_at=args.occurred_at,
        location=args.location,
        plate=args.plate,
        before_image=before,
        after_image=after,
        event_id=args.event_id,
        cam_id=args.cam_id,
        track_id=args.track_id,
        confidence=args.confidence,
        bbox=args.bbox,
    )
    print(f"PDF created: {pdf_path.resolve()}")

    if not args.skip_register:
        result = register_report(
            args.gateway_url,
            event_id=args.event_id,
            pdf_path=str(pdf_path.resolve()),
            status="GENERATED",
        )
        print(f"Registered: {result}")


if __name__ == "__main__":
    main()