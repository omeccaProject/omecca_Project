# Real Journey 폴리라인/차량 마커 로직 (2026-08-24 확정본)

이 문서는 GIS 지도에서 "이상감지 차량이 실시간으로 움직이고, 폴리라인이 도로 위에
정확하게 + 실시간으로 그려지는" 기능의 **최종 확정 설계**를 기록한다.

나중에 이 부분이 다시 이상하게 동작하면(예: 순간이동, 직선으로 그려짐, 파이썬을
끈 뒤에도 계속 재생됨, 지그재그/크리스크로스 폴리라인 등) 아래 설계대로 되돌려라.
사용자가 명시적으로 "이게 내가 원하는 로직이다"라고 확정한 버전이다.

## 요구사항 (사용자 확정)

1. 폴리라인은 실제 도로를 따라 **정확하게** 그려져야 한다 (직선 아님).
2. 폴리라인은 보라매역 → 장승배기 → 상도 → 한강대교남단 **순서대로만** 그려지고,
   중간 카메라를 건너뛰지 않는다.
3. 이상감지 차량 마커는 지도 위에서 **실시간으로 움직여야** 한다 (순간이동 아님).
4. 폴리라인도 차량이 움직이는 동안 **실시간으로 자라나야** 한다 (한 번에 다 그려지고
   끝나는 게 아니라, 차량을 따라 점점 그려지는 것처럼 보여야 함).
5. 파이썬(`test_suspicious_driving.py`)을 끄면, 화면도 **그 즉시** 멈춰야 한다.
   큐에 쌓인 오래된 애니메이션이 파이썬 종료 후에도 한참 재생되면 안 된다.
6. 같은 구간을 여러 번 다시 그려도(직선 → 정확한 도로경로로 교체) 예전에 그려진
   좌표가 화면에 안 지워지고 남아있으면 안 된다 (append-only 금지).

## Python 쪽 (`e_tracking/SmartCCTV/test_suspicious_driving.py`)

- `CAMERA_ORDER = ["L010111","L010271","L010128","L010481"]` — 순서 고정.
- `get_multi_point_road_route(cam_ids, cache)` — OSRM에 **한 번**의 다중 경유지
  요청(`;`로 구분된 여러 좌표)을 보내 전체 구간을 하나의 연속된 도로 경로로 받는다.
  구간별로 쪼개서 여러 번 호출하지 않는다. 실패 시 직선으로 폴백.
- `_advance_journey_to(journey, target_cam_id)` — 다음 카메라로 넘어갈 때마다
  **정확히 2번**만 `send_journey_update()`를 호출한다:
  1. 즉시: 지금까지의 카메라들을 잇는 **직선** 좌표 (사용자가 바로 반응을 볼 수 있게)
  2. 백그라운드 스레드에서 `get_multi_point_road_route()`로 계산한 **정확한 도로
     경로**로 통째로 교체
  - 이미 진행 중인 advance가 있으면(`_journey_pending`) 무시하고 하나만 실행한다.
  - `update_journey_for_frame()`의 "다음 CCTV 탐색"은 `CAMERA_ORDER`상 **바로 다음
    카메라만** 확인한다 (건너뛰기 금지).

이 부분은 사용자가 "지금 도로위 폴리라인이 맞게 그려지는건 좋다"고 확정했으므로
**변경하지 않는다**. 문제가 생기면 JS 쪽만 의심할 것.

## JavaScript 쪽 (`e_tracking/SmartCCTV/web/map.js`)

### `RealVehicleMarker.animateAlong(points, label, onFrame)`

- payload가 새로 올 때마다 호출된다. **큐에 쌓지 않는다.**
- 호출되자마자 `_cancelAnimation()`으로 진행 중이던 애니메이션을 무조건 취소한다.
- 마커의 "현재 실제 화면 위치"에서 새 `points` 배열 중 가장 가까운 지점(`startIdx`)을
  찾아, 그 지점부터 이어서 애니메이션한다 (뒤로 순간이동하는 부자연스러운 점프 방지).
- `requestAnimationFrame` 기반으로 `SPEED_METERS_PER_SEC = 300`속도로 구간을
  선형보간하며 부드럽게 이동한다.
- **매 프레임마다** `onFrame(지나온 좌표들 + 지금 보간 중인 좌표)`를 호출한다.

### 호출부 (`RealVehicleJourneyListener`의 onUpdate 콜백, map.js 내부)

```js
const label = payload.currentCamName || payload.currentCamId;
realVehicleMarker.animateAlong(points, label, (framePoints) => {
  routeManager.setRealJourneyPoints(framePoints);
});
```

- `onFrame`에서 `routeManager.setRealJourneyPoints(framePoints)`를
  호출해서 **매 프레임 폴리라인을 통째로 다시 그린다** (append하지 않음).
  → 이게 핵심이다: "실시간으로 자라나는 것처럼 보이지만, 실제로는 매 프레임
  authoritative한 좌표 기준으로 전체 재그리기"이기 때문에, append-only 방식의
  "오래된 직선이 안 지워지는" 버그가 재발하지 않으면서도 동시에 실시간으로
  그려지는 것처럼 보인다.

### 하지 말아야 할 것 (예전에 있었던 버그, 재도입 금지)

1. **큐 기반 애니메이션** (`_pathQueue`, `_consumeQueue`, 예전 `followPath()`) —
   payload가 여러 번 빠르게 오면(직선→도로경로 교체) 큐가 쌓여서, 파이썬을 끈
   뒤에도 한참 재생되며 지그재그로 겹쳐 그려짐. → **삭제됨, 다시 추가하지 말 것.**
2. **`routeManager.appendRealJourneyPoint()`로만 그리기** — 이 함수는 이미 그려진
   좌표를 절대 지우거나 다시 그리지 않는 append-only 함수라서, 나중에 더 정확한
   좌표가 와도 예전 직선이 화면에 남아있게 됨. 매 프레임/매 payload마다
   `setRealJourneyPoints()`(전체 재그리기)를 써야 한다.
3. **즉시 스냅만 하고 애니메이션 없는 버전** (`setPosition()`만 호출, `animateAlong()`
   안 씀) — 정확하긴 하지만 차량이 순간이동하는 것처럼 보여서 사용자가 명시적으로
   반려하고 애니메이션을 다시 요청함.

## 요약: 올바른 최종 상태 체크리스트

- [ ] Python: `_advance_journey_to()`가 advance당 정확히 2번만 payload를 보낸다
      (직선 1번 + 정확한 도로경로 1번).
- [ ] Python: `CAMERA_ORDER` 순서를 건너뛰지 않는다.
- [ ] JS: `RealVehicleMarker`에 `animateAlong()`이 있고, `followPath`/`_pathQueue`는
      없다.
- [ ] JS: `animateAlong()` 안에서 새 payload가 오면 `_cancelAnimation()`으로 기존
      애니메이션을 취소하고, 큐에 쌓지 않는다.
- [ ] JS: `onUpdate` 콜백이 `realVehicleMarker.animateAlong(points, label, onFrame)`을
      호출하고, `onFrame` 안에서 `routeManager.setRealJourneyPoints(framePoints)`를
      호출한다 (append 아님, 매번 전체 재그리기).
- [ ] 화면: 차량이 부드럽게 움직이고, 폴리라인이 실시간으로 자라나고, 도로에
      정확하게 맞고, 파이썬을 끄면 바로 멈춘다.
