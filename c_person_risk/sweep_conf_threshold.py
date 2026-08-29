import argparse
import os
import sys
import cv2
from collections import defaultdict

base_dir = os.path.dirname(os.path.abspath(__file__))
if base_dir not in sys.path:
    sys.path.append(base_dir)

from weapon_detect import WeaponDetector

CONF_SWEEP = [0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True)
    args = parser.parse_args()

    if not os.path.exists(args.video):
        print(f"파일 없음: {args.video}")
        sys.exit(1)

    print(f"=== {args.video} 기준 conf_threshold 스윕 ===\n")
    results = {}

    for conf in CONF_SWEEP:
        detector = WeaponDetector(conf_threshold=conf)
        cap = cv2.VideoCapture(args.video)
        frame_count = 0
        detect_count = 0
        label_counts = defaultdict(int)
        confidences = []

        while True:
            ret, frame = cap.read()
            if not ret:
                break
            frame_count += 1
            dets = detector.detect_weapons(frame)
            if dets:
                detect_count += 1
                for d in dets:
                    label_counts[d["label"]] += 1
                    confidences.append(d["confidence"])
        cap.release()

        rate = detect_count / frame_count * 100 if frame_count else 0
        avg_conf = sum(confidences) / len(confidences) if confidences else 0
        top_label = max(label_counts.items(), key=lambda x: x[1])[0] if label_counts else "-"
        results[conf] = (frame_count, detect_count, rate, top_label, avg_conf, dict(label_counts))

        print(f"conf={conf:.2f} | 탐지 프레임 {detect_count}/{frame_count} ({rate:.1f}%) "
              f"| 주로 '{top_label}'로 인식 | 평균신뢰도 {avg_conf:.2f}")

    print("\n=== 클래스 안정성 확인 (값 낮출수록 다른 클래스로 착각하는 비율도 커질 수 있음) ===")
    for conf, (fc, dc, rate, top, avgc, labels) in results.items():
        print(f"conf={conf:.2f}: {labels}")

    candidates = [c for c, (fc, dc, rate, top, avgc, labels) in results.items()
                  if rate >= 50 and len(labels) == 1]
    if candidates:
        best = max(candidates)
        print(f"\n>>> 이 영상 기준 추천 conf_threshold: {best} "
              f"(탐지율 {results[best][2]:.1f}%, 클래스 '{results[best][3]}'로 일관됨)")
    else:
        best = max(results.items(), key=lambda x: x[1][2])[0]
        print(f"\n>>> 50% 이상+클래스 일관 조건 만족하는 값 없음. "
              f"탐지율 제일 높은 conf={best} (탐지율 {results[best][2]:.1f}%)를 참고하세요 "
              f"- 다만 인식 클래스가 프레임마다 바뀔 수 있으니 화면으로 직접 확인 권장.")


if __name__ == "__main__":
    main()
