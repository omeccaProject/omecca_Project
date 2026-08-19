# d_lpr 통합 시 주의사항

번호판 인식 / 차량 위반 감지 모듈(박지원)을 팀 코드에 붙일 때 읽는 문서.

아래 항목은 **취향이나 스타일 문제가 아니라, 이미 한 번씩 사고가 났던 자리**다.
대부분 "고쳐진 것처럼 보이는데 조용히 망가지는" 종류라 리뷰에서 잘 안 걸린다.

---

## 1. 커밋하면 안 되는 것

| 대상 | 이유 |
|---|---|
| `.env`, `its_key.txt` | 공공데이터포털·ITS 인증키. **개인 명의**로 발급된 것이고, git 히스토리는 나중에 지워도 과거 커밋에 남는다 |
| `plates/`, `plates_test/`, `plates_final/` | 실제 도로에서 찍은 차량 번호판 사진 150장. **개인정보** |
| 학습 중간 산출물 `*.pt` | epoch 마다 쏟아진다. `models/` 안의 완성 모델만 예외로 열어 뒀다 |

`.gitignore` 와 `sync_to_team.ps1` 두 곳에서 막고 있다. **한쪽만 고치지 말 것.**
`.gitignore` 는 커밋만 막고 복사는 못 막는다.

### git 명령 주의

```bash
git add d_lpr        # O
git add .            # X — 다른 팀원 파일까지 딸려간다
git push --force     # X — 남의 커밋이 사라진다. 거절당하면 pull 이 답이다
```

`c_person_risk/models/best.pt` 는 항상 `modified` 로 뜬다. **`git restore` 하지 말 것** —
6MB 모델이 날아간다.

---

## 2. 지우면 조용히 망가지는 것

리팩터링하다가 "이건 왜 이렇게 짰지?" 싶은 자리들. 전부 이유가 있다.

### 2-1. MySQL 실패 시 SQLite 폴백 (`repository.py::_connect`)

예외를 삼키고 넘어간다. **의도된 것이다.** 시연 중 DB가 죽어도 파이프라인이
멈추지 않게 하려는 설계다.

부작용으로 "정말 MySQL 을 쓰는지" 코드만 봐서는 알 수 없다. 확인은 이걸로 한다:

```bash
python check_mysql.py --user root --password ...
```

**폴백을 없애면** 시연 중 DB 문제가 곧 전체 정지가 된다.

### 2-2. 한글 경로 입출력 (`visualize.py`)

```python
imread_unicode(path)     # cv2.imread   대신
imwrite_unicode(path)    # cv2.imwrite  대신
```

`cv2.imwrite` 는 경로에 한글이 있으면 (`C:\Users\박지원\...`) **아무것도 쓰지 않고
False 만 돌려준다.** 예외가 안 나서 "다 저장했다"고 착각한다. 실제로 20,000장이
하나도 저장 안 됐는데 "실패 0장"으로 보고된 적이 있다.

### 2-3. 한글 라벨 그리기

```python
draw_label(...)      # PIL 로 그린다
cv2.putText(...)     # X — 한글이 ??? 로 깨진다
```

### 2-4. DB 대조는 `resolve()` 한 곳에서만

`match()`(경보)와 `status_of()`(위반 기록)가 각자 DB를 뒤지던 시절이 있었다.
`status_of` 쪽에만 유사 매칭이 빠져 있어서, OCR 이 한 글자를 틀리면

```
경보      15무4755 → 유사 매칭으로 DB 17무4755 찾음 → 등록
위반 기록 15무4755 → 정확 매칭만 → 미등록
```

같은 차가 갈려 기록됐다. 관제 화면과 대시보드가 서로 다른 말을 한다.
지금은 둘 다 `resolve()` 를 탄다. **대조 논리를 다시 복제하지 말 것.**

`tests/test_match_consistency.py` 가 이걸 지킨다.

### 2-5. EasyOCR 언어 목록

`Reader(lang_list=...)` 가 `plate.yaml` 의 `lang_list` 에 **포함되는지** 검사하고,
하나라도 벗어나면 전용 모델을 통째로 거부한다.

```
config 기본값   ['ko', 'en']
plate.yaml     ['ko']
→ 'en' 이 남아서 "Plate is only compatible with English" 로 실패
```

