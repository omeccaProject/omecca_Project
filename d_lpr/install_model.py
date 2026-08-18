#!/usr/bin/env python3
"""번호판 전용 모델을 EasyOCR 이 찾는 자리에 놓는다.

왜 복사가 필요한가
    EasyOCR 은 사용자 모델을 **홈 폴더의 정해진 경로**에서만 읽는다.
    저장소 안에 두면 못 찾는다.

        ~/.EasyOCR/model/plate.pth            학습된 가중치
        ~/.EasyOCR/user_network/plate.py      신경망 구조
        ~/.EasyOCR/user_network/plate.yaml    문자셋·입력 규격

    세 개가 **전부** 있어야 쓴다. 하나라도 없으면 아무 말 없이 기본 한국어
    모델(korean_g2)로 넘어간다. 에러가 안 나기 때문에 "설치했는데 왜 성능이
    그대로지?" 로 헤매기 쉽다. 그래서 이 스크립트가 확인까지 해준다.

사용법
    python install_model.py            # models/ → ~/.EasyOCR/ 복사
    python install_model.py --check    # 지금 설치돼 있는지 확인만
    python install_model.py --force    # 이미 있어도 덮어쓰기

되돌리기
    ~/.EasyOCR/model/plate.pth 하나만 지우면 기본 모델로 돌아간다.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

SRC = BASE / "models"
HOME = Path.home() / ".EasyOCR"

# (저장소 안 파일, 놓아야 할 자리)
FILES = [
    (SRC / "plate.pth",  HOME / "model" / "plate.pth"),
    (SRC / "plate.py",   HOME / "user_network" / "plate.py"),
    (SRC / "plate.yaml", HOME / "user_network" / "plate.yaml"),
]

LINE = "─" * 66


def human(n: int) -> str:
    return f"{n / 1_048_576:.1f}MB" if n >= 1_048_576 else f"{n / 1024:.0f}KB"


def check() -> bool:
    print(f"\n설치 위치: {HOME}")
    print(LINE)
    ok = True
    for _, dst in FILES:
        if dst.exists():
            print(f"  [있음]  {dst.name:12} {human(dst.stat().st_size)}")
        else:
            print(f"  [없음]  {dst.name}")
            ok = False
    print(LINE)
    if ok:
        print("전용 모델이 설치돼 있습니다. 코드가 자동으로 이걸 씁니다.")
    else:
        print("파일이 빠져 있어 기본 모델(korean_g2)로 동작합니다.")
        print("  → python install_model.py 로 설치하세요.")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(description="번호판 전용 모델 설치")
    ap.add_argument("--check", action="store_true", help="설치 여부만 확인")
    ap.add_argument("--force", action="store_true", help="이미 있어도 덮어쓴다")
    a = ap.parse_args()

    if a.check:
        return 0 if check() else 1

    missing = [s for s, _ in FILES if not s.exists()]
    if missing:
        print(f"\n저장소에 모델 파일이 없습니다: {SRC}")
        for m in missing:
            print(f"    {m.name}")
        print("\n  git 에 올라와 있어야 합니다. `git pull` 을 먼저 해보세요.")
        return 1

    print(f"\n{SRC}\n  → {HOME}\n{LINE}")
    done = 0
    for src, dst in FILES:
        if dst.exists() and not a.force:
            print(f"  건너뜀  {dst.name}  (이미 있음, 덮어쓰려면 --force)")
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        print(f"  복사    {dst.name:12} {human(src.stat().st_size)}")
        done += 1
    print(LINE)
    print(f"{done}개 복사")

    # 복사했다고 믿지 말고, 코드가 실제로 인식하는지 물어본다.
    try:
        from app.lpr.recognizer import custom_model_ready
        ready, info = custom_model_ready()
        print(f"\n코드 인식 여부: {'OK — 전용 모델 사용' if ready else '실패 — ' + info}")
        if not ready:
            return 1
    except ImportError:
        print("\n(app 모듈을 불러올 수 없어 확인은 건너뜁니다)")

    print("\n확인:  python bench_lpr.py --dir plates_final --weights plate_det.pt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
