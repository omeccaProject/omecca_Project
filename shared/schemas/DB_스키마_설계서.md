# 오메카3 프로젝트 — DB 스키마 설계서 (MySQL)

작성: 장성혁 · 최종 확인: 2026-08-06 (b_gateway 코드 기준 검증 완료)

## 1. 개요

`이벤트_스키마_규격서.md`를 기반으로 실제 MySQL 테이블 구조를 설계했습니다.
DB명 `omecca`에 4개 테이블(`target`, `roi`, `event`, `report`)을 생성합니다.
실행 DDL 원본은 `b_gateway/src/main/resources/schema.sql`에 있습니다.

## 2. 테이블 관계도

```
target (관심 대상)         roi (감지 구역/라인)
    |  1                        |  1
    |                           |
    |  N                        |  N
    +---------> event <---------+
                  |  1
                  |
                  |  1
                report (증거 리포트 PDF)

event.target_id  -> target.id   (ON DELETE SET NULL)
event.roi_id     -> roi.id      (ON DELETE SET NULL)
report.event_id  -> event.id    (ON DELETE CASCADE, UNIQUE)
```

## 3. 테이블별 상세 스펙

### 3.1 target — 관심 대상

| 컬럼명 | 타입 | NULL | 설명 |
|---|---|---|---|
| id | BIGINT UNSIGNED PK | N | 자동증가 고유번호 |
| target_type | ENUM('PERSON','VEHICLE') | N | 대상 종류 |
| plate_number | VARCHAR(20) | Y | 차량인 경우 번호판 |
| person_ref_id | VARCHAR(50) | Y | 얼굴 임베딩/수배자 DB 참조 ID |
| label | VARCHAR(100) | Y | 관제요원이 붙인 메모/별칭 |
| registered_by | VARCHAR(50) | N | 등록한 관제요원 계정 |
| status | ENUM('ACTIVE','CLOSED') | N | 추적 상태 (기본값 ACTIVE) |
| created_at | DATETIME(3) | N | 등록 시각 |
| closed_at | DATETIME(3) | Y | 추적 종료 시각 |

### 3.2 roi — 감지 구역 / 가상 라인

| 컬럼명 | 타입 | NULL | 설명 |
|---|---|---|---|
| id | BIGINT UNSIGNED PK | N | 자동증가 고유번호 |
| cam_id | VARCHAR(50) | N | 해당 ROI가 속한 CCTV |
| roi_type | ENUM('ZONE','LINE') | N | ZONE(정지구역) / LINE(가상라인) |
| name | VARCHAR(100) | N | 예: '1번 차로 정지구역' |
| geometry_json | JSON | N | 좌표 폴리곤/라인 정의 |
| created_at | DATETIME(3) | N | 등록 시각 |

### 3.3 event — 전체 위험 이벤트 (핵심 테이블)

| 컬럼명 | 타입 | NULL | 설명 |
|---|---|---|---|
| id | BIGINT UNSIGNED PK | N | 자동증가 고유번호 |
| cam_id | VARCHAR(50) | N | 탐지된 CCTV |
| track_id | VARCHAR(50) | Y | 추적 ID |
| event_type | ENUM(7종) | N | 이벤트_스키마_규격서.md 3.2 참고 |
| object_class | ENUM('PERSON','VEHICLE','OBJECT') | N | |
| bbox_x / bbox_y / bbox_w / bbox_h | INT | Y | 바운딩 박스 (4개 컬럼) |
| confidence | DECIMAL(4,3) | Y | 탐지 신뢰도 |
| occurred_at | DATETIME(3) | N | 이벤트 실제 발생 시각 |
| received_at | DATETIME(3) | N | 서버 수신 시각 |
| lat / lng | DECIMAL(10,7) | Y | 위치 좌표 |
| is_registered_target | TINYINT(1) | N | 관심 대상 관련 여부 (기본값 0) |
| target_id | BIGINT UNSIGNED FK | Y | target.id 참조 |
| roi_id | BIGINT UNSIGNED FK | Y | roi.id 참조 |
| meta | JSON | Y | 이벤트 유형별 가변 필드 |
| frame_ref_before / frame_ref_after | VARCHAR(255) | Y | 전/후 캡쳐 이미지 경로 |
| created_at | DATETIME(3) | N | 레코드 생성 시각 |

### 3.4 report — 증거 리포트 (PDF)

| 컬럼명 | 타입 | NULL | 설명 |
|---|---|---|---|
| id | BIGINT UNSIGNED PK | N | 자동증가 고유번호 |
| event_id | BIGINT UNSIGNED FK/UNIQUE | N | event.id 참조, 1:1 관계 |
| pdf_path | VARCHAR(255) | N | PDF 저장 경로 |
| status | ENUM('PENDING','GENERATED','FAILED') | N | 생성 상태 |
| generated_at | DATETIME(3) | Y | PDF 생성 완료 시각 |
| created_at | DATETIME(3) | N | 레코드 생성 시각 |

## 4. 설계 시 고려사항

- **좌표 이중 저장**: 대시보드 조회 성능을 위해 `event`에도 `lat`/`lng`를 캐시처럼 저장.
  정밀 공간 쿼리(경로 시각화 등)는 별도 PostGIS 사용.
- **meta는 JSON 컬럼**: 이벤트 유형별 부가 정보가 다르므로, 새 기능이 추가돼도 테이블 구조 변경 없이 확장 가능.
- **report는 UNIQUE(event_id)**: 이벤트 1건당 리포트 1건만 존재. `b_report`가 PDF 생성을 마친 뒤
  등록하는 흐름이라 기본 상태값은 `GENERATED`.
- **target/roi는 NULL 허용 FK**: 모든 이벤트가 관심 대상이나 ROI와 연결되는 건 아님
  (예: 수배자 얼굴 인식은 target 없이도 발생).

## 5. 실행

```bash
mysql -u root -p < b_gateway/src/main/resources/schema.sql
```

## 6. 연동 상태

`b_gateway`의 Entity(`Target`, `Roi`, `Event`, `Report`)가 이 스키마와 1:1로 매핑되어 있으며,
`application.yml`의 `ddl-auto: validate` 설정으로 Entity와 실제 테이블 구조가 다르면
서버 시작이 차단됩니다 (설계와 코드가 어긋나는 걸 조기에 발견하기 위한 안전장치).
