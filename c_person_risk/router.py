import io
import pickle
import os
import face_recognition
from PIL import Image
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request
from c_person_risk.embedding_utils import save_embeddings_atomically

router = APIRouter(prefix="/api", tags=["Wanted Person"])
PKL_PATH = "c_person_risk/face_embeddings.pkl"

@router.post("/wanted-person")
async def register_wanted_person(
    request: Request,
    wanted_id: str = Form(...),
    name: str = Form(...),
    file: UploadFile = File(...)
):
    contents = await file.read()
    image = Image.open(io.BytesIO(contents)).convert("RGB")
    import numpy as np
    img_np = np.array(image)

    # model="cnn" 사용하여 128차원 임베딩 추출
    locations = face_recognition.face_locations(img_np, number_of_times_to_upsample=2, model="cnn")
    encodings = face_recognition.face_encodings(img_np, locations)

    if not encodings:
        raise HTTPException(status_code=400, detail="얼굴을 감지할 수 없습니다.")

    new_encoding = encodings[0]

    # 중복 등록 방지: 같은 wanted_id로 이미 등록된 사람이 있으면 막기
    # (예전에 김철수 사진 3장이 W002/W003/W004로 각각 따로 등록됐던
    #  그 문제가 API로도 똑같이 재발할 수 있어서 추가함)
    data = []
    if os.path.exists(PKL_PATH):
        with open(PKL_PATH, "rb") as f:
            data = pickle.load(f)   # ← list 형식 그대로 로드 (더 이상 dict로 안 덮어씀)

    if any(person["id"] == wanted_id for person in data):
        raise HTTPException(
            status_code=409,
            detail=f"이미 등록된 wanted_id입니다: {wanted_id}"
        )

    # face_detect.py가 기대하는 형식과 동일하게 딕셔너리로 추가
    data.append({
        "id": wanted_id,
        "name": name,
        "embedding": new_encoding
    })

    # 원자적 저장
    save_embeddings_atomically(PKL_PATH, data)

    # 싱글톤 FaceDetector 메모리 즉시 갱신 (Hot Reload)
    if hasattr(request.app.state, "face_detector"):
        request.app.state.face_detector.reload_embeddings()

    return {"status": "success", "wantedId": wanted_id, "name": name}