import time
import cv2
import numpy as np
from event_publisher import EventPublisher

publisher = EventPublisher()

dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
cv2.putText(dummy_frame, "OMNI-GUARD TEST", (50, 240), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

print("\n" + "="*70)
print("🚀 [동일 이벤트타입(WANTED_PERSON) / 서로 다른 대상 쿨다운 분리 실측]")
print("="*70 + "\n")

# [시나리오 1] 0.0초: W001 (이시헌) 진입
print("[1] 0.0초: Target W001(이시헌) 감지 시도")
meta1 = {"matchedDbId": "W001", "faceMatchScore": 0.92, "isArmed": False, "weaponType": None}
res1 = publisher.send_event(
    event_type="WANTED_PERSON",
    confidence=0.92,
    bbox=[100, 100, 200, 200],
    cam_id="CAM-01",
    meta=meta1,
    frame=dummy_frame
)
print(f" -> 결과: {'[SUCCESS 201]' if res1 else '[FAIL/DROPPED]'}\n")

time.sleep(0.5)

# [시나리오 2] 0.5초: W002 (김관용) 진입 (동일 WANTED_PERSON, 다른 대상 -> 전송 성공해야 함)
print("[2] 0.5초: Target W002(김관용) 감지 시도 (동일 WANTED_PERSON, 0.5초 간격 진입)")
meta2 = {"matchedDbId": "W002", "faceMatchScore": 0.88, "isArmed": False, "weaponType": None}
res2 = publisher.send_event(
    event_type="WANTED_PERSON",
    confidence=0.88,
    bbox=[150, 150, 250, 250],
    cam_id="CAM-01",
    meta=meta2,
    frame=dummy_frame
)
print(f" -> 결과: {'[SUCCESS 201]' if res2 else '[FAIL/DROPPED]'}\n")

time.sleep(0.5)

# [시나리오 3] 1.0초: W001 (이시헌) 재진입 (동일 대상 -> 쿨다운 차단되어야 함)
print("[3] 1.0초: Target W001(이시헌) 재진입 (동일 대상 쿨다운 억제 검증)")
meta3 = {"matchedDbId": "W001", "faceMatchScore": 0.93, "isArmed": False, "weaponType": None}
res3 = publisher.send_event(
    event_type="WANTED_PERSON",
    confidence=0.93,
    bbox=[100, 100, 200, 200],
    cam_id="CAM-01",
    meta=meta3,
    frame=dummy_frame
)
print(f" -> 결과: {'[SUCCESS 201]' if res3 else '[IGNORED by Cooldown (정상 동작)]'}\n")

print("="*70)
if res1 and res2 and not res3:
    print("🎯 [최종 판정: 합격] 서로 다른 대상(W001, W002)은 독립 발행되고, 동일 대상(W001)만 정확히 쿨다운 차단됨.")
else:
    print(f"[*] 상태 점검: res1={res1}, res2={res2}, res3={res3}")
print("="*70)
