from ultralytics import YOLO

def main():
    model = YOLO("yolo11n.pt")

    results = model.train(
        data="data.yaml",
        epochs=100,
        imgsz=640,
        batch=16,      # 8GB VRAM이니 16으로 상향 (노트북은 8이었음)
        workers=8,       # 6코어 CPU라 8까지 가능
        patience=25,
        name="road_hazard_v1"
    )

if __name__ == "__main__":
    main()