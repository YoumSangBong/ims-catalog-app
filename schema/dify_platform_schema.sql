-- ============================================================
-- 경영시스템문서 플랫폼 — 전체 DB 스키마 DDL (3순위 설계 결과물, 재검토 반영)
-- 대상: Cloud SQL PostgreSQL 인스턴스 ims-doc-instance (asia-northeast3, PG 18.4)
-- 작성일: 2026-08-17
-- 재검토1: 2026-08-18(한글SDK 확인 결과 반영, hwp_render_job 추가)
-- 재검토2: 2026-08-18(출력형식 요구사항 수정 — 병행X, 원본(HWP)+요청시 전환프로젝트
--          구조로 확정. application.project_no, conversion_project 테이블 추가)
-- (2026-08-23 지침서 관련 재검토3·4는 사용자 요청으로 되돌림 — 절차서까지
--  완성된 상태로 복귀했다가, 작성기준_r5 검토·협의를 거쳐 재검토5로 재반영)
-- 재검토5: 2026-08-24(작성기준_r5 기준 지침서=3레벨 문서 최종 확정 반영.
--          doc_type에 중분류/세분류/표기번호 컬럼 추가, guideline_item 추가,
--          document_integrated에 bundle_scope 추가로 절차서·지침서 통합본 분리)
-- 재검토6: 2026-08-24(작성기준_r7 기준 프로젝트제목 생성규칙 확정 — 소문자,
--          {std_code}{sector_code}{profile_seq 2자리}_{소스구분}{No}(소스명)|회사명.
--          application.project_no 규칙 갱신, sector_profile.profile_seq 추가,
--          doc_type에 원본추적용 source_project_title/source_original 추가)
-- 재검토7: 2026-08-24(샘플 문서 분석 워크플로우 — 4번째 워크플로우로 재도입.
--          sample_project_analysis/sample_doc_classification 테이블 추가:
--          ①프로젝트제목 도출(업종코드+profile_seq), ②절차서/지침서 구분 판정을
--          LLM 1차 판정 → 사람 검토 후 확정하는 감사로그 구조)
-- 실행 시점: 4순위 Streamlit 앱 1차 작업에서 DBeaver/psql로 실행
-- ============================================================

-- ---------- 영역 1. 기준정보 ----------

CREATE TABLE standard (
    std_code    varchar(4) PRIMARY KEY,        -- 'q','e','hs'
    iso_num     varchar(20) NOT NULL,           -- 'ISO 9001'
    title       varchar(50) NOT NULL,           -- '품질경영시스템'
    prefix      varchar(4) NOT NULL             -- 'Q'
);

CREATE TABLE sector_main (
    code        char(1) PRIMARY KEY,            -- M,U,C,S,I,E
    name        varchar(50) NOT NULL
);

CREATE TABLE iaf_group (
    iaf_num     varchar(2) PRIMARY KEY,
    name        varchar(100) NOT NULL
);

