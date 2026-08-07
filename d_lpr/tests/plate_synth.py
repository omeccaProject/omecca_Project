"""한국형 번호판 합성 이미지 생성기.

실제 CCTV 번호판 샘플을 확보하기 전까지 전처리·검출 로직을 정량 검증하기 위한
테스트용 생성기. 실제 촬영 조건에서 인식률을 떨어뜨리는 요인을 재현한다.

    기울기 · 저해상도 · 야간 저조도 · 역광 · 모션 블러 · 센서 노이즈 · JPEG 열화

번호판 규격(흰색 바탕 신형 기준)은 520 x 110 mm 로, 가로/세로 비 약 4.7 이다.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# 한글 글리프가 있는 폰트를 순서대로 탐색
FONT_CANDIDATES = [
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 1),      # KR
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 1),
    ("C:/Windows/Fonts/malgunbd.ttf", 0),
    ("C:/Windows/Fonts/malgun.ttf", 0),
    ("/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf", 0),
]

PLATE_AR = 520 / 110       # 실제 번호판 가로/세로 비


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    for path, index in FONT_CANDIDATES:
        if not Path(path).exists():
            continue
        try:
            f = ImageFont.truetype(path, size, index=index)
            if f.getbbox("가")[2] > 0:      # 한글 글리프 존재 확인
                return f
        except Exception:
            continue
    raise RuntimeError("한글 폰트를 찾지 못했습니다 (합성 테스트 불가)")


@dataclass
class PlateCondition:
    """촬영 조건."""

    name: str = "ideal"
    angle: float = 0.0            # 기울기(도)
    height: int = 110             # 번호판 픽셀 높이 (해상도)
    brightness: float = 1.0       # 밝기 배율 (<1 야간)
    contrast: float = 1.0         # 대비 배율 (<1 역광/안개)
    blur: int = 0                 # 가우시안 블러 커널 (홀수, 0=없음)
    motion_blur: int = 0          # 모션 블러 길이(px)
    noise: float = 0.0            # 가우시안 노이즈 표준편차
    jpeg_quality: int = 0         # JPEG 재압축 품질 (0=미적용)
    glare: bool = False           # 조명 반사 반점


def render_plate(plate_no: str, height: int = 110) -> np.ndarray:
    """이상적인 조건의 번호판 이미지(BGR)를 만든다."""
    w, h = int(height * PLATE_AR), height
    scale = 4                       # 안티에일리어싱을 위해 크게 그린 뒤 축소
    img = Image.new("RGB", (w * scale, h * scale), (245, 245, 240))
    d = ImageDraw.Draw(img)

    # 테두리
    d.rectangle([0, 0, w * scale - 1, h * scale - 1], outline=(30, 30, 30), width=3 * scale)

    font = _load_font(int(h * scale * 0.62))
    bbox = d.textbbox((0, 0), plate_no, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    d.text(
        ((w * scale - tw) / 2 - bbox[0], (h * scale - th) / 2 - bbox[1]),
        plate_no, font=font, fill=(20, 20, 20),
    )

    arr = np.array(img.resize((w, h), Image.LANCZOS))
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)


def _geometric(plate: np.ndarray, cond: PlateCondition) -> tuple[np.ndarray, np.ndarray]:
    """해상도·기울기 등 기하 변환만 적용하고 번호판 영역 마스크를 함께 반환한다.

    마스크가 있어야 회전 시 생기는 여백을 정답 영역에서 제외할 수 있다.
    """
    img = plate.copy()
    mask = np.full(img.shape[:2], 255, np.uint8)

    # 1) 해상도
    if cond.height != img.shape[0]:
        w = int(cond.height * PLATE_AR)
        interp = cv2.INTER_AREA if cond.height < img.shape[0] else cv2.INTER_CUBIC
        img = cv2.resize(img, (w, cond.height), interpolation=interp)
        mask = cv2.resize(mask, (w, cond.height), interpolation=cv2.INTER_NEAREST)

    # 2) 기울기 (여백을 두고 회전해 잘림 방지)
    if abs(cond.angle) > 0.01:
        h, w = img.shape[:2]
        pad = int(max(h, w) * 0.3)
        img = cv2.copyMakeBorder(img, pad, pad, pad, pad, cv2.BORDER_REPLICATE)
        mask = cv2.copyMakeBorder(mask, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=0)
        h2, w2 = img.shape[:2]
        m = cv2.getRotationMatrix2D((w2 / 2, h2 / 2), cond.angle, 1.0)
        img = cv2.warpAffine(img, m, (w2, h2), flags=cv2.INTER_CUBIC,
                             borderMode=cv2.BORDER_REPLICATE)
        mask = cv2.warpAffine(mask, m, (w2, h2), flags=cv2.INTER_NEAREST,
                              borderMode=cv2.BORDER_CONSTANT, borderValue=0)

    return img, mask


def _photometric(img: np.ndarray, cond: PlateCondition) -> np.ndarray:
    """조명·블러·노이즈 등 광학적 열화만 적용한다.

    야간·역광은 번호판만이 아니라 장면 전체에 걸리므로, 장면 합성 시에는
    번호판을 붙인 뒤 이 함수를 전체 이미지에 적용해야 물리적으로 맞다.
    """

    # 3) 조명 반사 (헤드라이트·가로등이 번호판에 만드는 국소 반점)
    if cond.glare:
        h, w = img.shape[:2]
        overlay = np.zeros_like(img, dtype=np.float32)
        cx, cy = int(w * random.uniform(0.35, 0.65)), int(h * random.uniform(0.35, 0.65))
        r = max(4, int(min(h, w) * 0.16))
        cv2.circle(overlay, (cx, cy), r, (255, 255, 255), -1)
        overlay = cv2.GaussianBlur(overlay, (0, 0), r * 0.6)
        img = np.clip(img.astype(np.float32) + overlay * 0.6, 0, 255).astype(np.uint8)

    # 4) 밝기 / 대비
    if cond.brightness != 1.0 or cond.contrast != 1.0:
        f = img.astype(np.float32)
        mean = f.mean()
        f = (f - mean) * cond.contrast + mean * cond.brightness
        img = np.clip(f, 0, 255).astype(np.uint8)

    # 5) 모션 블러
    if cond.motion_blur > 1:
        k = np.zeros((cond.motion_blur, cond.motion_blur), np.float32)
        k[cond.motion_blur // 2, :] = 1.0 / cond.motion_blur
        img = cv2.filter2D(img, -1, k)

    # 6) 초점 흐림
    if cond.blur > 0:
        k = cond.blur if cond.blur % 2 == 1 else cond.blur + 1
        img = cv2.GaussianBlur(img, (k, k), 0)

    # 7) 센서 노이즈
    if cond.noise > 0:
        n = np.random.normal(0, cond.noise, img.shape)
        img = np.clip(img.astype(np.float32) + n, 0, 255).astype(np.uint8)

    # 8) JPEG 열화
    if cond.jpeg_quality > 0:
        ok, enc = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, cond.jpeg_quality])
        if ok:
            img = cv2.imdecode(enc, cv2.IMREAD_COLOR)

    return img


def apply_condition(
    plate: np.ndarray, cond: PlateCondition, seed: Optional[int] = None,
    with_mask: bool = False,
):
    """촬영 조건(기하 + 광학)을 모두 적용해 열화시킨다.

    with_mask=True 이면 (이미지, 번호판 영역 마스크) 튜플을 반환한다.
    """
    if seed is not None:
        np.random.seed(seed)
        random.seed(seed)

    img, mask = _geometric(plate, cond)
    img = _photometric(img, cond)
    return (img, mask) if with_mask else img


def render_vehicle_scene(
    plate_no: str,
    scene_size: tuple[int, int] = (640, 480),
    plate_height: int = 40,
    cond: Optional[PlateCondition] = None,
    seed: Optional[int] = None,
) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    """번호판이 붙은 차량 후면 장면과 정답 bbox(x1,y1,x2,y2)를 만든다.

    detector 의 CV 폴백(모폴로지 기반 후보 추출)을 검증하기 위한 입력.
    """
    if seed is not None:
        np.random.seed(seed)
        random.seed(seed)

    W, H = scene_size
    scene = np.full((H, W, 3), 70, np.uint8)
    scene += np.random.randint(-12, 12, scene.shape).astype(np.uint8)

    # 차체 (번호판보다 대비가 낮은 넓은 면)
    body_color = random.choice([(120, 120, 125), (45, 45, 50), (150, 150, 155)])
    cv2.rectangle(scene, (int(W * 0.12), int(H * 0.18)), (int(W * 0.88), int(H * 0.92)),
                  body_color, -1)
    # 후미등 (번호판과 헷갈릴 수 있는 가로로 긴 밝은 사각형 → 오탐 유도)
    cv2.rectangle(scene, (int(W * 0.15), int(H * 0.35)), (int(W * 0.32), int(H * 0.45)),
                  (40, 40, 190), -1)
    cv2.rectangle(scene, (int(W * 0.68), int(H * 0.35)), (int(W * 0.85), int(H * 0.45)),
                  (40, 40, 190), -1)

    cond = cond or PlateCondition(height=plate_height)

    # 기하 변환만 적용해 붙이고, 광학 열화는 장면 전체에 나중에 건다.
    # (야간·역광은 번호판만이 아니라 화면 전체에 걸리므로)
    plate, mask = _geometric(render_plate(plate_no, height=110), cond)
    ph, pw = plate.shape[:2]

    ox = (W - pw) // 2
    oy = int(H * 0.68)
    ex, ey = min(W, ox + pw), min(H, oy + ph)
    sub_p = plate[: ey - oy, : ex - ox]
    sub_m = mask[: ey - oy, : ex - ox]

    # 마스크 영역에만 합성한다 (회전 여백이 가짜 사각형으로 남지 않도록)
    roi = scene[oy:ey, ox:ex]
    roi[sub_m > 0] = sub_p[sub_m > 0]

    scene = _photometric(scene, cond)

    ys, xs = np.nonzero(sub_m)
    if len(xs) == 0:
        return scene, (ox, oy, ex, ey)
    gt = (ox + int(xs.min()), oy + int(ys.min()), ox + int(xs.max()) + 1, oy + int(ys.max()) + 1)
    return scene, gt


# --------------------------------------------------------------------------
# 검증용 조건 세트
# --------------------------------------------------------------------------
CONDITIONS: list[PlateCondition] = [
    PlateCondition("이상적",        height=110),
    PlateCondition("기울기 +12도",  height=110, angle=12),
    PlateCondition("기울기 -8도",   height=110, angle=-8),
    PlateCondition("저해상도 40px", height=40, jpeg_quality=70),
    PlateCondition("야간 저조도",   height=80, brightness=0.35, contrast=0.6, noise=8),
    PlateCondition("역광",          height=80, brightness=1.5, contrast=0.35),
    PlateCondition("조명 반사",     height=90, glare=True),
    PlateCondition("모션 블러",     height=90, motion_blur=7),
    PlateCondition("초점 흐림",     height=90, blur=5),
    PlateCondition("복합 열화",     height=48, angle=7, brightness=0.5,
                   contrast=0.6, noise=6, jpeg_quality=55),
]
