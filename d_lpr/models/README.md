# 모델 파일

번호판 인식에 쓰는 완성된 모델. **저장소에 함께 올린다.**

| 파일 | 크기 | 무엇 |
|---|---|---|
| `plate_det.pt` | 5.3MB | 번호판 **검출** YOLO. 사진에서 번호판 위치를 찾는다 |
| `plate.pth` | 14.4MB | 번호판 **인식** 모델. AI Hub 55,572장으로 학습 |
| `plate.py` | 2KB | 인식 모델의 신경망 구조 |
| `plate.yaml` | 1KB | 문자셋(67자)·입력 규격 |

## 왜 git 에 올리나

없으면 EasyOCR 기본 한국어 모델(`korean_g2`)로 **조용히 넘어간다.** 에러가 안
나기 때문에 성능만 떨어지고 원인을 모른다. 팀원이 clone 만으로 같은 결과를
내려면 함께 있어야 한다.

용량도 문제되지 않는다 — GitHub 제한은 파일당 100MB(경고 50MB)이고, 이 저장소에는
이미 `yolo11n.pt`(5.4MB), `best.pt`(6.0MB)가 커밋돼 있다.

**학습 중간 산출물은 올리지 않는다.** `.gitignore` 가 `*.pt` 를 막고 이 폴더만
예외로 열어 뒀다. epoch 마다 쏟아지는 체크포인트가 딸려 오면 저장소가 못 쓰게 된다.

## 설치

`plate_det.pt` 는 경로만 넘기면 되므로 그대로 쓴다.

```bash
python bench_lpr.py --dir plates_final --weights models/plate_det.pt
```

나머지 셋은 EasyOCR 이 **홈 폴더의 정해진 자리**에서만 읽는다. 복사해야 한다.

```bash
python install_model.py           # models/ → ~/.EasyOCR/
python install_model.py --check   # 설치됐는지 확인만
```

놓이는 자리:

```
~/.EasyOCR/model/plate.pth
~/.EasyOCR/user_network/plate.py
~/.EasyOCR/user_network/plate.yaml
```

세 개가 **전부** 있어야 쓴다. 하나라도 없으면 기본 모델로 돌아간다.

## 안 받아도 되는 것

EasyOCR 이 첫 실행 때 알아서 내려받는다. 올리지 않는다.

```
craft_mlt_25k.pth   79MB   글자 영역 검출 (CRAFT)
korean_g2.pth       15MB   기본 한국어 인식
```

## 되돌리기

```bash
# 기본 모델로 돌아가기
rm ~/.EasyOCR/model/plate.pth
```

`plate.pth` 하나만 지우면 된다.

## 이 모델의 성능

| 측정 | 값 |
|---|---|
| AI Hub 검증셋 5,000장 | 90.58% |
| 자체 촬영 사진 35대 (개발에 쓰지 않은 차량) | 45.7% |
| └ 지역명 2줄 판 13대 | 76.9% |

격차가 큰 이유는 **촬영 조건**이다. AI Hub 는 고정 설치 CCTV 라 거리·각도가
일정하고, 자체 촬영분은 원거리·야간·비스듬한 각도가 섞여 있다. 자세한 것은
`RUN.md` 4-2 절 참고.
