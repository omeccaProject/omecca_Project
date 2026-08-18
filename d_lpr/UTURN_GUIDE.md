# 불법 유턴 감지 — 구현 내용과 실행 순서

담당: 박지원 (개발 내용 ⑦ 불법 유턴·신호 위반 감지)
마지막 확인: 2026-08-13 · `pytest tests -q` → **354 passed**

---

## 0. 판정 원리 (왜 이렇게 만들었나)

전 차량을 계속 추적하면서 "유턴처럼 생긴 궤적"을 찾는 방식은 무겁고 오탐이 많다.
대신 **중앙선(노란 실선)을 넘는 사건**을 1차 트리거로 쓴다.

```
정상 주행에서 노란 실선을 넘는 일은 거의 없다
  → 넘었다는 사실 자체가 강한 신호
  → 넘은 그 차량만 4초 지켜본다 (화면에 40대가 있어도 지켜보는 건 1~2대)
  → 진행 방향이 150도 이상 뒤집혔으면 유턴 확정
  → 그 시점의 표지·신호로 합법/불법을 가른다
```

좌회전 차량은 애초에 중앙 실선을 넘지 않고, 넘더라도 방향 반전이 아니므로
2단계에서 걸러진다. 실선에서 차로를 바꾸면 그건 역주행이라 별개 문제다.

### 위반 3종

| subtype | 조건 | 예시 |
|---|---|---|
| `no_sign` | 유턴 표지가 없는 중앙선을 넘어 유턴 | 신호와 무관하게 항상 위반 |
| `red_light` | 유턴 허용 구간이지만 적색 신호 | 빨간불에 유턴 |
| `wrong_signal` | 좌회전 화살표가 아닌데 유턴 | 직진 녹색만 켜진 곳에서 유턴 |

합법으로 보고 **이벤트를 내지 않는** 경우

- 좌회전 화살표(`left_arrow`) 또는 직진+좌회전(`green_left`)
- 보행 녹색 (해당 교차로가 그렇게 운영되는 경우)
- 신호를 모를 때(`unknown`) — 근거 없이 위반으로 단정하지 않는다

---

## 1. 준비

```bash
pip install opencv-python ultralytics
```

`opencv-python-headless` 가 깔려 있으면 화면(`--show`)이 안 뜬다.

```bash
pip uninstall opencv-python-headless
pip install opencv-python
```

---

## 2. 먼저 로직만 점검 (영상·YOLO 없이 5초)

```bash
python run_uturn.py --fake --save output/fake_uturn.mp4
```

합성 화면에 유턴 1대 · 좌회전 1대 · 직진 1대가 나온다.
**유턴 1건만** 잡히면 판정 로직은 정상이다.

```
합성 모드: 유턴 1대 · 좌회전 1대 · 직진 1대 → 유턴 1건만 잡혀야 정상
  ★ 불법 유턴  t=  5.60s  track=#101  no_sign
     중앙선 통과 후 진행 방향 반전 (진입 -90° → 진출 118°, 각도차 152°)
불법 유턴 1건
```

`output/fake_uturn.mp4` 를 열어 보면 판정 과정이 그려져 있다.

---

## 3. 영상 촬영

사거리에서 30초~1분. 체크할 것

- **중앙선(노란 실선)이 화면에 보일 것** — 이게 없으면 판정을 못 한다
- 카메라 고정 (흔들리면 좌표가 어긋난다)
- 차량 신호등이 같이 보이면 좋다 (신호 타임라인을 적기 편하다)
- 번호판이 보이는 영상은 개인정보다. 발표 자료에 넣을 땐 번호판을 가린다

---

## 4. 중앙선 그리기

```bash
python draw_roi.py --video 내영상.mp4 --cam CAM-TEST
```

첫 프레임이 뜬다. 조작은 이렇다.

| 키 | 뜻 |
|---|---|
| `1` | 중앙선 · 유턴 **금지** (표지판 없는 곳) |
| `2` | 중앙선 · 유턴 **허용** (유턴 표지판이 있는 곳) |
| `3` | 정지선 (신호위반 판정용, 선택) |
| `4` | 진출선 (선택) |
| 좌클릭 2번 | 선 하나 완성 |
| `z` | 마지막 선 취소 · `r` 전부 지우기 |
| `w` | 저장하고 종료 · `q` 저장 없이 종료 |