`custom_lang_list()` 가 yaml 을 따라가게 돼 있다. 하드코딩으로 되돌리지 말 것.

### 2-6. `_recover_hangul` 은 **교체**지 삽입이 아니다

숫자만 7~8자리로 읽혔을 때 한글 자리를 채우는데, 삽입하면 `1031385` → `10조31385`
로 9자가 되어 형식 검사에서 탈락한다.

---

## 3. 이미 해보고 실패한 것 — 반복하지 말 것

성능을 올리려다 오히려 떨어뜨린 시도들. 되돌려 놨다.

| 시도 | 결과 |
|---|---|
| 문자 분할(`segment.py`) 파라미터 재튜닝 | 분할 정확도 36% → 77% 로 올렸는데 **최종 정확도는 78% → 76% 하락** |
| `recognize()` 다중 엔진 앙상블 | 잘림 3건 → 9건, 정확도 94% → 68% |
| 상자 병합 규칙 과튜닝 | `plates/` 잘림 3→0 이었으나 새 사진에서 11건 발생 |

공통 교훈: **중간 지표가 올라도 최종 정확도는 떨어질 수 있다.** 반드시 끝까지
재고 비교한다.

---

## 4. 측정 규칙

### `plates_final/` 은 봉인돼 있다

이 폴더로 낸 **45.7%** 가 발표에 쓰는 유일한 정직한 수치다.
결과를 보고 코드를 고치면 그 순간 무효가 되고, 4차 폴더가 필요해진다.

개발 중 성능 확인은 이걸로 한다:

```bash
python bench_lpr.py --dir plates --dir plates_test --weights models/plate_det.pt
```

### 비교할 때 설정을 맞춘다

`--weights` 유무만으로도 수치가 바뀐다. 이전 값과 비교하려면 같은 옵션을 써야 한다.

---

## 5. 붙이는 지점 (바꾸면 대시보드가 깨진다)

### 이벤트 버스 (`app/core/bus.py`)

```python
TOPIC_PLATE     = "lpr.plate"          # 번호판 확정
TOPIC_ALERT     = "vehicle.alert"      # 고위험 차량 경보
TOPIC_VIOLATION = "violation.event"    # 신호위반 / 불법유턴
```

```python
from app.core.bus import bus, TOPIC_VIOLATION

@bus.subscribe
def on_event(topic, payload):
    ...
```

### REST API (`app/api/server.py`)

```
GET  /health
GET  /api/violations           /api/violations/{event_id}
GET  /api/stats                /api/stats/summary  /by-type  /by-hour
GET  /api/vehicles             /api/vehicles/{plate_no}
GET  /api/zones                /api/recent-alerts
WS   /ws
```

토픽 이름과 엔드포인트 경로는 **계약**이다. 바꾸려면 대시보드 담당과 합의한다.

---

## 6. 합친 뒤 확인

```bash
python -m pytest tests/ -q          # 393개 전부 통과해야 한다
python run_demo.py                  # 설치 없이 6개 시나리오가 돈다
python install_model.py --check     # 전용 모델이 잡히는지
python check_mysql.py               # MySQL 을 쓸 때만
```

테스트가 깨지면 위 항목 중 하나를 건드린 것이다. 어떤 테스트가 깨졌는지 보면
어디를 되돌려야 하는지 바로 나온다.

---

## 7. 알아 둘 성능 수치

| 측정 | 값 |
|---|---|
| AI Hub 검증셋 5,000장 | 90.58% |
| 자체 촬영 35대 (개발 미사용) | **45.7%** |
| └ 지역명 2줄 판 13대 | 76.9% |
| 신뢰도 0.8 이상만 채택 시 정밀도 | 95.5% |

**격차의 원인은 알고리즘이 아니라 촬영 조건이다.** 같은 모델이 근접·주간 사진에서
98%, 원거리·야간에서 42% 를 낸다. 실제 단속 카메라가 적외선 조명·고속 셔터·고정
설치로 이 문제를 광학 단계에서 푸는 이유다.

그래서 인식률이 낮아 보여도 **모델 교체로는 잘 안 올라간다.** 시간을 쓴다면
영상 다중 프레임 투표(이미 `LPRPipeline.TrackVote` 에 구현됨) 쪽이 효율이 좋다.
