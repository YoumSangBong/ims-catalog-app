# ims-catalog-app — 4순위 1차: DB 스키마 + 기준정보 적재 + Streamlit 화면 골격

경영시스템문서 플랫폼 4순위(Streamlit 앱 1차)의 스크립트/화면입니다.
Cloud SQL(`ims-doc-instance`)에 30개 테이블 스키마를 만들고, doc_type 마스터(66건)와
업종 프로필(IAF 562건)을 적재하는 A단계, Streamlit 화면 골격(`app.py`)을 만든 B단계에
이어, 이번 전달분에는 **수정검토1.6 반영(스키마 변경 + 화면 재구성)**이 추가되었습니다.
9개 샘플 패키지 DB 적재(C단계)는 다음 전달분입니다.

이미 A단계·B단계를 완료하셨다면, 이번엔 **`scripts/05_migrate_review1_6.py` 한 단계만
새로 실행**하시고 `app.py`만 최신 버전으로 교체하시면 됩니다 — 자세한 건 "5. 수정검토1.6
반영" 절을 참고해주세요.

이 스크립트들은 **로컬 PC(VS Code)에서 직접 실행**하는 용도입니다. 아래 순서대로 진행해주세요.

## 0. 준비물 확인

- 이 폴더를 원하는 위치에 두세요 (예: 기존 `dify-workflow-project` 저장소 안에 폴더로 추가하거나, 새 폴더로 독립 사용).
- Cloud SQL `postgres` 계정 비밀번호를 알고 계셔야 합니다(모르면 GCP 콘솔 → `ims-doc-instance` → 사용자 → `postgres` 우측 ⋮ → 비밀번호 변경으로 새로 설정).
- 지금 작업 중인 PC의 공인 IP가 Cloud SQL "연결 → 네트워킹 → 승인된 네트워크"에 등록되어 있어야 합니다(이미 확인하신 상태로 알고 있습니다).

## 1. 가상환경 만들고 패키지 설치

```
cd ims-catalog-app
python -m venv venv
venv\Scripts\activate        (Windows)
pip install -r requirements.txt
```

## 2. .env 파일 만들기

`.env.example`을 복사해서 `.env`로 이름을 바꾸고, `DB_PASSWORD`에 실제 비밀번호를 입력하세요.
`DB_HOST`는 이미 알려주신 퍼블릭 IP(`34.64.137.224`)로 채워져 있고, `DB_NAME`도 `ims_docs`로
채워져 있습니다 — 다르면 맞게 고쳐주세요. `.env`는 `.gitignore`에 이미 등록되어 있어
GitHub에 올라가지 않습니다.

## 3. 순서대로 실행

```
cd scripts
python 00_test_connection.py      # 접속 확인 (제일 먼저)
python 01_init_schema.py          # 30개 테이블 생성 + standard 3건
python 02_seed_doc_type.py        # form_pattern 4건 + doc_type 66건
python 03_seed_reference_data.py  # sector_main 6건 + iaf_group 39건 + sector_profile 562건
python 04_verify.py               # 결과 검증 (테이블 수·행 수 출력)
```

`04_verify.py` 실행 결과가 아래와 같이 나오면 정상입니다(제가 로컬 PostgreSQL로 미리
전체 스크립트를 실행해서 이 결과를 직접 확인했습니다).

```
테이블 30/30개 존재
30개 테이블 전부 확인됨.

주요 테이블 행 수:
  - standard: 3건
  - sector_main: 6건
  - iaf_group: 39건
  - sector_profile: 562건
  - form_pattern: 4건
  - doc_type: 66건
```

`doc_type`은 manual 1건 + procedure 52건 + guideline 13건으로 구성됩니다.

## 문제가 생기면 (A단계)

- `01_init_schema.py`에서 "already exists" 오류 → 예전에 이미 실행한 적이 있다는 뜻입니다. 처음부터 다시 하려면 DBeaver에서 `DROP SCHEMA public CASCADE; CREATE SCHEMA public;` 실행 후 1단계부터 다시.
- `02`에서 "duplicate key" 오류 → 이미 적재됨, 다시 실행할 필요 없음.
- `00_test_connection.py`에서 timeout/connection refused → 승인된 네트워크에 지금 PC의 IP가 등록되어 있는지, `.env`의 비밀번호가 맞는지 확인해주세요.

## 4. Streamlit 화면 실행 (B단계 — 이번 전달분)

A단계(1~3번)를 이미 완료하셨다면(=`04_verify.py` 결과가 정상이었다면) 바로 이어서
실행하시면 됩니다. **가상환경을 새로 만들 필요 없이, 기존 `ims-catalog-app` 폴더에
`app.py`만 추가하시면 됩니다.**

```
cd ims-catalog-app          (scripts 폴더가 아니라 최상위 폴더입니다)
venv\Scripts\activate       (이미 활성화되어 있다면 생략)
streamlit run app.py
```

정상적으로 실행되면 자동으로 브라우저가 열리고 `http://localhost:8501` 주소로
"경영시스템문서 플랫폼" 화면이 뜹니다. 왼쪽 사이드바에 "DB 연결됨"이라는 초록색
메시지가 보이면 정상입니다. 안 뜨면 터미널 창에 있는 URL을 직접 브라우저 주소창에
입력해도 됩니다. 종료할 때는 터미널 창에서 `Ctrl + C`를 누르세요.

