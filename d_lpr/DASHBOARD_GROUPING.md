# 대시보드 "이상운전" 묶기 — b_dashboard 담당자에게

박지원 (⑦ 신호위반·불법유턴) → 장성혁 / 대시보드 담당

## 요청

관제 화면에서 **불법 유턴과 신호 위반을 "이상운전" 한 묶음으로** 보여 주고 싶습니다.
이를 위해 `meta.riskCategory` 를 추가했습니다. **eventType 은 그대로입니다.**

## 붙는 값

```json
{
  "eventType": "UTURN_VIOLATION",
  "meta": {
    "riskCategory": "abnormal_driving",
    "riskCategoryLabel": "이상운전",
    "violationSubtype": "no_sign"
  }
}
```

| eventType | riskCategory | 라벨 |
|---|---|---|
| `UTURN_VIOLATION` | `abnormal_driving` | 이상운전 |
| `SIGNAL_VIOLATION` | `abnormal_driving` | 이상운전 |
| `UNREGISTERED_VEHICLE` | `vehicle_alert` | 차량 경보 |

`DUI_PATTERN`(⑥ 음주운전 패턴)도 `abnormal_driving` 으로 보내 주시면 셋이 한 묶음이 됩니다.
(그건 ⑥ 담당자 쪽 코드라 제가 안 건드렸습니다.)

## 대시보드에서 쓰는 법

```js
const group = e.meta?.riskCategory ?? "other";
// group === "abnormal_driving" 인 것들을 "이상운전" 탭/차트에 모은다
```

`riskCategory` 가 없는 옛 이벤트는 `other` 로 떨어지므로 기존 화면은 안 깨집니다.

## 왜 eventType 을 안 바꿨나

불법 유턴을 `DUI_PATTERN` 으로 보내는 방법도 있었지만 안 했습니다.

1. **틀린 근거가 전달됩니다.** `DUI_PATTERN` 은 음주운전 의심입니다. 유턴은 음주와
   무관한데 관제 요원이 "음주 의심"으로 받게 됩니다.
2. **통계가 부풀려집니다.** 같은 사건이 `UTURN_VIOLATION` + `DUI_PATTERN` 두 건으로
   나가면 b_report 집계가 2배가 됩니다.
3. **담당 지표가 오염됩니다.** ⑥ 음주운전 패턴 정확도에 제 유턴 이벤트가 섞입니다.

규격서 4장이 금지하는 건 "임의로 새 **최상위** 필드 추가"이고 `meta` 는 확장 가능하다고
명시돼 있어서(3.4), 이 방식이 규격 위반이 아닙니다.

## 검증

`tests/test_signal_api.py::TestRiskCategoryGrouping` 7개로 고정했습니다.

- eventType 이 규격 7종에서 안 벗어남
- 최상위 필드가 안 늘어남
- 이벤트가 한 건만 나감 (중복 없음)
- 버스 경유 경로도 같은 값
