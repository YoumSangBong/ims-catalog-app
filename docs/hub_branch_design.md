# 허브 앱 / 브랜치 앱 체제 — 확정 설계 (2026-10-27)

4순위(Streamlit 앱) 브랜치 앱 생성 체제에 대해 2026-10-23~27 논의로 확정한 내용.
스키마는 `scripts/12_migrate_hub_branch.py`(멱등)로 반영. 화면(app.py / 브랜치 앱) 구현은
다음 단계.

## 1. 명칭

| 구분 | 명칭 | DB 값 |
|---|---|---|
| 기존 오너 앱 | **허브 앱** | `entry_app = 'hub'` |
| 고객용 앱 | **브랜치 앱** | `entry_app = 'branch'` |
| 플랫폼 운영 주체(사람) | 운영사 / 운영자 | `author_role = 'operator'` |
| 고객사(사람) | 고객 관리자 / 고객 사용자 | `author_role = 'customer'` |

"어느 앱에서 했나"(hub/branch)와 "누가 했나"(operator/customer)를 분리해 기록한다.
예: 로컬 브랜치 고객이 허브 앱에서 양식을 작성 = `hub` + `customer`.

## 2. 고객 3유형 (`customer_type_policy`, `customer_account`)

| 유형 | 문서 | 양식 실적 | 템플릿 |
|---|---|---|---|
| ① 단순 사용자 `simple` | 허브에서 생성·보관 → **발행 + 다운로드 키**로 종결. 개정은 추가오더(새 발행+새 키) | 없음 | 없음 |
| ② 브랜치 `branch` | 허브·브랜치가 **같은 DB 행을 공유**, 양쪽 모두 개정 가능 | 브랜치 앱(또는 허브 앱)에서 입력, 서버 저장·공유 | 최대 30% 비공개 시 전체 활용 |
| ③ 로컬 브랜치 `local_branch` | 다운로드 키로 종결 | 허브 앱에서 작성, **저장은 고객 하드**(양식+json zip). 업로드 시 데이터 포함 양식으로 복구 | A/B안(아래) |

- 고객사에 전달된 문서는 고객사 입장에선 **원본**(배포본/사본 개념 아님) → 용어는 "발행".
- 보안과 무관하게 클라우드를 쓰는 고객을 위해 허브 앱에도 양식 실적 입력·기록 보관 기능을 둔다
  (브랜치와 같은 `form_record` 테이블 사용 → 어느 앱에서 입력해도 공유).
- 유형별 수치(30%, 50%, 12개월, 1건)는 코드 고정이 아니라 `customer_type_policy` 설정값.
  요금 확정 후 함께 조정.

## 3. 문서 발행과 다운로드 키 (`doc_release`, `doc_release_item`, `download_key`, `download_log`)

- 발행 = 그 시점의 `document_individual` 개정번호·storage_path 묶음을 박제
  → 이후 개정돼도 "11/01 발행분엔 P530 Rev.2" 재현 가능(7.5.3 배포 이력).
- 다운로드 키는 sha256 해시만 저장(원문은 고객에게 1회 표시), 만료일·최대 횟수·폐기.
- `download_log`가 단순 사용자의 문서 단위 메타데이터(어떤 발행분을 언제 받았나).

## 4. 브랜치 양방향 개정 — 충돌 방지

`document_individual`은 (신청건, 문서종류)당 1행 + `revision_no` UPDATE 구조이므로 별도
`base_revision_id` 대신 **`revision_no` 자체를 낙관적 잠금 토큰**으로 쓴다.

```sql
UPDATE document_individual
   SET revision_no = revision_no + 1, last_author_role = %s, storage_path = %s
 WHERE doc_id = %s AND revision_no = %s   -- 편집 시작 시점의 값
-- 0행이면 "그 사이 다른 쪽이 개정함" → 저장 거부, 최신본 다시 열기 안내
```

`document_individual.last_author_role`, `document_revision_log.author_role/author_user_id`로
누가 개정했는지 남김 → 허브 앱에서 "고객이 개정한 문서" 알림 가능.

## 5. 양식 실적 기록 (`form_record`, `form_record_payload`)

