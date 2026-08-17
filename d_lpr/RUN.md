# 실행 방법

박지원 담당 모듈(불법 유턴 · 신호 위반 · 번호판 인식) 실행 순서.
모든 명령은 `d\omeca-lpr` 폴더에서 실행한다.

```powershell
cd C:\Users\박지원\Desktop\d\omeca-lpr
.venv64\Scripts\activate
```

프롬프트 앞에 `(.venv64)` 가 붙으면 준비 완료.

---

## 지금 당장 되는 것 (설치 없이)

`.venv64` 에 이미 opencv·numpy 가 있어서 아래는 바로 돌아간다.

```powershell
python run_uturn.py --fake --save output\fake_uturn.mp4
```

합성 화면에 차 **4대**가 지나간다 — 유턴 · 좌회전 · 직진 · 신호위반.
**정확히 2건**(불법 유턴 1 + 신호 위반 1)이 잡히면 정상이다.
좌회전·직진은 안 잡혀야 한다 (오탐 반례).

```
합성 모드: 유턴·좌회전·직진·신호위반 4대 → 유턴 1건 + 신호위반 1건, 정확히 2건이 정상
  ★ 불법 유턴  t=  5.60s  track=#101  no_sign  유턴 금지 구간에서 유턴 ...
  ★ 신호 위반  t=  5.87s  track=#104  INT-FAKE  적색 신호 중 정지선 통과 후 교차로 진출 ...
위반 2건 (불법 유턴 1 / 신호 위반 1)
```

`output\fake_uturn.mp4` 를 열면 판정 과정이 그려져 있다. **발표 시연에 그대로 쓸 수 있다.**

---

## 추가 설치가 필요한 것

| 하고 싶은 것 | 설치 |
|---|---|
| 실제 영상으로 유턴 감지 | `pip install ultralytics` |
| 테스트 돌려서 검증 | `pip install pytest` |
| 신호 API 점검·교차로 찾기 | 없음 (표준 라이브러리만) |
| 번호판 인식 | 이미 설치됨 (easyocr) |

```powershell
pip install ultralytics pytest
```

`ultralytics` 는 torch 를 쓰는데 이미 깔려 있으므로(2.13.0+cpu) 금방 끝난다.
YOLO 가중치(`yolo11n.pt`)는 첫 실행 때 자동으로 받는다.

---

## 1. 테스트로 전체 검증 (30초)

```powershell
python -m pytest tests -q
```

```
382 passed
```

여기서 다 통과하면 판정 로직·신호 API 연동·번호판 인식이 전부 정상이다.

---

## 1-2. 실영상 검증 결과 (2026-08-13)

`불법유턴3.mp4` (1920×1080, 24fps, 10초, 고정 카메라)로 **실제 검출 성공**.

```
중앙선 1개: center_uturn3(금지)     ← 노란 픽셀 검출로 x≈945 확인
  ★ 불법 유턴  t=6.08s  track=#1  no_sign
     중앙선 통과 후 진행 방향 반전 (진입 142° → 진출 -57°, 각도차 162°)
위반 1건 (불법 유턴 1 / 신호 위반 0)
```

- 주인공 차량이 **197프레임(8.2초) 연속 추적** — 선회 중 ID 안 끊김
- 배경 차량 6대는 오탐 없음
- 결과 영상: `output/uturn3_result.mp4`

> 이 검증의 차량 검출은 `quick_track.py`(배경차감)로 했다. 정식 수치는
> 김준호 `e_tracking`(YOLO11m) 로그로 다시 뽑아야 한다.

---

## 2. 실제 영상으로 유턴 감지

### 2-1. 영상 준비

사거리에서 30초~1분 촬영. **노란 중앙선이 화면에 보여야 한다.** 카메라는 고정.

### 2-2. 중앙선 그리기

```powershell
python draw_roi.py --video 내영상.mp4 --cam CAM-TEST
```

첫 프레임 창이 뜬다.