유턴만 볼 거면 `1`(또는 `2`) 하나면 된다. **차량이 실제로 넘어가는 노란 실선 위에**
길게 긋는다. 4K 영상을 노트북 화면에서 축소해 그려도 원본 좌표로 저장된다.

결과는 `config_zones.json` 의 해당 `cam_id` 항목에 들어간다.

---

## 5. 신호 타임라인 적기 (선택, 하지만 권장)

신호제어기 연동은 아직 못 하므로, **영상을 보면서 신호가 바뀌는 초를 적는다.**
값이 영상의 진짜 신호이므로 판정 결과도 진짜다. 자동으로 못 읽을 뿐이다.

`signal_timeline.json` 을 만든다 (`signal_timeline.example.json` 복사해서 수정):

```json
{
  "SIG-1": [
    {"at": 0,  "phase": "red"},
    {"at": 12, "phase": "left_arrow"},
    {"at": 20, "phase": "green"},
    {"at": 48, "phase": "yellow"},
    {"at": 51, "phase": "red"}
  ],
  "SIG-1-PED": [
    {"at": 0,  "ped": "red"},
    {"at": 12, "ped": "green"},
    {"at": 20, "ped": "red"}
  ]
}
```

- `at` 은 **영상 시작을 0초**로 한 상대 시간
- `phase`: `red` `yellow` `green` `left_arrow` `green_left`
- `SIG-1-PED` 는 보행 신호. **실제 연계는 아직 안 되므로 "연계했다고 가정"하고
  영상 보고 직접 적는 값이다.** 발표에서 이 점을 그대로 말하는 게 맞다.
- `signal_id` 는 `draw_roi.py` 가 `SIG-1` 로 넣어 둔다. 바꾸려면 `config_zones.json`
  에서 해당 라인의 `signal_id` 를 고치고 타임라인 키도 맞춘다.

타임라인이 없으면 `no_sign`(유턴 금지 구간) 판정만 돌아간다.

---

## 5-2. 실시간 신호 API 연동 — 실제로 붙였다

**행정안전부 한국지역정보개발원 「(전국 통합데이터) 교통안전 신호등 실시간 정보」**
공공데이터포털 15157604 · Base URL `https://apis.data.go.kr/B551982/rti`

| 오퍼레이션 | 내용 | 규모 |
|---|---|---|
| `/crsrd_map_info` | 교차로 ID·이름·위경도 | 전국 4,239곳 |
| `/tl_drct_info` | 실시간 점등상태·잔여시간 | 1,399곳 |

실제로 호출해서 응답을 받아 확인했다. 아래는 전부 **추측이 아니라 실측**이다.

### 실제로 뭐가 오는지 — 전수 조사 결과 (2026-08-13)

규격에는 유턴·보행 신호가 다 있지만, **실제로 값이 채워져 오는지는 별개**라
1,399행을 전부 훑어 세어 봤다.

| 항목 | 실측 |
|---|---|
| 교차로 목록(`/crsrd_map_info`) | 4,239곳 |
| 실시간 신호가 오는 곳(`/tl_drct_info`) | **1,342곳** |
| 그중 값이 하나라도 채워진 곳 | 1,380행 |
| **유턴 신호(`Utsg`)에 값이 있는 곳** | **1곳** (동대문역, 서쪽 진입, 적색) |

**유턴 신호는 사실상 안 온다.** 규격에 필드는 있지만 전국에서 1곳뿐이다.
앞서 "유턴 신호를 직접 본다"고 한 건 **내가 규격만 보고 앞서간 것이다.**
코드는 값이 오면 쓰도록 돼 있지만(그 1곳에서는 실제로 동작한다), 현실적으로는
**종전대로 좌회전·보행 신호로 추론하는 경로가 주력**이다.

보행 신호(`Pdsg`)는 꽤 온다. 이건 "연계 가정"이 아니라 실제 값이다.

### 데이터 구조 — 교차로 하나에 신호가 48개

```
교차로(crsrdId) × 진입방향 8개 × 이동류 6개

진입방향  nt 북 · et 동 · st 남 · wt 서 · ne 북동 · se 남동 · sw 남서 · nw 북서
이동류    Stsg 직진 · Ltsg 좌회전 · Utsg 유턴 · Pdsg 보행 · Bssg 버스 · Bcsg 자전거

필드명 = <방향><이동류><접미사>
    wtStsgSttsNm = 서쪽 진입 직진신호 점등상태명
    wtUtsgRmndCs = 서쪽 진입 유턴신호 잔여시간
```

