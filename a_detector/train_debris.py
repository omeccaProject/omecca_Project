from pathlib import Path
from ultralytics import YOLO

ROOT = Path(__file__).resolve().parent.parent   # omecca_Project 폴더

if __name__ == "__main__":
    model = YOLO("yolo11s.pt")

    model.train(
        data=str(Path(__file__).parent / "road_hazard_v3/data.yaml"),
        epochs=150,
        imgsz=640,
        batch=16,
        device=0,
        workers=4,
        amp=True,
        cache=False,
        patience=30,

        optimizer="AdamW",
        lr0=0.001,
        cos_lr=True,

        degrees=15.0,
        perspective=0.001,
        scale=0.6,
        hsv_h=0.02, hsv_s=0.8, hsv_v=0.6,
        mosaic=1.0,
        close_mosaic=15,
        fliplr=0.5,

        project=str(ROOT / "runs" / "detect"),   # ← 파일 위치 기준
        name="debris_kky_v4",
    )