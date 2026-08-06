import cv2

def frame_generator(source, target_fps=30):
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        raise RuntimeError(f"영상을 열 수 없습니다: {source}")

    orig_fps = cap.get(cv2.CAP_PROP_FPS) or 30
    skip = max(int(orig_fps // target_fps), 1)

    frame_idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if frame_idx % skip == 0:
            yield frame, frame_idx
        frame_idx += 1

    cap.release()


if __name__ == "__main__":
    count = 0
    for frame, idx in frame_generator("../data/videos/test1.mp4", target_fps=10):
        count += 1
        print(f"프레임 #{idx} 읽음, 크기: {frame.shape}")
    print(f"총 {count}개 프레임 처리 완료")