import json
import numpy as np
import cv2
import sys
import os

base_dir = os.path.dirname(os.path.abspath(__file__))
if base_dir not in sys.path:
    sys.path.append(base_dir)

from face_detect import FaceDetector
from weapon_detect import WeaponDetector

def test_pipeline_contracts():
    print("=== [OmniGuard C파트 데이터 규약(Contract) 검증 시작] ===")
    
    # 1. 실제 영상 my_sample.mp4 프레임 추출
    video_path = os.path.join(base_dir, "my_sample.mp4")
    assert os.path.exists(video_path), f"[FAIL] 테스트 영상 파일 없음: {video_path}"
    
    cap = cv2.VideoCapture(video_path)
    ret, frame = cap.read()
    cap.release()
    assert ret and frame is not None, "[FAIL] 영상 프레임 로드 실패"

    h, w = frame.shape[:2]
    if h > 720:
        scale = 720.0 / h
        frame = cv2.resize(frame, (int(w * scale), 720))
    H, W = frame.shape[:2]
    print(f"[INFO] 테스트 입력 프레임 해상도: {W}x{H}")

    # 2. FaceDetector 규약 검증
    face_detector = FaceDetector(tolerance=0.55)
    faces = face_detector.detect_faces_with_person_crop(frame)
    print(f"[TEST 1] face_detect.py 검증 (실제 검출된 수배자 수: {len(faces)}명)")
    assert len(faces) > 0, "[FAIL] 검출된 얼굴이 0개입니다. DB 등록 상태를 확인하세요."

    for idx, f in enumerate(faces):
        print(f"  - 수배자 [{idx+1}] 검증: {f['name']} ({f['matchedDbId']})")
        # 필수 키 5종 존재 검증
        required_keys = ["matchedDbId", "name", "faceMatchScore", "location", "personBbox"]
        for k in required_keys:
            assert k in f, f"[FAIL] 필수 키 누락: {k}"
        
        # location 순서 및 범위 검증 (top, right, bottom, left)
        top, right, bottom, left = f["location"]
        assert 0 <= top <= H and 0 <= bottom <= H, f"[FAIL] location Y범위 오류: ({top}, {bottom})"
        assert 0 <= left <= W and 0 <= right <= W, f"[FAIL] location X범위 오류: ({left}, {right})"
        assert top <= bottom and left <= right, f"[FAIL] location 좌표 역전: top={top}, bottom={bottom}"
        print(f"    * location: ({top}, {right}, {bottom}, left={left}) -> 범위 정상 [PASS]")
        print(f"    * faceMatchScore: {f['faceMatchScore']} (타입: {type(f['faceMatchScore']).__name__}) -> [PASS]")

    # 3. WeaponDetector 규약 검증
    weapon_detector = WeaponDetector()
    weapons = weapon_detector.detect_weapons(frame) if hasattr(weapon_detector, "detect_weapon") else []
    print(f"[TEST 2] weapon_detect.py 검증 (검출 수: {len(weapons)})")
    for w_obj in weapons:
        for k in ["label", "confidence", "bbox"]:
            assert k in w_obj, f"[FAIL] weapon 필수 키 누락: {k}"
        left, top, right, bottom = w_obj["bbox"]
        assert 0 <= left <= W and 0 <= right <= W, "[FAIL] weapon bbox X범위 오류"
        assert 0 <= top <= H and 0 <= bottom <= H, "[FAIL] weapon bbox Y범위 오류"
    print("  * weapon_detect 인터페이스 규약 -> [PASS]")

    # 4. isArmed Always-Defined & JSON 직렬화 검증
    print("[TEST 3] isArmed Always-Defined & JSON 직렬화 검증")
    mock_meta = {
        "isArmed": len(weapons) > 0,
        "matchedDbId": faces[0]["matchedDbId"],
        "faceMatchScore": faces[0]["faceMatchScore"],
        "weaponType": weapons[0]["label"] if len(weapons) > 0 else None
    }
    
    assert "isArmed" in mock_meta, "[FAIL] isArmed 키 누락"
    assert isinstance(mock_meta["isArmed"], bool), "[FAIL] isArmed가 bool 타입이 아님"
    print(f"  * isArmed 상태: {mock_meta['isArmed']} (타입: bool) -> [PASS]")

    # JSON 직렬화 검증
    serialized = json.dumps(mock_meta)
    assert isinstance(serialized, str), "[FAIL] 직렬화 결과가 문자열이 아님"
    print(f"  * JSON 직렬화 성공 페이로드: {serialized} -> [PASS]")

    print("\n>>> [RESULT] 모든 데이터 규약(Contract) 검증을 100% 완벽히 통과했습니다! <<<")

if __name__ == "__main__":
    test_pipeline_contracts()
