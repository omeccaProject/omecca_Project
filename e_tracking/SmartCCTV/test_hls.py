import cv2

HLS_URL = "https://strm1.spatic.go.kr/live/76.stream/chunklist_w1824089310.m3u8"

cap = cv2.VideoCapture(HLS_URL)

if not cap.isOpened():
    print("❌ HLS 영상을 열 수 없습니다.")
    exit()

print("✅ HLS 연결 성공!")

while True:
    ret, frame = cap.read()

    if not ret:
        print("❌ 프레임을 읽지 못했습니다.")
        break

    cv2.imshow("UTIC L010263 - Isu Station", frame)

    if cv2.waitKey(1) & 0xFF == 27:
        break

cap.release()
cv2.destroyAllWindows()