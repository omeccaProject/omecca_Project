"""단일 사진 1장을 known_faces/에 정식 등록하고 face_embeddings.pkl에 임베딩을
append하는 1회성 스크립트. WantedPersonService(Spring)가 등록 API를 받을 때마다
서브프로세스로 동기 실행한다 - camera_watcher.py처럼 계속 떠있는 워처가 아니라
"실행하고 끝나는" 스크립트다.

탐지 전략(품질 우선, False Accept 실험에서 확인된 사실 반영):
    1차: HOG, upsample=1  (제일 빠름, 대부분의 정면 사진에서 성공)
    2차: HOG, upsample=2  (원거리/작은 얼굴 사진 대응, build_face_db.py와 동일 정책)
    3차: CNN, upsample=1  (HOG가 못 잡는 각도/저조도 사진 최후 보정 - _2.jpg 실측에서
                           HOG 실패·CNN 성공 사례를 실제로 확인했었음)
    3단계 다 실패하면 등록 실패로 종료(exit 1), stderr에 사유 출력 - Spring이 이걸
    그대로 failureReason으로 저장한다.

등록은 "덮어쓰기 가능"하게 설계함: 같은 --id로 다시 호출되면(재등록/사진 교체)
기존 entry를 먼저 지우고 새로 추가한다 - 중복 방지 책임은 Spring 쪽
(wantedId unique 제약)에 있지만, 스크립트 레벨에서도 안전장치로 한 번 더 막는다.

사용법:
    python register_single_face.py --id W005 --name 홍길동 --photo /path/to/upload.jpg
"""
import argparse
import os
import shutil
import sys
import pickle

import face_recognition
import numpy as np
from PIL import Image, ImageOps

from embedding_utils import save_embeddings_atomically

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
KNOWN_FACES_DIR = os.path.join(BASE_DIR, "known_faces")
PKL_PATH = os.path.join(BASE_DIR, "face_embeddings.pkl")

MAX_DIM = 1080


def load_and_preprocess_image(image_path, max_dim=MAX_DIM):
    """EXIF 회전 보정 + 리사이즈. build_face_db.py의 동일 함수와 로직을 맞춰서
    두 등록 경로(다중 사진 배치 등록 / 웹 UI 단일 등록)의 결과가 서로 다르게
    나오지 않도록 한다."""
    pil_img = Image.open(image_path)
    pil_img = ImageOps.exif_transpose(pil_img)
    w, h = pil_img.size
    if max(w, h) > max_dim:
        scale = max_dim / max(w, h)
        pil_img = pil_img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
    return np.array(pil_img.convert("RGB"))


def detect_face_encoding(image):
    """HOG(upsample 1->2) -> CNN(upsample 1) 순서로 시도, 첫 성공 결과를 반환.
    전부 실패하면 (None, 실패사유문자열)을 반환한다."""
    attempts = [
        ("hog", 1),
        ("hog", 2),
        ("cnn", 1),
    ]
    for model, upsample in attempts:
        locations = face_recognition.face_locations(image, number_of_times_to_upsample=upsample, model=model)
        if not locations:
            continue
        encodings = face_recognition.face_encodings(image, known_face_locations=locations)
        if encodings:
            return encodings[0], None
    return None, ("사진에서 얼굴을 감지하지 못했습니다 (HOG upsample=1/2, CNN upsample=1 "
                   "모두 시도했으나 실패). 더 정면에 가깝고 밝은 사진으로 다시 시도해주세요.")


def main():
    parser = argparse.ArgumentParser(description="수배자 사진 1장 등록 (단일 실행)")
    parser.add_argument("--id", required=True, help="수배자 ID (예: W005)")
    parser.add_argument("--name", required=True, help="수배자 이름 (밑줄(_) 문자 불가)")
    parser.add_argument("--photo", required=True, help="원본 업로드 사진의 절대경로")
    args = parser.parse_args()

    if "_" in args.name:
        print("이름에 밑줄(_) 문자를 포함할 수 없습니다 (known_faces 파일명 파싱 규칙과 충돌).",
              file=sys.stderr)
        sys.exit(1)

    if not os.path.exists(args.photo):
        print(f"원본 사진 파일을 찾을 수 없습니다: {args.photo}", file=sys.stderr)
        sys.exit(1)

    try:
        image = load_and_preprocess_image(args.photo)
    except Exception as e:
        print(f"이미지 로드 실패: {e}", file=sys.stderr)
        sys.exit(1)

    encoding, error = detect_face_encoding(image)
    if encoding is None:
        print(error, file=sys.stderr)
        sys.exit(1)

    os.makedirs(KNOWN_FACES_DIR, exist_ok=True)
    ext = os.path.splitext(args.photo)[1].lower() or ".jpg"
    dest_filename = f"{args.id}_{args.name}{ext}"
    dest_path = os.path.join(KNOWN_FACES_DIR, dest_filename)
    shutil.copyfile(args.photo, dest_path)

    data = []
    if os.path.exists(PKL_PATH):
        with open(PKL_PATH, "rb") as f:
            data = pickle.load(f)

    # 재등록/사진 교체 대응 - 같은 id의 기존 entry는 먼저 제거하고 새로 추가
    data = [entry for entry in data if entry.get("id") != args.id]
    data.append({
        "id": args.id,
        "name": args.name,
        "embedding": encoding,
        "file": dest_filename,
    })

    save_embeddings_atomically(PKL_PATH, data)
    print(f"등록 완료: {args.id} - {args.name} ({dest_filename})")
    sys.exit(0)


if __name__ == "__main__":
    main()