| 키 | 뜻 |
|---|---|
| `1` | 중앙선 · 유턴 **금지** (표지판 없는 곳) |
| `2` | 중앙선 · 유턴 **허용** (유턴 표지판 있는 곳) |
| `3` / `4` | 정지선 / 진출선 (신호위반용, 선택) |
| 좌클릭 2번 | 선 하나 완성 |
| `z` / `r` | 마지막 취소 / 전부 지우기 |
| `w` | **저장하고 종료** |

`1` 누르고 노란 실선 위에 좌클릭 두 번, `w`. 끝.

### 2-3. 실행

```powershell
python run_uturn.py --video 내영상.mp4 --cam CAM-TEST --show --save output\result.mp4
```

화면 색

- 초록 박스 — 일반 차량
- **빨강 박스** — 중앙선(또는 적색 정지선)을 넘어 지켜보는 중
- **빨강 박스 + 하단 배너** — 위반 확정

느리면 `--stride 2 --imgsz 640` 을 붙인다.

---

## 3. 신호까지 반영

### 방법 A — 영상 보고 직접 적기 (녹화본용, 권장)

```powershell
copy signal_timeline.example.json signal_timeline.json
notepad signal_timeline.json
```

영상을 보면서 신호가 바뀌는 **초**를 적는다. 영상 시작이 0초.

```json
{ "SIG-1": [ {"at": 0, "phase": "red"}, {"at": 12, "phase": "left_arrow"} ] }
```

```powershell
python run_uturn.py --video 내영상.mp4 --cam CAM-TEST --signal signal_timeline.json --show
```

### 방법 B — 실시간 API (실시간 CCTV용)

KLID 「교통안전 신호등 실시간 정보」에 이미 붙여 놨다. 주소·필드는 실제
응답으로 확인했으니 바로 돌아간다. 할 일은 **내 교차로 ID 찾기** 하나뿐이다.

```powershell
python signal_probe.py                          # 연결 확인 + 살아있는 교차로
python signal_probe.py --near 37.5665,126.978   # 촬영 지점 좌표로 찾기
python signal_probe.py --find 사거리             # 이름으로 찾기
python signal_probe.py --watch 1057             # 8방향 신호 실시간 관찰
```

찾은 값(`교차로ID:방향`, 예: `1057:wt`)을 `config_zones.json` 의 해당 라인
`signal_id` 에 넣고 실행한다.

```powershell
python run_uturn.py --cam CAM-TEST --signal-api
```

> 유턴 신호가 따로 오는 API라, 좌회전 화살표로 추론하지 않고 **유턴 신호를
> 직접 보고** 판정한다. 보행 신호도 실제 값이 온다.

> 녹화 영상 + 실시간 API 는 시각이 안 맞는다. 녹화본은 방법 A 를 쓴다.

---

## 3-2. 김준호 e_tracking 결과로 판정 (팀 통합)

김준호 모듈이 만든 추적 JSON 을 그대로 먹인다. **YOLO 도, 우리 추적기도 필요 없다.**

```powershell
# 1) 김준호 쪽에서 추적 로그 생성
cd ..\omecca_Project\e_tracking\SmartCCTV
python export_track_log.py --video videos\내영상.mp4 --output web\data\track.json --cam-id ISU

# 2) 그 로그로 유턴 판정
cd C:\Users\박지원\Desktop\d\omeca-lpr
python run_uturn.py --track-log ..\omecca_Project\e_tracking\SmartCCTV\web\data\track.json ^
                    --cam ISU --save output\result.mp4
```

`--video` 를 같이 주면 그 영상 위에 판정 결과를 그려 준다. 안 줘도 좌표만으로
판정은 되고, 화면은 빈 캔버스로 나온다.

출력에 e_tracking 이 잡은 이상운전 에피소드도 같이 찍히므로, 같은 차량을
양쪽이 어떻게 봤는지 대조할 수 있다.

### 한 번에 돌리기 — `run_all.ps1`

위 두 단계를 영상 5개에 대해 자동으로 돈다. **팀 코드는 그대로 두고 출력 경로만
우리 쪽으로 돌린다** — `omecca_Project` 폴더에는 아무것도 안 쓴다.