그래서 우리 `signal_id` 는 **"교차로ID:방향"** 이다. 예: `"1057:wt"`
`config_zones.json` 의 라인마다 이 값을 넣는다.

### 점등상태는 SAE J2735 규격을 그대로 쓴다

| 응답 값 | 뜻 | 우리 상태 |
|---|---|---|
| `stop-And-Remain` | 정지 유지 | 적색 |
| `protected-Movement-Allowed` | 보호 이동 (화살표 등) | 녹색 |
| `permissive-Movement-Allowed` | 비보호 이동 | 녹색 |
| `protected-Clearance` / `permissive-Clearance` | 정리 | 황색 |
| `caution-Conflicting-Traffic` | 황색 점멸 | 황색 |
| `stop-Then-Proceed` | 적색 점멸 | 적색 |
| `pre-Movement` | 적+황 (곧 녹색) | 적색 |
| `dark` / `unavailable` / `""` | 정보 없음 | **판정 보류** |

빈 문자열이 아주 흔하다. 그 방향에 그 이동류가 없거나 자료가 안 올라온 것이다.

### 잔여시간 단위 — 확인 필요

받은 값이 `808 / 468 / 327 / 257 / 138 / 78` 이다.
초로 보면 808초(13분)라 신호 주기로 말이 안 된다. **0.1초 단위**로 보면
80.8 / 46.8 / 32.7 / 25.7 / 13.8 / 7.8초로 실제 주기와 맞는다.
원본이 SAE J2735(1/10초)라 그대로 실어 보내는 것으로 보인다.

`REMAIN_UNIT_SEC = 0.1` 로 두었지만 **스톱워치로 한 번 검증할 것.**

```bash
python signal_probe.py --watch 1057 --seconds 120
```

잔여시간이 1초에 1씩 줄면 맞다.

### 인증키는 `.env` 로

```bash
copy .env.example .env      # Windows
```

`.env` 는 `.gitignore` 에 있어 깃허브에 안 올라간다. 팀원에게는 `.env.example`
만 공유한다. 로그에는 `CFwn…D%3D` 형태로만 남는다.

> **Decoding 키를 쓰면 인증이 깨진다.** `%2B`, `%3D%3D` 가 있는 Encoding 쪽을
> 그대로 넣고, 코드에서 다시 인코딩하지 않는다 (`%2B` → `%252B` 면 401).
> 회귀 테스트로 고정해 뒀다.

### 내 교차로가 목록에 있는지부터 확인해야 한다

전국 4,239곳 중 실시간 신호가 오는 곳은 1,342곳(32%)뿐이다. 촬영 지점이
여기 없으면 **실시간 API를 쓸 수 없고**, `--signal` 타임라인 방식을 써야 한다.

실측 예 — **이수역(7호선) 사거리**

```
교차로 ID   1552   이수역   37.4853994, 126.9821635   ← 목록에는 있음
실시간 신호                                            ← 안 옴
가장 가까운 실시간 교차로   3.9km 떨어진 '녹지대'(3226)
```

즉 이수역 영상은 **타임라인 방식(5장)으로 판정해야 한다.**

### 내 교차로 찾기

```bash
python signal_probe.py                          # 연결 확인 + 살아있는 교차로
python signal_probe.py --near 37.5665,126.978   # 촬영 지점 좌표로 찾기
python signal_probe.py --find 사거리             # 이름으로 찾기
python signal_probe.py --watch 1057             # 8방향 신호 실시간 관찰
```

찾은 값을 `config_zones.json` 의 `signal_id` 에 넣는다.

```json
{ "line_id": "center_1", "line_type": "center",
  "uturn_allowed": true, "signal_id": "1057:wt" }
```

### 실행

```bash
python run_uturn.py --cam CAM-TEST --signal-api ...
```

### 설계에서 중요한 두 가지

**① API는 "지금"만 아는데 판정은 "그때"를 묻는다**

`phase_at(signal_id, ts)` 의 `ts` 는 차가 선을 넘던 **과거** 시각이다. 그래서
백그라운드로 폴링하며 **변화 이력을 쌓아 두고** 그 시각을 되찾는다.