CREATE TABLE company (
    company_id      bigserial PRIMARY KEY,
    company_name    varchar(200) NOT NULL,
    biz_reg_no      varchar(20),
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE sector_profile (
    profile_id              bigserial PRIMARY KEY,
    sector_code             varchar(10) NOT NULL,          -- 'M17f'
    profile_seq             smallint NOT NULL,             -- 같은 sector_code 내 프로필 순번(1~99). 프로젝트제목(작성기준_r7)에
                                                             -- sector_code 뒤에 2자리 zero-pad로 이어붙임(예: M01a01) — 파싱 모호함 방지 위해 항상 2자리 고정.
    sector_main             char(1) NOT NULL REFERENCES sector_main(code),
    iaf_num                 varchar(2) NOT NULL REFERENCES iaf_group(iaf_num),
    sector_detail           char(1) NOT NULL,
    sector_name             varchar(200) NOT NULL,
    is_default              boolean NOT NULL DEFAULT false,
    hazards                 jsonb NOT NULL DEFAULT '[]',
    env_aspects              jsonb NOT NULL DEFAULT '[]',
    quality_chars            jsonb NOT NULL DEFAULT '[]',
    key_laws_sh              jsonb NOT NULL DEFAULT '[]',
    key_laws_env              jsonb NOT NULL DEFAULT '[]',
    process_hints             jsonb NOT NULL DEFAULT '[]',
    source_type               varchar(20) NOT NULL DEFAULT 'iaf_csv',  -- 'iaf_csv' | 'custom'
    created_by_company_id     bigint REFERENCES company(company_id),
    created_at                 timestamptz NOT NULL DEFAULT now(),
    CHECK (profile_seq BETWEEN 1 AND 99),
    UNIQUE (sector_code, profile_seq)
);
CREATE INDEX idx_sector_profile_code ON sector_profile(sector_code);

-- form_pattern: 양식(category='form') 자동화 디자인 패턴 참조테이블(2026-08-25 추가).
-- CHECK enum 대신 별도 테이블로 분리한 이유: 현재 4개 패턴은 소량 샘플로 검토한 잠정 분류이며,
-- 4순위 이후 양식 샘플이 더 확보되면 최종 패턴이 추가/조정될 예정 — 그때 스키마 변경(ALTER) 없이
-- 이 테이블에 행만 추가/수정하면 되도록 확장 가능하게 설계.
CREATE TABLE form_pattern (
    pattern_code   varchar(30) PRIMARY KEY,   -- 'register_log' 등
    pattern_name   varchar(100) NOT NULL,     -- '등록대장류'
    description    text                       -- 패턴 판별 기준 설명
);

CREATE TABLE doc_type (
    doc_type_id       bigserial PRIMARY KEY,
    doc_type_code     varchar(30) UNIQUE NOT NULL,   -- 'P610', 'P812(HS-1)', 'P810-01' 등 — doc_type_master 엑셀의 코드 그대로 사용(마스터, STD무관, QEHS 접두어 없음)
    doc_type_name     varchar(100) NOT NULL,         -- '리스크 및 기회관리'
    category          varchar(20) NOT NULL,          -- 'manual' | 'procedure' | 'form' | 'guideline'(2026-08-24 추가, 작성기준_r5)
    applicable_std    jsonb NOT NULL,                -- ['q','e','hs']
    applicable_label  varchar(30),                   -- '공통(순수)' | '공통(고유조항포함)' | 'Q전용' | 'E전용' | 'HS전용' | 'EHS통합전용' — doc_type_master의 "적용구분" 컬럼 그대로(사람이 읽는 분류, applicable_std로 완전히 유도되지 않는 정보 포함)
    is_mandatory      boolean NOT NULL DEFAULT true,
    clause_ref        varchar(20),                   -- '6.1.2' 등 doc_type_master의 "관련 ISO 조항"
    remark            text,                          -- doc_type_master의 "비고" — 코드 충돌 사유, 분류 근거 등 설계 메모 보존
    -- 아래 4개 컬럼은 category='guideline'인 행에만 채움(작성기준_r5, 2026-08-24 추가)
    subcategory        varchar(10),                  -- 중분류: '안전'|'보건'|'기술'|'생산'|'작업'|'품질'|'환경' 등
    subcategory_group  varchar(30),                  -- 세분류명: '일반작업안전' 등 (중분류를 한 단계 더 나눈 그룹)
    subcategory_letter char(1),                       -- 세분류문자: 세분류 그룹별 A,B,C... 부여
    display_code        varchar(20),                  -- 지침서 실제 문서 표기번호(규정번호 비노출): 예 'SI-A01' = 중분류이니셜(S)+I(지침서)-세분류문자+일련번호
    -- 아래 2개 컬럼은 원본 추적용(작성기준_r7, 2026-08-24 추가) — 이 doc_type 항목이 어느 샘플/원본에서 파생됐는지 기록
    source_project_title varchar(120),                -- 프로젝트제목(작성기준_r7 생성규칙, 소문자). 예: 'qm01a01_s01(itcpass)'
    source_original       varchar(120),                -- Original(원본출처) — 해당 샘플 소스 내 원본 문서 고유번호. 예: 'WJS-AF-01'
    -- 아래 1개 컬럼은 category='form'인 행에만 채움(2026-08-25 추가) — form_pattern 참조, 잠정 분류이므로 nullable
    form_pattern_code    varchar(30) REFERENCES form_pattern(pattern_code)
);

-- ---------- 영역 1-보조. 샘플 문서 분석 (2026-08-24 추가, 4번째 워크플로우) ----------
-- 회사가 보유한 기존 경영시스템 문서(풀버전 통합본 포함)를 업로드하면, 사람이 매번
-- 직접 판단하지 않아도 되도록 두 가지를 LLM이 1차 판정하고 사람이 검토·승인하는 구조.
-- ① 프로젝트제목 도출: 문서에서 회사개요·적용범위 등 짧은 발췌만 뽑고(전체를 읽지 않음),
--    sector_profile의 hazards/quality_chars/process_hints 키워드와 매칭해 후보를 4~8개로
--    압축한 뒤, 그 후보+발췌만 LLM에 줘서 최종 sector_code+profile_seq를 판정한다.
-- ② 절차서/지침서 구분: 통합본에 섞여 있는 개별 문서마다, "조직적 승인·검토·기록 절차의
--    유무"라는 확립된 기준을 few-shot으로 주고 LLM이 절차서/지침서와 판정근거를 낸다.
-- 두 판정 모두 reviewed=false로 감사로그에 남고, 사람이 검토·승인해야(Streamlit, 5~6순위)
-- 실제 sector_profile 연결(application.profile_id)이나 doc_type_master 반영으로 이어진다.
CREATE TABLE sample_project_analysis (      -- ① 프로젝트제목 도출 판정 로그
    analysis_id          bigserial PRIMARY KEY,
    source_file_name       varchar(255) NOT NULL,     -- 분석 대상 원본 파일명
    excerpt_text              text,                       -- 1단계: 회사개요/적용범위 등 발췌 텍스트(전체 문서 아님)
    candidate_profile_ids       jsonb,                      -- 2단계: 키워드 매칭으로 좁힌 후보 profile_id 배열(LLM 미사용)
    matched_keywords               jsonb,                      -- 매칭에 쓰인 키워드(hazards/quality_chars/process_hints 교집합)
    llm_sector_code                     varchar(10),               -- 3단계: LLM 최종 판정 sector_code
    llm_profile_seq                       smallint,                  -- 3단계: LLM 최종 판정 profile_seq
    llm_reasoning                           text,                      -- 판정근거
    reviewed                                  boolean NOT NULL DEFAULT false,
    resulting_profile_id                        bigint REFERENCES sector_profile(profile_id),  -- 승인 후 실제 연결
    created_at                                    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE sample_doc_classification (    -- ② 절차서/지침서 구분 판정 로그
    classification_id     bigserial PRIMARY KEY,
    analysis_id             bigint REFERENCES sample_project_analysis(analysis_id),  -- 같은 문서 세트 분석에 소속(선택)
    doc_title                 varchar(200) NOT NULL,
    doc_excerpt                 text,
    llm_category                   varchar(20),           -- 'procedure' | 'guideline' 판정
    llm_reasoning                     text,                  -- 판정근거(승인·검토·기록 절차 유무 등)
    reviewed                            boolean NOT NULL DEFAULT false,
    resulting_doc_type_id                  bigint REFERENCES doc_type(doc_type_id),  -- 승인 후 실제 연결
    created_at                              timestamptz NOT NULL DEFAULT now()
);

-- ---------- 영역 3. 조직도 (application보다 먼저 정의 — FK 순서) ----------

CREATE TABLE org_chart (
    org_chart_id        bigserial PRIMARY KEY,
    org_chart_name       varchar(200) NOT NULL,
    industry_tag          varchar(50),
    company_size_tag       varchar(20),             -- micro/small/medium/large
    source_company_id       bigint REFERENCES company(company_id),
    is_template               boolean NOT NULL DEFAULT true,
    created_at                 timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE org_chart_role (
    role_id         bigserial PRIMARY KEY,
    org_chart_id    bigint NOT NULL REFERENCES org_chart(org_chart_id),
    role_name       varchar(100) NOT NULL,     -- '품질경영팀장'
    department      varchar(100),
    parent_role_id  bigint REFERENCES org_chart_role(role_id),
    seq             int NOT NULL DEFAULT 0
);

-- ---------- 영역 2. 신청 건 ----------

CREATE TABLE application (
    application_id      bigserial PRIMARY KEY,
    company_id           bigint NOT NULL REFERENCES company(company_id),
    project_no             varchar(120) UNIQUE NOT NULL,  -- 프로젝트제목 생성규칙(작성기준_r7, 2026-08-24 확정, 소문자):
                                                            -- {std_code 소문자}{sector_code}{profile_seq 2자리}_{소스구분}{No 2자리}({소스명}) | 회사명
                                                            -- 소스구분: s=기존외부소싱샘플 n=신규내부제작샘플 x=기존내부보유 (없음)=신규내부제작(실제 회사)
                                                            -- 예: qm01a01_s01(itcpass), qehsc82f01_경영시스템주식회사. 애플리케이션(백엔드)에서 생성해 채움, 원본(HWP) 프로젝트는 접미사 없음
    std_code_normalized    varchar(4) NOT NULL,     -- 'q'|'e'|'hs'|'qe'|'qhs'|'ehs'|'qehs' 7종 그대로 저장
    active_stds              jsonb NOT NULL,          -- ['q','e','hs'] 형태 배열 — doc_type 매칭용
    sector_code                 varchar(10) NOT NULL,
    profile_id                    bigint REFERENCES sector_profile(profile_id),
    org_chart_id                    bigint REFERENCES org_chart(org_chart_id),
    status                            varchar(20) NOT NULL DEFAULT 'in_progress',
    created_at                         timestamptz NOT NULL DEFAULT now()
);

-- ---------- 영역 2-보조. 전환 프로젝트 (3순위 재검토 2차, 2026-08-18 추가) ----------
-- 한글(HWP)이 원본이며 application 자체가 원본 프로젝트다(project_no에 접미사 없음).
-- 엑셀/워드 전환본은 "병행 생성"이 아니라, 원본 완성 후 필요할 때 사용자가 별도로
-- 요청해서 만드는 "전환 프로젝트"다. process_step/org_chart/책임과 권한 등 콘텐츠
-- 생성 테이블은 전환 프로젝트에서 중복 생성하지 않는다 — 내용은 원본 그대로이고
-- 파일 형식만 바뀌기 때문. 전환 대상 범위는 전체(매뉴얼+절차서 전 문서).
CREATE TABLE conversion_project (
    conversion_id       bigserial PRIMARY KEY,
    application_id       bigint NOT NULL REFERENCES application(application_id),  -- 원본(HWP) 프로젝트
    project_no             varchar(120) UNIQUE NOT NULL,  -- 원본 project_no + '_Exl' 또는 '_Wrd'
    format                    varchar(10) NOT NULL,          -- 'xlsx' | 'docx'
    status                       varchar(20) NOT NULL DEFAULT 'requested',  -- requested|in_progress|done|failed
    storage_root_path               varchar(500),
    requested_at                       timestamptz NOT NULL DEFAULT now(),
    completed_at                         timestamptz
);
CREATE INDEX idx_conversion_project_app ON conversion_project(application_id);

-- 통합규격(qe/qhs/ehs/qehs) 전용 테이블은 두지 않는다. std_code_normalized에
-- 조합 문자열을 그대로 저장하고, active_stds(개별 토큰 배열)로 doc_type을
-- 매칭한다. 예) 이 신청 건에 필요한 문서종류 조회:
--
--   SELECT dt.* FROM doc_type dt, application a
--   WHERE a.application_id = :id
--     AND dt.applicable_std ?| ARRAY(SELECT jsonb_array_elements_text(a.active_stds));
--
-- applicable_std가 ['q']뿐인 문서(품질 전용)는 std_code_normalized가 'qehs'여도
-- active_stds에 'q'가 포함되어 있으면 자동으로 걸린다 — 7가지 조합을 doc_type
-- 쪽에 미리 다 등록해 둘 필요가 없다.

-- ---------- 영역 4. 절차서 생성 결과 (v0.2 확장) ----------

CREATE TABLE process_step (
    step_id          bigserial PRIMARY KEY,
    application_id   bigint NOT NULL REFERENCES application(application_id),
    doc_type_id      bigint NOT NULL REFERENCES doc_type(doc_type_id),
    pdca_stage       varchar(1) NOT NULL,     -- P/D/C/A
    stage_seq        int NOT NULL,
    step_name        varchar(200) NOT NULL,
    clause_no        varchar(10),             -- '6.1'
    created_at       timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE process_step_io (
    io_id       bigserial PRIMARY KEY,
    step_id     bigint NOT NULL REFERENCES process_step(step_id),
    io_type     varchar(10) NOT NULL,          -- 'input'|'output'
    io_desc     varchar(300) NOT NULL
);

CREATE TABLE process_step_activity (
    activity_id     bigserial PRIMARY KEY,
    step_id         bigint NOT NULL REFERENCES process_step(step_id),
    activity_desc   text NOT NULL,
    seq             int NOT NULL DEFAULT 0
);

CREATE TABLE process_dependency (
    dependency_id   bigserial PRIMARY KEY,
    from_step_id    bigint NOT NULL REFERENCES process_step(step_id),
    to_step_id      bigint NOT NULL REFERENCES process_step(step_id)
);

CREATE TABLE term_dictionary (
    term_id         bigserial PRIMARY KEY,
    std_code        varchar(4) NOT NULL,
    term            varchar(100) NOT NULL,
    definition      text NOT NULL,
    source_clause   varchar(20)
);

CREATE TABLE process_term_usage (
    usage_id    bigserial PRIMARY KEY,
    step_id     bigint NOT NULL REFERENCES process_step(step_id),
    term_id     bigint NOT NULL REFERENCES term_dictionary(term_id)
);

CREATE TABLE responsibility_matrix (
    resp_id     bigserial PRIMARY KEY,
    step_id     bigint NOT NULL REFERENCES process_step(step_id),
    role_id     bigint NOT NULL REFERENCES org_chart_role(role_id),
    resp_type   varchar(10) NOT NULL            -- '수행'|'검토'|'승인'
);

-- ---------- 영역 4-보조. 지침서 생성 결과 (2026-08-24 추가, 작성기준_r5) ----------
-- 지침서는 절차서(process_step/responsibility_matrix)와 달리 PDCA·조직 승인 흐름이 없고,
-- "항목 제목·수치기준·작업방법·근거법규"를 나열하는 기술기준 목록 구조다. 생성 방식은
-- (1) 중분류/세분류/제목으로 방향 결정 → (2) 샘플 프레임(디자인)을 선택 → (3) 지침서내용샘플
-- (기존 확보 지침서 텍스트·이미지) + 제목 관련 주요특성을 입력으로 LLM이 본문을 작성하며,
-- 지식노드에 근거 법규 원문이 있으면 그 원문에서 수치기준을 가져와 정확도를 높이고,
-- 없으면 지침서내용샘플+주요특성만으로 작성하되 이 경우 사람 검토(needs_review)를 거친다.
CREATE TABLE guideline_item (
    item_id             bigserial PRIMARY KEY,
    application_id      bigint NOT NULL REFERENCES application(application_id),
    doc_type_id         bigint NOT NULL REFERENCES doc_type(doc_type_id),
    item_title          varchar(200) NOT NULL,       -- 항목 제목
    tech_standard        text,                          -- 수치기준(예: 조도 75~750lux)
    work_method            text,                          -- 작업방법
    source_regulation       varchar(200),                  -- 근거법규(산업안전보건기준에관한규칙 등)
    content_source_type      varchar(20) NOT NULL DEFAULT 'sample',
                                                            -- 'regulation'(지식노드 법규원문 기반) | 'sample'(지침서내용샘플+주요특성만 사용, 법규원문 없음)
    needs_review              boolean NOT NULL DEFAULT false, -- content_source_type='sample'이면 true — 법규원문 대조 없이 생성되어 사람 검토 필요
    created_at                  timestamptz NOT NULL DEFAULT now()
);

-- ---------- 영역 5. 양식 ----------

CREATE TABLE form_template (
    form_id         bigserial PRIMARY KEY,
    application_id  bigint NOT NULL REFERENCES application(application_id),
    step_id         bigint REFERENCES process_step(step_id),
    form_name       varchar(200) NOT NULL
);

CREATE TABLE form_field (
    field_id    bigserial PRIMARY KEY,
    form_id     bigint NOT NULL REFERENCES form_template(form_id),
    field_name  varchar(100) NOT NULL,
    field_type  varchar(20) NOT NULL,           -- text/date/number/signature 등
    seq         int NOT NULL DEFAULT 0
);

-- ---------- 영역 5. 문서 보관 ----------

CREATE TABLE document_individual (       -- 개별본
    doc_id              bigserial PRIMARY KEY,
    application_id      bigint NOT NULL REFERENCES application(application_id),
    conversion_project_id  bigint REFERENCES conversion_project(conversion_id),  -- NULL=원본(HWP), 값 있으면 그 전환 프로젝트 소속 파일
    doc_type_id         bigint NOT NULL REFERENCES doc_type(doc_type_id),
    revision_no         int NOT NULL DEFAULT 1,
    format              varchar(10) NOT NULL,        -- 'hwp'(원본) | 'xlsx'|'docx'(전환)
    storage_path        varchar(500),
    status              varchar(20) NOT NULL DEFAULT 'draft',
    created_at          timestamptz NOT NULL DEFAULT now(),
    CHECK (
        (conversion_project_id IS NULL AND format = 'hwp')
        OR (conversion_project_id IS NOT NULL AND format IN ('xlsx', 'docx'))
    )
);

CREATE TABLE document_content (          -- 내용본
    content_id      bigserial PRIMARY KEY,
    doc_id          bigint NOT NULL REFERENCES document_individual(doc_id),
    content_text    text,
    extracted_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE document_integrated (       -- 통합본
    integrated_id       bigserial PRIMARY KEY,
    application_id       bigint NOT NULL REFERENCES application(application_id),
    conversion_project_id  bigint REFERENCES conversion_project(conversion_id),  -- NULL=원본(HWP), 값 있으면 그 전환 프로젝트 소속
    revision_no            int NOT NULL DEFAULT 1,
    format                    varchar(10) NOT NULL DEFAULT 'hwp',  -- 'hwp'(원본) | 'xlsx'|'docx'(전환)
    bundle_scope              varchar(10) NOT NULL DEFAULT 'core',
                                                    -- 'core'(매뉴얼+절차서+양식) | 'guideline'(지침서) — 2026-08-24 추가.
                                                    -- 같은 프로젝트(application)라도 절차서 계열 통합본과 지침서 통합본은
                                                    -- composed_doc_ids가 섞이지 않도록 별도 행으로 분리한다.
    storage_path              varchar(500),
    composed_doc_ids            jsonb NOT NULL,     -- [doc_id, doc_id, ...]
    created_at                    timestamptz NOT NULL DEFAULT now(),
    CHECK (
        (conversion_project_id IS NULL AND format = 'hwp')
        OR (conversion_project_id IS NOT NULL AND format IN ('xlsx', 'docx'))
    ),
    CHECK (bundle_scope IN ('core', 'guideline'))
);

CREATE TABLE document_revision_log (
    log_id          bigserial PRIMARY KEY,
    doc_id          bigint REFERENCES document_individual(doc_id),
    integrated_id   bigint REFERENCES document_integrated(integrated_id),
    revision_no     int NOT NULL,
    change_note     text,
    changed_at      timestamptz NOT NULL DEFAULT now()
);

-- ---------- 영역 5-보조. HWP 렌더링 작업 큐 (3순위 재검토, 2026-08-18 추가) ----------
-- 한글SDK가 서버자동화 라이선스인 것은 확인됨. 다만 현재는 Windows 서버에서만
-- 구동되고(리눅스 옵션은 추후 구매 시 재확인 필요), Postgres/Streamlit 등
-- 나머지 스택은 리눅스(Cloud Run 등)로 유지될 전망이라, HWP 출력 단계만 별도
-- Windows 서버로 원격 위임되는 비동기 구조가 됨. 이 위임 요청/결과를 추적하기
-- 위한 큐 테이블이다. 리눅스 옵션이 확정되어 별도 서버가 필요 없어지면 이
-- 테이블은 단순화하거나 제거해도 된다(문서 생성 로직 자체는 이 테이블에
-- 의존하지 않도록 설계함 — document_individual/document_integrated가 이미
-- 최종 결과의 storage_path를 갖고, hwp_render_job은 그 결과가 나오기까지의
-- 중간 상태만 추적).
CREATE TABLE hwp_render_job (
    job_id          bigserial PRIMARY KEY,
    doc_id          bigint REFERENCES document_individual(doc_id),
    integrated_id   bigint REFERENCES document_integrated(integrated_id),
    render_server   varchar(20) NOT NULL DEFAULT 'windows',  -- 'windows' | 'linux'(리눅스 옵션 확정 시)
    status          varchar(20) NOT NULL DEFAULT 'queued',   -- queued|processing|done|failed
    request_payload jsonb,
    output_path     varchar(500),
    error_msg       text,
    requested_at    timestamptz NOT NULL DEFAULT now(),
    completed_at    timestamptz,
    CHECK (doc_id IS NOT NULL OR integrated_id IS NOT NULL)
);
CREATE INDEX idx_hwp_render_job_status ON hwp_render_job(status);

-- ---------- 기존 통합본 샘플 분해 추적 (4순위 작업용) ----------

CREATE TABLE legacy_source_document (
    legacy_id       bigserial PRIMARY KEY,
    file_name       varchar(300) NOT NULL,
    uploaded_at     timestamptz NOT NULL DEFAULT now(),
    note            text
);

CREATE TABLE legacy_split_mapping (
    mapping_id  bigserial PRIMARY KEY,
    legacy_id   bigint NOT NULL REFERENCES legacy_source_document(legacy_id),
    doc_id      bigint NOT NULL REFERENCES document_individual(doc_id)
);

-- ============================================================
-- 기준정보 초기값 (standard 3개 규격) — 나머지 기준정보(sector_main,
-- iaf_group, sector_profile, doc_type)는 4순위에서 CSV Import로 적재
-- ============================================================

INSERT INTO standard (std_code, iso_num, title, prefix) VALUES
    ('q',  'ISO 9001',  '품질경영시스템',     'Q'),
    ('e',  'ISO 14001', '환경경영시스템',     'E'),
    ('hs', 'ISO 45001', '안전보건경영시스템', 'HS');