```powershell
cd C:\Users\박지원\Desktop\d\omeca-lpr
.\run_all.ps1                  # 불법유턴3·5·6·7 + 신호위반2 전부
.\run_all.ps1 -Only UTURN3     # 하나만
.\run_all.ps1 -SkipTrack       # 추적은 건너뛰고 판정만 다시 (ROI 고쳤을 때)
```

결과는 전부 `omeca-lpr\output` 에 떨어진다.

| 파일 | 만든 주체 |
|---|---|
| `y_UTURN3.json` | 김준호 e_tracking (추적 로그) |
| `y_UTURN3_events.json` | 우리 모듈 (위반 이벤트) |
| `y_UTURN3_result.mp4` | 우리 모듈 (판정 과정 영상) |

마지막에 요약이 찍힌다.

```
UTURN3    위반 1건  (프레임 240, 추적기 e_tracking(SmartCCTV))
            t=  6.08s  #1  불법 유턴  no_sign
```

> `ultralytics` 가 없으면 1단계에서 전부 실패한다. 그때는 `quick_track.py` 로
> 만들어 둔 로그가 이미 `output\uturn3.json` 등에 있으니 `-SkipTrack` 으로
> 판정만 다시 돌릴 수 있다 (단, 파일명을 `y_UTURN3.json` 으로 맞춰야 한다).

---

## 4. 번호판 인식만 따로

```powershell
python try_lpr.py --image 번호판사진.jpg
```

### 4-2. 인식률 측정 (실데이터)

`plates/` 에 사진을 넣고 **파일 이름을 번호판 번호로** 저장한 뒤 돌린다.

```powershell
python bench_lpr.py --save-fail
```

### 사진 세 묶음을 쓰는 이유 — 읽기 전에 알아야 할 것

    plates/        개발용 50장.  근접·주간·정면. 여기 결과를 보고 고쳤다.
    plates_test/   개발용 50장.  원거리·야간·비스듬·노란판.
    plates_final/  최종 시험지.  다 고친 뒤 **딱 한 번**만 쓴다.

처음에는 `plates/` 하나로만 쟀고 **98%** 가 나왔다. 그런데 그 50장에서 틀린
사진을 보고 코드를 고쳤으므로, **시험지를 보고 공부한 점수**였다.

한 번도 안 본 `plates_test/` 로 재니 **42%** 였다. 56%p 차이다.
개발용 사진으로 잰 숫자는 성능 추정치가 될 수 없다는 것이 이걸로 확인됐다.

**따라서 아래 개발용 수치는 "이 변경이 도움이 됐나"를 보는 용도이지,
성능을 나타내는 숫자가 아니다.** 발표에 쓸 숫자는 `plates_final/` 것뿐이다.

### 개발용 100장 (plates + plates_test) 경과

| 단계 | 정확도 |
|---|---|
| 검출기 없음 | 70/100 |
| 번호판 검출기(YOLO) 적용 | 67/100 |
| + 2줄 번호판 정렬 수정 | 67/100 |

**세 번 연속 제자리라 여기서 멈췄다.** 총점은 안 움직이고 오류 유형만
돌아간다 — 잘림을 고치면 여분 글자가 늘고, 2줄을 고치면 또 다른 것이 나온다.
남은 오답은 275x238 같은 작은 이미지, 심한 블러, 원거리 촬영이 대부분이라
규칙으로 손댈 여지가 적다.

검출기는 총점을 못 올렸지만 **잘림을 11건에서 2건으로 줄였다.** 대신 번호판
전체를 제대로 잡게 되면서 2줄 번호판 문제가 새로 드러났다.

### 확실한 것만 쓰는 운영

| 임계값 | 채택 | 정답 | 정밀도 |
|---|---|---|---|
| 0.40 (현재) | 81 | 66 | 81.5% |
| 0.70 | 52 | 50 | 96.2% |
| **0.80** | 35 | 35 | **100%** |

