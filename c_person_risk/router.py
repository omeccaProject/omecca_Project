import io
import pickle
import os
import face_recognition
from PIL import Image
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
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

    # 중복 등록 방지
    data = []
    if os.path.exists(PKL_PATH):
        with open(PKL_PATH, "rb") as f:
            data = pickle.load(f)

    if any(person["id"] == wanted_id for person in data):
        raise HTTPException(
            status_code=409,
            detail=f"이미 등록된 wanted_id입니다: {wanted_id}"
        )

    data.append({
        "id": wanted_id,
        "name": name,
        "embedding": new_encoding
    })

    # 원자적 저장
    save_embeddings_atomically(PKL_PATH, data)

    # 메모리 즉시 갱신
    if hasattr(request.app.state, "face_detector"):
        request.app.state.face_detector.reload_embeddings()

    return {"status": "success", "wantedId": wanted_id, "name": name}


# ---------------------------------------------------------
# [수배자 등록 시연용 Web UI 엔드포인트]
# ---------------------------------------------------------
@router.get("/wanted-person-ui", response_class=HTMLResponse)
async def wanted_person_register_ui():
    return HTMLResponse(content=REGISTER_UI_HTML)


REGISTER_UI_HTML = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>OmniGuard - 수배자 등록 시스템</title>
<style>
  body {
    font-family: -apple-system, "맑은 고딕", sans-serif;
    background: #0f0f0f;
    color: #eee;
    display: flex;
    justify-content: center;
    align-items: center;
    height: 100vh;
    margin: 0;
  }
  .card {
    background: #1a1a1a;
    padding: 36px;
    border-radius: 12px;
    width: 380px;
    box-shadow: 0 4px 20px rgba(0,0,0,0.4);
  }
  h2 {
    margin-top: 0;
    font-size: 20px;
    text-align: center;
    color: #fff;
  }
  h2 span { color: #2563eb; }
  label { display: block; margin-top: 18px; font-size: 13px; color: #aaa; }
  input[type="text"], input[type="file"] {
    width: 100%;
    padding: 10px;
    margin-top: 6px;
    border-radius: 6px;
    border: 1px solid #333;
    background: #0f0f0f;
    color: #eee;
    box-sizing: border-box;
    font-size: 14px;
  }
  button {
    width: 100%;
    margin-top: 26px;
    padding: 13px;
    border: none;
    border-radius: 6px;
    background: #2563eb;
    color: white;
    font-weight: bold;
    cursor: pointer;
    font-size: 14px;
  }
  button:disabled { background: #555; cursor: not-allowed; }
  #message {
    margin-top: 16px;
    padding: 10px;
    border-radius: 6px;
    font-size: 13px;
    display: none;
    text-align: center;
  }
  #message.success { background: #14532d; color: #86efac; display: block; }
</style>
</head>
<body>
  <div class="card">
    <h2>OmniGuard <span>수배자 등록 시스템</span></h2>
    <form id="registerForm">
      <label>수배자 ID</label>
      <input type="text" id="wanted_id" name="wanted_id" placeholder="예: W005" required>
      <label>수배자 이름</label>
      <input type="text" id="name" name="name" placeholder="예: 홍길동" required>
      <label>수배자 사진</label>
      <input type="file" id="file" name="file" accept="image/*" required>
      <button type="submit" id="submitBtn">등록하기</button>
    </form>
    <div id="message"></div>
  </div>
<script>
const form = document.getElementById("registerForm");
const messageBox = document.getElementById("message");
const submitBtn = document.getElementById("submitBtn");

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  submitBtn.disabled = true;
  submitBtn.textContent = "등록 중...";
  messageBox.style.display = "none";

  const nameValue = document.getElementById("name").value;
  const formData = new FormData();
  formData.append("wanted_id", document.getElementById("wanted_id").value);
  formData.append("name", nameValue);
  formData.append("file", document.getElementById("file").files[0]);

  try {
    const res = await fetch("/api/wanted-person", {
      method: "POST",
      body: formData
    });
    if (res.ok) {
      messageBox.className = "success";
      messageBox.textContent = `수배자 [${nameValue}] 등록 완료`;
      messageBox.style.display = "block";
      form.reset();
    } else {
      const errData = await res.json().catch(() => null);
      const errMsg = errData?.detail || `등록 실패 (${res.status})`;
      alert(errMsg);
    }
  } catch (err) {
    alert("서버 연결 실패: " + err.message);
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = "등록하기";
  }
});
</script>
</body>
</html>"""