**② 잔여시간으로 전환 시각을 역산한다**

1초 폴링이면 전환 시각에 최대 1초 오차가 난다. 적색 판정 유예가 0.3초라
그냥 넘길 수 없다.

```
직전 관측이 (10.0초, 녹색, 잔여 2.4초)  →  실제 전환은 12.4초
폴링이 13.0초에 적색을 봤어도 12.4초로 기록
```

### API가 죽으면 — 판정 보류

마지막 수신값이 5초보다 오래되면 `UNKNOWN` 을 돌려주고, 판정 쪽은 위반으로
만들지 않는다. **신호를 모르는 채로 사람에게 과태료를 물릴 수는 없다.**

### 주의: 녹화 영상 + 실시간 API 는 시각이 안 맞는다

어제 찍은 영상에 오늘의 신호를 붙이면 판정이 무의미하다. 녹화본은 `--signal`
타임라인, 실시간 CCTV는 `--signal-api`. `run_uturn.py` 가 경고를 띄운다.

---

## 6. 실행

```bash
python run_uturn.py --video 내영상.mp4 --cam CAM-TEST \
    --signal signal_timeline.json \
    --save output/result.mp4 --show
```

| 옵션 | 설명 |
|---|---|
| `--show` | 실시간 창으로 본다 (`q` 로 중단) |
| `--save PATH` | 판정 과정을 그린 영상 저장 |
| `--events PATH` | 이벤트 JSON (기본 `output/uturn_events.json`) |
| `--stride 2` | 느리면 2~3으로 올린다 (2프레임마다 1장 처리) |
| `--conf 0.35` | 차량 검출 신뢰도 하한 |
| `--lpr` | 번호판 인식도 함께 (많이 느려진다) |

화면 색 의미

- 초록 박스: 일반 차량
- 빨강 박스: 중앙선을 넘어 **지켜보는 중**
- 빨강 박스 + 하단 배너: **위반 확정**
- 노란 선: 중앙선 (진한 노랑 = 유턴 허용)
- 우상단 원: 현재 신호

출력 예시

```
중앙선 1개: center_1(금지)
신호 타임라인: signal_timeline.json
  ★ 불법 유턴  t= 18.40s  track=#7  wrong_signal
     좌회전 신호가 아닌 상태(green)에서 유턴 — 중앙선 통과 후 진행 방향 반전 ...
불법 유턴 1건
```

---

## 7. 안 잡힐 때 조정

| 증상 | 볼 곳 | 조치 |
|---|---|---|
| 유턴을 했는데 안 잡힘 | 중앙선 위치 | `draw_roi.py` 로 다시 그린다. 차량 **바닥 중심**이 지나는 자리여야 한다 |
| 〃 | `uturn_angle_deg` (기본 150) | 완만한 유턴이면 130~140으로 낮춘다 |
| 〃 | `uturn_confirm_sec` (기본 4.0) | 유턴이 느리면 6.0으로 올린다 |
| 〃 | `uturn_lookback_px` (기본 120) | 진입 직선 구간이 짧으면 80으로 줄인다 |
| 〃 | `--show` 로 track 번호 | 선회 중 `#번호`가 바뀌면 추적이 끊긴 것 (아래 9장) |
| 좌회전을 유턴으로 오탐 | `uturn_angle_deg` | 160으로 올린다 |
| 차량이 아예 안 잡힘 | `--conf` | 0.25로 낮춘다. `--imgsz 1280` 도 시도 |
| 너무 느림 | `--stride` | 2~3. `--imgsz 640` |

전부 `config.yaml` 의 `violation:` 항목에서 바꾼다.

---

## 8. 이번에 바뀐 코드 (팀 합칠 때 참고)

### 새로 만든 파일