전체 정확도와 별개로 **신뢰도가 높은 것은 거의 틀리지 않는다.** 실제 단속
시스템처럼 확실한 것만 자동 처리하고 나머지는 사람이 확인하는 운영이 가능하다.

### 무엇이 통했고 무엇이 안 통했나

**통한 것 — 사진이 아니라 '번호판의 성질'을 고친 것**

- 번호판은 형식이 고정이다 → 형식에 안 맞으면 안쪽의 유효한 조각을 꺼낸다
- 한글 없는 한국 번호판은 없다 → 숫자만 나오면 한글 자리를 다시 읽는다
- 번호판은 2줄일 수 있다 → y 로 줄을 나눠 위→아래로 잇는다
- 전용 모델은 글자 67자만 안다 → 한글↔숫자 혼동이 구조적으로 불가능

**안 통한 것 — 그 사진들에만 맞춘 것**

- 문자 분할 기준값을 47장에 최적화 → 분할 정확도 36%→77%, **최종 정확도는 78%→76%**
  중간 지표가 좋아진다고 최종 지표가 좋아지지 않는다. 되돌렸다.
- 검출 상자 병합 수정 → `plates/` 잘림 3건이 0건이 됐지만,
  새 사진에서는 같은 유형이 11건 나왔다. 3장에만 맞춘 수정이었다.

수정할 때 통과해야 할 질문은 하나다.
**"이 사진들을 한 번도 안 봤어도 이 수정이 옳다고 말할 수 있는가."**

사진은 `plates/` 에 두고 **커밋하지 않는다** (개인정보, `.gitignore` 등록됨).
공유할 것은 `output/lpr_bench.md` 의 수치뿐이다.

### 번호판 전용 모델

`~/.EasyOCR/` 에 아래 세 파일이 있으면 자동으로 쓴다. 없으면 기본 `korean_g2`.

    model/plate.pth            가중치
    user_network/plate.py      모델 구조
    user_network/plate.yaml    글자 목록(67자)·입력 크기

**되돌리려면 `plate.pth` 만 지우면 된다.**

만드는 방법은 `prep_aihub.py` → `train_plate_colab.ipynb` 순서다.
학습 데이터는 AI Hub 「자동차 차종/연식/번호판 인식용 영상」 2만 장.

### 번호판 검출 모델 (선택)

`--weights plate_det.pt` 로 넘기면 번호판 위치를 YOLO 로 찾는다. 없으면
EasyOCR 의 범용 글자 검출로 대신한다.

    python bench_lpr.py --dir plates --weights plate_det.pt

만드는 방법은 `train_detector_colab.ipynb`. 학습 데이터는 Roboflow
`car-plate-data` 1,000장 (CC BY 4.0). 한글 파일명이 내보내기 과정에서
날아가 **인식** 학습에는 못 쓰지만, 상자 좌표는 멀쩡해서 **검출**에는 쓸 수 있다.

---

## 4-3. MySQL 실접속 점검

평소에는 SQLite 로 동작한다. 운영에서 MySQL 을 쓸 때 **정말 붙는지** 확인한다.

```powershell
pip install pymysql
python check_mysql.py --create --user root --password 비밀번호
```

**실측 결과 (2026-08-15, MySQL 8.0.42)** — 7단계 전부 통과

| 단계 | 확인 내용 | 결과 |
|---|---|---|
| 1 | pymysql 설치 | 2.2.8 |
| 2 | 서버 접속 | MySQL 8.0.42 |
| 3 | 데이터베이스 `omeca` | 존재 |
| 4 | 테이블 3개 (`vehicle`/`violation`/`plate_read_log`) | 존재 |
| 5 | 읽기 | vehicle 12행 |
| 6 | **한글 저장 (utf8mb4)** | `99하9999` 왕복 성공 |
| 7 | 실제 조회 경로 | `driver = mysql` |

`VehicleRepository` 는 MySQL 접속에 실패하면 **조용히 SQLite 로 넘어간다.**
시연이 멈추지 않게 하려는 설계인데, 그래서 평소 실행만으로는 어느 쪽을 쓰는지
알 수 없다. 이 스크립트는 폴백 없이 붙어 보고 실패 원인을 그대로 보여준다.

