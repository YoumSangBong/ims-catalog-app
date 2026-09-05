# ims-catalog-app — 4순위 1차: DB 스키마 + 기준정보 적재 + Streamlit 화면 골격

경영시스템문서 플랫폼 4순위(Streamlit 앱 1차)의 스크립트/화면입니다.
Cloud SQL(`ims-doc-instance`)에 30개 테이블 스키마를 만들고, doc_type 마스터(66건)와
업종 프로필(IAF 562건)을 적재하는 A단계(지난 전달분, 이미 완료하셨습니다)에 이어,
이번 전달분에는 **B단계 — Streamlit 화면 골격(`app.py`)**이 추가되었습니다.
9개 샘플 패키지 DB 적재(C단계)는 다음 전달분입니다.

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
2. **신청건·조직도 관리** — 회사/신청건/조직도를 조회하고, 화면에서 직접 새로 등록할 수
   있습니다(테스트 삼아 회사 하나 등록해보시는 걸 추천드립니다). 신청건을 등록하면
   `project_no`(예: `qeM01a01_회사명`)가 자동으로 만들어집니다.
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

## 다음 단계 (다음 전달분 — C단계)

- 9개 샘플 패키지(한국안전기술, 크몽 QES, 크몽 WJS, 예스폼 6종)를 `legacy_source_document` /
  `document_individual` / `document_content`에 적재하는 스크립트
