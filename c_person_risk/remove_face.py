"""face_embeddings.pkl에서 특정 수배자 id의 임베딩(들)을 제거하는 1회성 스크립트.
WantedPersonService(Spring)의 삭제 API가 DB row를 지우기 전에 이 스크립트를 먼저
실행해서, pkl과 DB가 서로 어긋나지 않게 한다.

known_faces/ 폴더의 실제 사진 파일(예: W005_홍길동.jpg)도 같이 정리한다 - pkl만
지우고 사진 파일이 남아있으면, 나중에 누군가 build_face_db.py로 known_faces를
통째로 재빌드할 때 지운 사람이 되살아나는 사고를 방지하기 위함.

사용법:
    python remove_face.py --id W005
"""
import argparse
import glob
import os
import pickle
import sys

from embedding_utils import save_embeddings_atomically

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
KNOWN_FACES_DIR = os.path.join(BASE_DIR, "known_faces")
PKL_PATH = os.path.join(BASE_DIR, "face_embeddings.pkl")


def main():
    parser = argparse.ArgumentParser(description="수배자 임베딩 제거 (단일 실행)")
    parser.add_argument("--id", required=True, help="제거할 수배자 ID (예: W005)")
    args = parser.parse_args()

    removed_count = 0
    if os.path.exists(PKL_PATH):
        with open(PKL_PATH, "rb") as f:
            data = pickle.load(f)
        before = len(data)
        data = [entry for entry in data if entry.get("id") != args.id]
        removed_count = before - len(data)
        save_embeddings_atomically(PKL_PATH, data)

    # known_faces/<id>_*.* 패턴의 실제 사진 파일도 정리 (다중 사진 등록 시
    # W001_이시헌_1.jpg / _2 / _3처럼 여러 장일 수 있어 glob으로 전부 제거)
    deleted_files = 0
    for path in glob.glob(os.path.join(KNOWN_FACES_DIR, f"{args.id}_*")):
        try:
            os.remove(path)
            deleted_files += 1
        except OSError as e:
            print(f"경고: 사진 파일 삭제 실패({path}): {e}", file=sys.stderr)

    print(f"제거 완료: pkl entry {removed_count}개, 사진 파일 {deleted_files}개 삭제됨")
    sys.exit(0)


if __name__ == "__main__":
    main()
