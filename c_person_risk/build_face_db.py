import face_recognition
import os
import pickle

KNOWN_FACES_DIR = "known_faces"
OUTPUT_FILE = "face_embeddings.pkl"

def build_database():
    db = []  # [{"id": "W001", "name": "홍길동", "embedding": [...]}]
    
    for filename in os.listdir(KNOWN_FACES_DIR):
        if not filename.lower().endswith((".jpg", ".png", ".jpeg")):
            continue
        
        # 파일명에서 ID, 이름 추출 (예: W001_홍길동.jpg)
        name_part = os.path.splitext(filename)[0]
        try:
            wanted_id, name = name_part.split("_", 1)
        except ValueError:
            print(f"⚠️ 파일명 형식이 안 맞음(건너뜀): {filename}")
            continue
        
        path = os.path.join(KNOWN_FACES_DIR, filename)
        image = face_recognition.load_image_file(path)
        encodings = face_recognition.face_encodings(image)
        
        if len(encodings) == 0:
            print(f"⚠️ 얼굴 인식 실패(건너뜀): {filename}")
            continue
        
        db.append({
            "id": wanted_id,
            "name": name,
            "embedding": encodings[0]  # 128차원 벡터
        })
        print(f"✅ 등록됨: {wanted_id} - {name}")
    
    with open(OUTPUT_FILE, "wb") as f:
        pickle.dump(db, f)
    print(f"\n총 {len(db)}명 등록 완료 → {OUTPUT_FILE} 저장됨")

if __name__ == "__main__":
    build_database()