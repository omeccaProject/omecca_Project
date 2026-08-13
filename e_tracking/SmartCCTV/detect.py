from ultralytics import YOLO
import cv2
import glob
import os

# ==========================
# 설정
# ==========================

# YOLO 모델
model = YOLO("yolo11n.pt")

# 차량 클래스(COCO)
VEHICLE_CLASSES = [2, 3, 5, 7]
# 2=Car, 3=Motorcycle, 5=Bus, 7=Truck

# 신뢰도
CONFIDENCE = 0.5

# 폴더
IMAGE_FOLDER = "images"
OUTPUT_FOLDER = "result"

os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# 이미지 목록
images = sorted(glob.glob(os.path.join(IMAGE_FOLDER, "*.jpg")))

print(f"\n총 {len(images)}장의 이미지를 처리합니다.\n")

# ==========================
# 차량 탐지
# ==========================

for idx, img_path in enumerate(images):

    results = model.predict(
        img_path,
        classes=VEHICLE_CLASSES,
        conf=CONFIDENCE,
        verbose=False
    )

    img = cv2.imread(img_path)

    boxes = results[0].boxes

    for box in boxes:

        x1, y1, x2, y2 = map(int, box.xyxy[0])

        # 박스
        cv2.rectangle(
            img,
            (x1, y1),
            (x2, y2),
            (0, 255, 0),
            2
        )

        # 라벨(신뢰도 제거)
        cv2.putText(
            img,
            "Vehicle",
            (x1, y1 - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 0),
            2
        )

    filename = os.path.basename(img_path)

    cv2.imwrite(
        os.path.join(OUTPUT_FOLDER, filename),
        img
    )

    print(f"[{idx+1}/{len(images)}] {filename}")

print("\n모든 차량 탐지가 완료되었습니다.")