- `form_record`: 신청건, 양식 문서(doc_id), **작성 당시 양식 개정번호**, 기록일, 입력 앱, 작성 주체,
  `evidence_ref`. 트리거로 "양식 문서인지 / 같은 신청건 문서인지" 검증.
- **실적 원본은 `form_record_payload`로 분리**(값 + 해시) — 운영자 DB 권한 차단·고객별 암호화를
  이 테이블에만 적용하기 위함.
- 로컬 브랜치 실적 원본은 서버에 저장하지 않는다. 다운로드 zip = 보기용 양식(HWPX/PDF) +
  복구용 json(양식코드·개정번호·입력값·해시). 복구 키는 json이 기본, HWPX 필드 읽기는 보조.

### evidence_ref 형태 (jsonb)

```json
{"type": "erp", "system": "더존 iCUBE", "menu": "생산관리 > 작업일보",
 "period": "2026-10", "note": "월별 출력본으로 심사 시 제시"}
```

`type` ∈ `erp | paper | file | external`(CHECK 제약). 양식별 기본값은
`doc_type.default_evidence`, 기록마다 덮어쓰기 가능. ERP 연속발생형 기록은 데이터를 끌어오지 않고
이 증빙 위치로 대체(기존 결정 유지).

## 6. 데이터 공유 정책

| 층 | 대상 | 허브 활용 |
|---|---|---|
| 사용 메타데이터 | 3유형 공통 원칙(실제 발생: 양식 작성 고객의 필드 정보, 단순 사용자는 문서 단위) | 기본 허용(약관) — 양식·플랫폼 개선 |
| 익명 통계·벤치마크 | — | **제외**(사업 취지와 다름) |
| 공용 기록 템플릿 | 공개 양식의 익명화 기록 | 검수 후 게시 |
| 실적 원본 | — | 원칙적 불가, 고객 승인 기한부 접근만 |

### 6-1. 필드 사용 메타데이터 (`form_field_usage`)

필드 1개 입력당: 입력 여부, **글자 수, 표시 폭(전각 2/반각 1), 줄 수, 넘침 여부**.
숫자·금액 필드는 정확한 길이 대신 **자릿수 구간(`numeric_bucket`)만**(CHECK로 강제).
판단: 필드별 분포의 P90~P95 폭 기준, 넘침 비율 높은 필드 우선 개선. 로컬 고객은 복구용 json
업로드 시 이 항목만 계산해 남김(`source='local_upload'`).

### 6-2. 공개/비공개 (`form_disclosure_setting`, `doc_type.is_personal_data`)

- 비공개 단위 = **양식 종류**(설정 행 없으면 공개로 간주).
- **개인정보 양식**(건강진단, 산업재해·사고조사, 개인별 교육훈련 등)은 운영자가
  `is_personal_data=true` 지정 → 고객 설정과 무관하게 항상 비공개, **비율 분모에서도 제외**.
- 브랜치: 비공개 ≤ 30%. 로컬 브랜치: 비공개 ≤ 50%(상위 요금제 혜택 —
  고객 안내 문구: "로컬 요금제는 비공개 가능 범위가 더 넓습니다(최대 50%)").
- 업종별 고객 수 부족 시 게시 보류 규칙은 **두지 않음**(업종이 세분화돼 대부분 고객이 적고,
  업종 노하우는 비공개 범위로 보호됨).

### 6-3. 템플릿 활용 자격

- 브랜치: 비공개 비율이 한도 이내면 전체 활용.
- 로컬 브랜치(유료 방식 삭제, 기여 기반):
  - **A안**: 비공개 ≤ 50% **그리고** 공개 양식마다 실제 승인 제출 → 전체 활용.
  - **B안**: 절차서 단위 — 그 절차서의 양식(개인정보 제외)이 전부 공개 + 각각 실제 승인 제출 →
    그 절차서 양식 템플릿만 활용. 절차서↔양식 연결은 기존 규칙대로 `doc_type.clause_ref` 공유.
  - 자격은 지정이 아니라 **실제 제출 기준**: 공개 양식별 최근 12개월 내 승인(`approved`)
    제출 1건 이상. 제출 = 건별 선택 → 익명화 미리보기 → 고객 승인 → 전송.
- 단순 사용자: 없음(구독 전환 유도 포인트).

