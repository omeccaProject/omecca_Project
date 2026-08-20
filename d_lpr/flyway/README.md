# Flyway 전환 — 적용 안내

각자 컴퓨터에서 SQL 을 손으로 돌리는 걸 없앤다. **앱을 켜면 DB 가 알아서 맞춰진다.**

이 폴더는 **준비물 보관소**다. 실제 적용은 `b_gateway` 쪽에 파일을 옮겨야 하므로,
그 폴더 담당자와 합의한 뒤에 진행한다.

---

## 지금 뭐가 문제인가

```yaml
# b_gateway/src/main/resources/application.yml
ddl-auto: validate
```

`validate` 는 **"테이블을 만들지 마라, 있는지 검사만 해라"** 는 뜻이다. 그래서 각자
손으로 만들어야 하고, 하나라도 안 맞으면 앱이 시작조차 안 된다.

게다가 돌려야 할 SQL 이 흩어져 있고 **순서가 어디에도 안 적혀 있다.**

```
b_gateway/src/main/resources/schema.sql                        ← 최신 완성본
                             migration_add_camera_table.sql    ┐ 예전 DB 를 가진
                             migration_add_camera_catalog.sql  │ 사람이 따라잡기
                             migration_add_camera_batch2.sql   │ 위한 보정 스크립트
                             migration_add_target_vehicle_fields.sql ┘
d_lpr/sql/schema.sql                                           ← LPR 테이블
d_lpr/sql/seed.sql
```

`migration_*.sql` 은 `schema.sql` 로 새로 만든 DB 에는 **필요 없다** (파일 주석에도
그렇게 적혀 있다). 그런데 그걸 모르고 다 돌리면 `ALTER TABLE ... ADD COLUMN color`
가 이미 있는 컬럼을 또 추가하려다 실패한다. "실행시 문제" 의 정체가 이것이다.

---

## Flyway 가 하는 일

버전이 붙은 SQL 을 **순서대로 한 번씩만** 적용하고, 어디까지 했는지 DB 에 기록한다
(`flyway_schema_history` 테이블이 자동 생성된다).

```
새 팀원      앱 실행 → V1, V2, V3 전부 적용
이미 V2까지  앱 실행 → V3 만 적용
다 끝난 사람 앱 실행 → 아무 일도 안 일어남
```

"내가 이거 돌렸던가?" 를 고민할 필요가 없어진다.

---

## 준비된 파일

| 파일 | 내용 |
|---|---|
| `V1__baseline.sql` | camera, camera_catalog, target, roi, event, report, user (b_gateway) |
| `V2__lpr_tables.sql` | vehicle, plate_read_log (d_lpr) |
| `V3__lpr_seed.sql` | 시연용 차량 12대 |

원본에서 **`CREATE DATABASE` 와 `USE omecca;` 를 뺐다.** Flyway 는 이미 그 DB 에
접속한 상태로 돌기 때문에, 남겨 두면 마이그레이션이 깨진다.

`migration_*.sql` 4개는 V1 에 이미 반영돼 있으므로 **더 이상 필요 없다.**
지우기 아까우면 `_archive/` 로 옮겨 둔다.

셋 다 sqlglot 으로 MySQL 문법 검증을 마쳤다 (17 / 2 / 1 구문).

---

## 적용 순서

### 1. 파일 옮기기

```powershell
cd C:\Users\박지원\Desktop\d\omecca_Project
mkdir b_gateway\src\main\resources\db\migration
copy ..\omeca-lpr\flyway\V*.sql b_gateway\src\main\resources\db\migration\
```

### 2. `pom.xml` 에 의존성 두 개

Spring Boot 3.3.4 가 버전을 관리하므로 `<version>` 은 적지 않는다.

```xml
<dependency>
    <groupId>org.flywaydb</groupId>
    <artifactId>flyway-core</artifactId>
</dependency>
<dependency>
    <groupId>org.flywaydb</groupId>
    <artifactId>flyway-mysql</artifactId>
</dependency>
```

`flyway-mysql` 을 빠뜨리면 "Unsupported Database: MySQL" 로 실패한다. Flyway 10 부터
DB 별 지원이 따로 떨어져 나갔다.

### 3. `application.yml` 의 `spring:` 아래에 추가

```yaml
  flyway:
    enabled: true
    baseline-on-migrate: true   # 이미 테이블이 있는 DB 도 V1 을 건너뛰고 합류시킨다
    baseline-version: 0
    clean-disabled: true        # flyway clean 은 스키마의 모든 표를 지운다. 반드시 막는다
```

`ddl-auto: validate` 는 **그대로 둔다.** Flyway 가 먼저 만들고 Hibernate 가 검증하는
순서를 Spring Boot 가 보장한다. 정석 조합이다.

### 4. 확인

```powershell
cd b_gateway
.\mvnw spring-boot:run
```

로그에 이렇게 나오면 성공이다.

```
Flyway Community Edition ... by Redgate
Successfully applied 3 migrations to schema `omecca`
```

---

## 처음 도입할 때 딱 한 번 필요한 것

이미 DB 를 만들어 둔 사람은 `baseline-on-migrate: true` 덕분에 그대로 합류한다.
다만 **테이블 구조가 V1 과 다르면** 나중에 `validate` 에서 걸린다.

발표 전이라면 **한 번 밀고 새로 만드는 쪽이 확실하다.**

```sql
DROP DATABASE omecca;
CREATE DATABASE omecca DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

그다음 앱을 켜면 Flyway 가 V1~V3 를 전부 적용한다.

---

## 주의 — `flyway clean` 절대 쓰지 말 것

**스키마의 모든 테이블을 지운다.** `vehicle`, `plate_read_log` 도 같이 날아간다.
위 설정의 `clean-disabled: true` 가 이걸 막는다. 빼지 말 것.

---

## 앞으로 스키마를 바꿀 때

**기존 V 파일을 고치면 안 된다.** Flyway 는 적용된 파일의 체크섬을 기록해 두고,
바뀌면 다음 실행에서 "Migration checksum mismatch" 로 멈춘다.

새 파일을 만든다.

```
V4__add_something.sql
V5__fix_index.sql
```

번호는 겹치지 않게. 두 사람이 동시에 V4 를 만들면 충돌하니, 만들기 전에 한마디 하는
게 좋다.

---

## LPR 쪽은 어떻게 되나

Flyway 가 `vehicle` / `plate_read_log` 까지 만들어 주므로 **더 이상 따로 만들 필요가
없다.** `check_mysql.py` 는 이제 *만드는* 도구가 아니라 *확인하는* 도구로 쓴다.

```bash
python check_mysql.py            # --create 없이. 붙는지·한글 되는지 점검만
```
