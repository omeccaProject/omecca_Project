import face_recognition
import os
import pickle
import numpy as np
from PIL import Image, ImageOps

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
KNOWN_FACES_DIR = os.path.join(BASE_DIR, "known_faces")
OUTPUT_FILE = os.path.join(BASE_DIR, "face_embeddings.pkl")

def load_and_preprocess_image(image_path, max_dim=1080):
    """EXIF 회전 보정 + 고속 연산을 위한 자동 리사이즈 (10배 가속)"""
    pil_img = Image.open(image_path)
    pil_img = ImageOps.exif_transpose(pil_img)
    
    # 긴 축 기준 1080px로 리사이즈하여 CPU 연산량 대폭 감소
    w, h = pil_img.size
    if max(w, h) > max_dim:
        scale = max_dim / max(w, h)
        new_w, new_h = int(w * scale), int(h * scale)
        pil_img = pil_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        
    return np.array(pil_img.convert("RGB"))

def build_database():
    db = []

    if not os.path.exists(KNOWN_FACES_DIR):
        print(f"⚠️ known_faces 폴더가 없습니다: {KNOWN_FACES_DIR}")
        return

    for filename in os.listdir(KNOWN_FACES_DIR):
        if not filename.lower().endswith((".jpg", ".png", ".jpeg")):
            continue
        
        # 파일명 파싱 (W001_이시헌_1.jpg -> ID: W001, Name: 이시헌)
        name_part = os.path.splitext(filename)[0]
        parts = name_part.split("_")
        
        if len(parts) >= 2:
            wanted_id = parts[0]
            name = parts[1]
        elif len(parts) == 1:
            wanted_id = parts[0]
            name = parts[0]
        else:
            print(f"⚠️ 파일명 형식 오류(건너뜀): {filename}")
            continue
        
        path = os.path.join(KNOWN_FACES_DIR, filename)
        
        try:
            image = load_and_preprocess_image(path)
        except Exception as e:
            print(f"⚠️ 이미지 로드 실패: {filename} ({e})")
            continue

        # 1차 탐색 (HOG)
        face_locations = face_recognition.face_locations(image, number_of_times_to_upsample=1, model="hog")
        
        # 2차 탐색 (HOG 감도 상향)
        if len(face_locations) == 0:
            face_locations = face_recognition.face_locations(image, number_of_times_to_upsample=2, model="hog")

        encodings = face_recognition.face_encodings(image, known_face_locations=face_locations)
        
        if len(encodings) == 0:
            print(f"⚠️ 얼굴 인식 실패(건너뜀): {filename}")
            continue
        
        db.append({
            "id": wanted_id,
            "name": name,
            "embedding": encodings[0],
            "file": filename
        })
        print(f"✅ 등록됨: {wanted_id} - {name} (파일: {filename})")
    
    with open(OUTPUT_FILE, "wb") as f:
        pickle.dump(db, f)
    print(f"\n총 {len(db)}개 얼굴 벡터 등록 완료 → {OUTPUT_FILE} 저장됨")

if __name__ == "__main__":
    build_database()