화면 구성 (왼쪽 사이드바에서 전환):

1. **기준정보 조회** — standard / sector_main / iaf_group / sector_profile / doc_type / form_pattern
   6개 테이블을 골라서 조회합니다. sector_profile은 업종코드·업종명으로, doc_type은
   분류(매뉴얼/절차서/지침서/양식)와 적용규격(품질/환경/안전보건)으로 필터링할 수 있습니다.
2. **사용자 관리** — "사용자 등록"(실제 회사/샘플 통합, 아래 5번 참고)과 "조직도"
   두 항목입니다. 신청건을 등록하면 `project_no`(예: `qeM01a01_회사명`)가 자동으로
   만들어집니다.
3. **샘플 문서 관리** — 아직 비어 있습니다. 다음 전달분(C단계)에서 9개 샘플 패키지를
   적재하면 이 화면에 표시됩니다.
4. **문서 보관 조회** — 개별본/내용본/통합본 조회 화면입니다. 마찬가지로 C단계 데이터
   적재 전까지는 비어 있는 게 정상입니다.

### 문제가 생기면 (B단계)

- `streamlit run app.py`가 "streamlit: command not found"/인식할 수 없는 명령 →
  `venv\Scripts\activate`로 가상환경이 활성화된 상태인지 확인해주세요 (터미널 맨 앞에
  `(venv)`가 보여야 합니다).
- 사이드바에 "DB 연결 실패" 빨간 메시지 → A단계 때와 같은 원인입니다(`.env` 비밀번호,
  승인된 네트워크의 IP 등록 여부).
- 화면이 하얗게 뜨거나 오류가 보이면, 어떤 화면에서 어떤 오류가 떴는지 스크린샷으로
  보내주시면 바로 확인해드리겠습니다.

## 5. 수정검토1.6 반영 (이번 전달분)

사용자님이 검토해주신 xlsx(수정검토1.6)를 반영한 변경사항입니다. **처음 이 폴더를
새로 설치하시는 분은 이 단계를 건너뛰어도 됩니다** — `schema/dify_platform_schema.sql`에
이미 반영되어 있어서 1~3번 순서대로만 실행하면 됩니다. 이미 A단계를 완료해 Cloud SQL에
데이터가 들어있는 경우에만 아래 마이그레이션 스크립트를 한 번 실행해주세요.

```
cd scripts
python 05_migrate_review1_6.py
```

이 스크립트가 하는 일:

- `application` 테이블: `company_id`를 nullable로 변경하고 `sample_name`(샘플명) /
  `sample_original`(샘플 원본 소스명) / `org_scale`(직원수 규모) 컬럼을 추가합니다.
  "회사로 등록" 또는 "샘플로 등록" 중 하나만 가능하도록 제약도 함께 추가됩니다.
- `company` 테이블: `biz_reg_no`(사업자등록번호)에 중복 등록 방지 제약을 추가합니다.
  단, 기존에 이미 중복된 사업자등록번호가 있으면 제약을 건너뛰고 화면에 알려드리니,
  그 경우 중복 데이터를 정리한 뒤 다시 실행해주세요.

몇 번을 실행해도 안전합니다(이미 적용된 부분은 건너뜁니다).

**바뀐 화면 (2. 사용자 관리 > 사용자 등록)**:

- "등록 종류"에서 실제 회사/샘플 중 선택 — 회사는 회사명+사업자등록번호(111-11-11111
  형식), 샘플은 샘플명+Original(샘플 입수 소스명)을 입력합니다. 같은 사업자등록번호로
  다시 등록하면 새 회사를 만들지 않고 기존 회사에 신청건만 추가됩니다.
- "규격 선택"이 기존 복수선택 방식에서 q/e/hs/qe/qhs/ehs/qehs 7개 조합 중 하나를
  고르는 방식으로 바뀌었습니다.
- "업종 분류 수준"에서 세부 프로필까지 특정 가능한지, 아니면 업종코드까지만/대분류까지만
  확인 가능한지 선택할 수 있습니다 — 정확한 업종을 모르셔도 등록할 수 있습니다.
- "직원수 규모(Org.scale)"를 10인미만~1000인이상 6단계 중에서 선택합니다.

문서 물리저장은 Google Cloud Storage(GCS)로 확정했고, 경로 규칙은
`{규격조합}/{project_no}/{문서종류}_rev{개정번호}.{형식}`으로 정했습니다 — 실제 업로드
스크립트는 C단계(또는 이후 documint 통합)에서 준비합니다.

"조직 책임과 권한" 화면(부서별 미션·책임/권한·권한기준 등)은 별도 세션에서 설계 중이라
이번 전달분에는 포함하지 않았고, 기존 "조직도" 기능(조직도/직책 등록)을 그대로 두었습니다.

## 다음 단계 (다음 전달분 — C단계)

- 9개 샘플 패키지(한국안전기술, 크몽 QES, 크몽 WJS, 예스폼 6종)를 `legacy_source_document` /
  `document_individual` / `document_content`에 적재하는 스크립트