> 6번을 넣은 이유 — MySQL 을 기본 설정으로 설치하면 문자셋이 `latin1` 인
> 경우가 있다. 그러면 `12가3456` 이 `12?3456` 으로 저장되는데 **에러가 안 난다.**
> 실제로 넣고 꺼내 봐야 안다.

### 운영에서 MySQL 쓰기

```yaml
# config.yaml
db:
  driver: mysql
  host: localhost
  port: 3306
  user: omeca
  database: omeca
```

비밀번호는 `config.yaml` 에 적지 않는다. `.env` 의 `OMECA_DB_PASSWORD` 를 쓴다.

팀 DB(`omecca`: target/roi/event/report)와는 테이블이 겹치지 않는다.
우리 것은 차량 원장·위반·인식로그로, 미등록 차량 판별에 쓴다.

---

## 5. 실시간 CCTV 보기

```powershell
python its_cctv.py --list --area 서울
python its_cctv.py --play 0 --area 서울
```

인증키는 `.env` 의 `ITS_API_KEY` 에서 읽는다 (이미 채워져 있음).

---

## 자주 나는 오류

| 메시지 | 원인 · 해결 |
|---|---|
| `ModuleNotFoundError: ultralytics` | `pip install ultralytics` |
| `cv2.imshow ... not implemented` | headless 버전이 깔림 → `pip uninstall opencv-python-headless` 후 `pip install opencv-python` |
| `'CAM-TEST' 카메라 설정이 없습니다` | `draw_roi.py` 로 먼저 중앙선을 그린다 |
| `중앙선(line_type=center)이 없습니다` | `draw_roi.py` 에서 `1` 또는 `2` 모드로 그려야 한다 |
| `--video 를 지정하거나 --fake` | 둘 중 하나는 있어야 한다 |
| 유턴을 했는데 안 잡힘 | `UTURN_GUIDE.md` 7장 참고. 먼저 `--show` 로 차 번호(`#7`)가 선회 중 안 바뀌는지 확인 |
| 신호 API `SERVICE_KEY_IS_NOT_REGISTERED` | 승인 직후면 1시간쯤 기다려야 한다. 또는 Decoding 키를 넣은 것 |
| `교차로 XXXX 는 실시간 신호가 안 옵니다` | 전국 4,239곳 중 1,399곳만 실시간 신호가 온다. `--near` 로 다른 교차로를 찾는다 |

---

## 파일별 역할 한눈에

| 명령 | 하는 일 | 필요한 것 |
|---|---|---|
| `run_uturn.py --fake` | 합성 장면으로 로직 점검 | 없음 |
| `run_uturn.py --video` | 실제 영상 유턴 감지 (자체 YOLO) | ultralytics |
| `run_uturn.py --track-log` | **김준호 추적 결과로 판정** | 없음 |
| `run_all.ps1` | **추적→판정 일괄 실행 (영상 5개)** | ultralytics |
| `quick_track.py` | 검증용 간이 추적기 (YOLO 없이 로그 생성) | opencv |
| `bench_lpr.py` | **번호판 인식률 측정 (실데이터)** | easyocr |
| `prep_aihub.py` | AI Hub 데이터 → 학습 세트 | opencv |
| `train_plate_colab.ipynb` | 번호판 전용 모델 학습 (Colab GPU) | — |
| `train_detector_colab.ipynb` | 번호판 검출 모델 학습 (Colab GPU) | — |
| `check_mysql.py` | **MySQL 실접속 점검 (7단계)** | pymysql |
| `draw_roi.py` | 중앙선·정지선 그리기 | opencv |
| `signal_probe.py` | 신호 API 점검·내 교차로 찾기 | 없음 |
| `try_lpr.py` | 번호판 인식 단독 실행 | easyocr |
| `its_cctv.py` | 실시간 CCTV 보기 | opencv |
| `pytest tests -q` | 전체 검증 (382개) | pytest |

자세한 설명은 `UTURN_GUIDE.md`.