| 파일 | 역할 |
|---|---|
| `app/violation/track_log.py` | **김준호 e_tracking 결과 → 우리 규격 어댑터** (팀 통합용) |
| `app/violation/vehicle_track.py` | **임시** 차량 검출·추적기 (YOLO + ByteTrack, 실패 시 IoU 추적) |
| `app/violation/synthetic.py` | 합성 검증 장면 (영상·YOLO 없이 로직 점검) |
| `draw_roi.py` | 마우스로 중앙선/정지선 찍어 `config_zones.json` 저장 |
| `run_uturn.py` | 영상 → 판정 → 오버레이 영상 + 이벤트 JSON |
| `signal_timeline.example.json` | 신호 타임라인 예시 |
| `app/violation/signal_klid.py` | **KLID 실시간 신호 API 연동** `KlidSignal` (8방향×6이동류) |
| `app/violation/signal_api.py` | 범용 신호 API 어댑터 (다른 기관 API용 예비) |
| `signal_probe.py` | 교차로 찾기·신호 관찰 도구 |
| `.env.example` | 필요한 비밀키 목록 (커밋용 템플릿) |
| `tests/test_signal_klid.py` | **실제 응답 원문**으로 검증하는 테스트 43개 |
| `tests/test_track_log.py` | e_tracking 어댑터 테스트 13개 |
| `tests/test_signal_api.py` | 범용 어댑터 테스트 27개 |

> `vehicle_track.py` 는 **임시 대역**이다. 김준호 `e_tracking` 이 완료되어
> `track_log.py` 어댑터로 대체 가능해졌다. `run_uturn.py --track-log` 를 쓰면
> 팀 추적 결과 위에서 판정이 돈다. 두 소스 모두 공통 `Detection` 규격을
> 내보내므로 `ViolationEngine` 쪽은 한 줄도 안 고쳤다.

### 고친 파일

| 파일 | 무엇을 |
|---|---|
| `app/violation/signal_state.py` | `LEFT_ARROW`·`GREEN_LEFT` 페이즈, `PedPhase`, `UTURN_ALLOWED_PHASES`, `TimelineSignal`, `ManualSignal.update_ped()`, **`Movement` 이동류 enum + `movement_at()`** 추가 |
| `app/violation/roi.py` | `VirtualLine` 에 `line_type`·`uturn_allowed`·`signal_id` 추가, `CameraZones.center_lines()` 추가 |
| `app/violation/detectors.py` | `UTurnDetector` 를 **중앙선 통과 트리거 방식으로 전면 교체**. `Verdict.subtype` 추가, `_judge()` 로 3종 분류, `_approach_heading()` 추가, **유턴 신호를 직접 보고 판정** |
| `app/violation/engine.py` | `UTurnDetector(self.signal)` 로 신호 주입, `_emit()` 에 `subtype` 전달 |
| `app/core/schemas.py` | `ViolationEvent.subtype` 필드 + `to_payload()` 반영 |
| `app/core/gateway.py` | 게이트웨이 규격 `meta.violationSubtype` 으로 전달 (최상위 필드는 건드리지 않음) |
| `app/violation/trajectory.py` | `TrackPoint.car_h` (화면상 차량 크기 = 거리의 기준자), `Track.car_size()` 추가 |
| `app/core/config.py` | `.env` 로더(`load_dotenv`), `secret()`, `mask()` 추가 — 의존성 없이 표준 라이브러리만 |
| `its_cctv.py` | ITS 키를 `.env` 에서도 읽도록 (`its_key.txt` 도 계속 동작) |
| `.gitignore` | `.env`, `.env.local` 추가 |
| `app/core/config.py` · `config.yaml` | `uturn_confirm_sec`, `uturn_heading_window`, `uturn_lookback_px`, `uturn_lookback_cars`, `uturn_min_move_px`, `uturn_min_path_px`, `uturn_use_ped_signal` 추가 · `track_history` 120 → 300 |
| `config_zones.json` | CAM-001 `center_A`(금지), CAM-002 `center_B`(허용)·`center_B2`(금지) 중앙선 추가 |
| `tests/test_violation.py` | `TestUTurn` 전면 재작성(11개) + `TestSyntheticScene` 추가 |

### 팀 규격에 미친 영향

`meta` 안에만 필드를 하나 늘렸다. 규격서 4장의 "임의로 새 최상위 필드를 추가하지
말 것"을 지켰으므로 **b_gateway 쪽은 수정 없이 그대로 받는다.**

```json
{
  "eventType": "UTURN_VIOLATION",
  "meta": { "violationSubtype": "no_sign", "detail": "유턴 금지 구간에서 유턴 — ..." }
}
```

---

## 9. 실제 영상에 적용될까 — 위험 지점

판정 로직은 **좌표만 보고 돌아간다.** 좌표가 합성 배우에서 오든 YOLO에서 오든
똑같이 동작하므로 그 부분은 실영상에서도 그대로 간다. 문제는 그 **위쪽**이다.