판정은 뷰로 제공: `v_form_disclosure_status`(신청건×양식), `v_template_access`(신청건 단위
비율·한도·전체 자격), `v_procedure_template_access`(B안 절차서별), `v_template_visible_form`
(템플릿 코너에 보여줄 양식 목록, `access_basis` = full | procedure).

### 6-4. 공용 템플릿 + 검수 (`record_template`)

- 고객 제공: 익명화(회사명·인명·주소·거래처명 제거/일반명칭 치환, 수치 구간화) →
  `submitted` → 운영자 검수 → `approved`/`rejected` → 승인분 중 선별해 `is_published`.
  게시는 승인분만(CHECK). "공개 = 원본 노출이 아니라 익명화→후보 풀→검수 후 일부 게시"를
  약관·화면에 명시(`customer_account.terms_version/terms_accepted_at`).
- 운영자 작성 예시(`source='operator'`)로 초기 코너를 먼저 채운다.

### 6-5. 신뢰 장치 (`operator_access_grant`, `operator_access_log`)

- 장애 대응 등으로 실적 원본을 봐야 할 때는 고객 관리자가 승인한 **기한부 접근**만.
- 운영자 접근 기록은 브랜치 앱에서 고객이 직접 조회.
- 인프라 운영자가 기술적으로 100% 못 보게 하긴 어려우므로 목적은 "약관 + 권한 분리 + 접근
  기록 공개로 신뢰 확보", 그래도 불안한 고객은 로컬 브랜치 유형.

## 7. 템플릿 코너(화면)

- 하나의 화면 모듈을 브랜치 앱(②)·허브 앱(③)이 공용. 위치: "📋 기록 작성 예시".
- `v_template_visible_form`으로 내 신청건에 허용된 양식만 표시 → 읽기 전용 미리보기 →
  "이 예시로 시작"(입력 화면을 예시 값으로 채움, 양식 개정판이 달라도 필드명 기준 매칭).
- 허브 앱: 제공 접수함 → 익명화 결과 확인 → 승인/반려 → 게시 선별.

## 8. 브랜치 앱 화면 구성(예정)

1. 📘 내 문서함(공유 문서 열람·개정, 개정 알림) 2. 📁 내 파일 보관함 3. ✍ 기록 입력 4. 📊 기록 대장
5. 📋 기록 작성 예시 6. 🔒 공개 설정(양식별 비공개 선택, 현재 비율/한도 표시) 7. 👥 사용자 관리
8. 🕵 운영자 접근 기록

## 9. 스키마 변경 요약 (12번 마이그레이션, 신규 14개 테이블 → 총 48개)

- 신규: `customer_type_policy`(시드 3), `customer_account`, `app_user`, `doc_release`,
  `doc_release_item`, `download_key`, `download_log`, `form_record`, `form_record_payload`,
  `form_disclosure_setting`, `record_template`, `form_field_usage`, `operator_access_grant`,
  `operator_access_log`
- 컬럼 추가: `document_individual.last_author_role`, `document_revision_log.author_role/
  author_user_id`, `doc_type.default_evidence/is_personal_data`
- 트리거: `trg_form_record_check` / 뷰 4종

검증(로컬 PostgreSQL 16, 실제 라이브 스키마 발췌 + 기존 데이터 선삽입): 최초/재실행 멱등,
기존 행 기본값, 브랜치 30%·로컬 50% 경계, 개인정보 양식 강제 비공개·분모 제외, 12개월 경과·
검수 대기 제출 불인정, A/B안 전환, 트리거·CHECK 제약 거부 케이스, 발행 스냅샷, revision_no
낙관적 잠금 충돌 감지 — 38개 검사 전부 통과.

## 10. 다음 단계(미착수)

1. 허브 앱(app.py): 명칭 변경, 고객 유형 지정·발행/다운로드 키 화면, 양식 실적 입력,
   템플릿 검수 화면, 개인정보 양식 지정(기준정보 → doc_type).
2. 브랜치 앱 신규(로그인/권한, 위 8번 화면).
3. 로컬 저장: 양식+json zip 다운로드/업로드 복구, 메타데이터 추출.
4. DB 권한 분리: 앱별 DB 계정 분리 후 `form_record_payload`에 운영자 계정 SELECT 차단
   (Cloud SQL 역할 설정), 이후 고객별 키 암호화.