### 실제 영상을 가정하고 코드를 다시 본 결과 잡아낸 버그 2개

**① 궤적 버퍼가 한 바퀴 돌면 판정이 깨진다** (실영상이면 거의 매번 터짐)

통과 시점을 궤적 배열의 **인덱스**로 들고 있었다. 궤적 버퍼는 오래된 점을
밀어내는 링버퍼라, 버퍼가 한 바퀴 돌면 그 인덱스가 엉뚱한 구간을 가리킨다.
게다가 `track_history` 기본값 120은 30fps에서 **4초**뿐이라 유턴 확정 창(4초)과
정확히 겹쳤다. 합성 장면은 짧아서 안 걸렸을 뿐이다.

→ 통과 이후 구간을 **시각**으로 자르도록 고치고, `track_history` 를 300(10초)으로 올림.

**② 신호 대기하다 유턴하면 못 잡는다** (실제 교차로에서 가장 흔한 형태)

진입 방향을 "통과 2초 전" 위치에서 쟀는데, 유턴하려는 차는 보통 신호를 기다리며
**정차**한다. 2초 전은 멈춰 있던 구간이라 방향이 엉뚱하게 나온다.

→ 시간이 아니라 **이동 거리** 기준으로 되돌아가도록 변경. 멈춘 시간은 이동 거리가
0이라 자동으로 건너뛰어진다. 되돌아갈 거리는 화면상 차량 크기(`car_h`)에
비례시켰으므로 4K든 720p든, 멀든 가깝든 같게 동작한다.
회귀 테스트 `test_uturn_after_waiting_at_the_light` 로 고정.

### 아직 확인 못 한 것 — 위험 큰 순서

| 위험 | 왜 | 확인 방법 |
|---|---|---|
| **track ID 끊김** | 유턴은 차가 가장 느리고 가장 많이 가려지는 순간이다. ByteTrack이 ID를 놓치고 새로 부여하면 후보(`_pending`)를 잃어 **놓친다**. 지금 가장 큰 위험 | `--show` 로 돌리며 유턴 차량의 `#번호`가 선회 내내 안 바뀌는지 눈으로 확인 |
| **카메라 각도** | 낮은 위치에서 비스듬히 찍으면 중앙선이 화면에서 직선이 아니고, 차량 접지점도 흔들린다 | 가능한 한 높고 정면에 가깝게 촬영 |
| **YOLO 차량 검출률** | 기본 모델은 COCO라 한국 도로 실측치가 없다. LPR 때 합성 98% → 실데이터 3.3% 였던 전례가 있다 | 영상 돌려보고 초록 박스가 차마다 붙는지 확인 |
| **처리 속도** | CPU + 4K면 yolo11n 도 3~8fps. 30초 영상에 수 분 | 오프라인이면 무관. `--stride 2`, `--imgsz 640` |



**된다**

- 중앙선 통과 → 방향 반전 → 유턴 확정까지의 판정 로직 (합성 장면 270개 테스트 통과)
- 표지·신호 조건에 따른 위반 3종 분류
- 좌회전·직진 차량 오탐 없음 (반례 테스트 포함)
- 신호 대기로 정차했다가 하는 유턴도 잡음 (회귀 테스트 포함)
- 실제 영상의 신호 타임라인을 넣으면 그 신호 기준으로 진짜 판정
- KLID 실시간 신호 API 연동 — 실제 응답으로 파싱·판정까지 테스트 완료
- 보행 신호는 API 실제 값을 쓴다 (연계 가정 아님)

**아직 아니다**

- 잔여시간 단위(0.1초 가정) — 스톱워치로 검증 안 했다
- **유턴 신호는 전국 1곳에만 온다** — 규격엔 있지만 실제로는 거의 비어 있다.
  코드 경로는 살아 있으나 주력은 좌회전·보행 신호 추론이다
- **이수역은 실시간 신호가 안 온다** → 타임라인 방식으로 판정해야 한다
- 보행 신호 — **연계 가정이 아니라 실제 API 값**을 쓴다 (해당 교차로에 자료가 있을 때)
- 차량 검출·추적 — 임시 대역이다. 정식은 김관용·김준호 모듈
- 실제 도로 영상 정확도 — 아직 촬영 영상으로 측정한 수치가 없다.
  촬영 후 이 문서에 실측치를 적어야 한다
