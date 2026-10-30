"""
12_migrate_hub_branch.py — 허브 앱 / 브랜치 앱 체제 스키마 (멱등)

2026-10-27 확정 설계 반영 (claude/hub_branch_design.md 참고):
  - 고객 3유형(simple / branch / local_branch)과 유형별 정책값(비공개 비율 등)
  - 문서 발행(doc_release) + 다운로드 키(download_key)
  - 허브·브랜치 양방향 개정 시 작성 주체(operator / customer) 기록
  - 양식 실적 기록(form_record) + 실적 원본 분리 테이블(form_record_payload)
  - 증빙 위치(evidence_ref), 양식별 기본 증빙(doc_type.default_evidence)
  - 개인정보 양식 지정(doc_type.is_personal_data) — 공개 대상·비율 계산에서 제외
  - 양식 종류 단위 비공개 설정(form_disclosure_setting)
  - 공용 기록 템플릿 + 검수(record_template)
  - 필드 사용 메타데이터(form_field_usage) — 글자 수/표시 폭/줄 수/넘침
  - 운영자 기한부 접근 승인/접근 기록(operator_access_grant / operator_access_log)
  - 템플릿 활용 자격 판정 뷰 4종

실행:  python scripts/12_migrate_hub_branch.py
접속:  기존 스크립트(01~11)와 동일하게 scripts/db.py의 get_conn() 사용
       (.env의 DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD).
여러 번 실행해도 안전(이미 있는 테이블/컬럼/제약/시드는 건너뜀, 뷰는 재생성).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import get_conn  # noqa: E402


STEPS = []


def step(title):
    def deco(sql):
        STEPS.append((title, sql))
        return sql
    return deco


# ---------------------------------------------------------------------------
# 1. 고객 유형 정책 + 고객 계정 + 사용자
# ---------------------------------------------------------------------------
step("customer_type_policy 테이블 + 시드")("""
CREATE TABLE IF NOT EXISTS public.customer_type_policy (
    customer_type          varchar(20) PRIMARY KEY,
    type_label             varchar(50)  NOT NULL,
    -- 양식 종류 기준 최대 비공개 비율(0~1). NULL = 공개 개념 없음(단순 사용자)
    max_private_ratio      numeric(4,3),
    -- 템플릿 활용 규칙: none | disclose_ratio | ratio_or_procedure
    template_access_rule   varchar(30)  NOT NULL,
    -- 실제 제출 기준 자격: 공개 양식별 최근 N개월 내 승인 제출 M건 이상 (로컬 브랜치용)
    contribution_window_months  integer,
    min_contribution_per_form   integer,
    note                   text,
    CONSTRAINT customer_type_policy_ratio_chk
        CHECK (max_private_ratio IS NULL OR (max_private_ratio >= 0 AND max_private_ratio <= 1)),
    CONSTRAINT customer_type_policy_rule_chk
        CHECK (template_access_rule IN ('none', 'disclose_ratio', 'ratio_or_procedure'))
);
INSERT INTO public.customer_type_policy
    (customer_type, type_label, max_private_ratio, template_access_rule,
     contribution_window_months, min_contribution_per_form, note)
VALUES
    ('simple', '단순 사용자', NULL, 'none', NULL, NULL,
     '발행+다운로드 키로 종결, 개정은 추가오더. 문서 단위 메타데이터(다운로드 이력)만 발생.'),
    ('branch', '브랜치 사용자', 0.300, 'disclose_ratio', NULL, NULL,
     '허브·브랜치가 같은 행을 공유. 양식 종류 기준 최대 30% 비공개, 나머지 공개 시 템플릿 전체 활용.'),
    ('local_branch', '로컬 브랜치 사용자', 0.500, 'ratio_or_procedure', 12, 1,
     '실적 원본은 고객 하드에만 저장. 상위 요금제 혜택으로 최대 50% 비공개. A: 비율 충족 시 전체 활용, B: 절차서 단위 공개 시 해당 절차서 템플릿 활용. 자격은 실제 승인 제출 기준.')
ON CONFLICT (customer_type) DO NOTHING;
""")

step("customer_account 테이블")("""
CREATE TABLE IF NOT EXISTS public.customer_account (
    company_id         bigint PRIMARY KEY REFERENCES public.company(company_id),
    customer_type      varchar(20) NOT NULL REFERENCES public.customer_type_policy(customer_type),
    terms_version      varchar(20),          -- 동의한 약관 버전(공개·익명화·검수 조항 포함)
    terms_accepted_at  timestamptz,
    is_active          boolean NOT NULL DEFAULT true,
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now()
);
""")

step("app_user 테이블")("""
CREATE TABLE IF NOT EXISTS public.app_user (
    user_id        bigserial PRIMARY KEY,
    company_id     bigint REFERENCES public.company(company_id),
    role           varchar(20) NOT NULL,
    login_id       varchar(100) NOT NULL UNIQUE,
    display_name   varchar(100),
    password_hash  varchar(255),
    is_active      boolean NOT NULL DEFAULT true,
    created_at     timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT app_user_role_chk
        CHECK (role IN ('operator', 'customer_admin', 'customer_user')),
    -- 운영자는 회사 소속 없음, 고객 계정은 반드시 회사 소속
    CONSTRAINT app_user_company_chk
        CHECK ((role = 'operator' AND company_id IS NULL)
            OR (role <> 'operator' AND company_id IS NOT NULL))
);
""")

# ---------------------------------------------------------------------------
# 2. 문서 발행 + 다운로드 키
# ---------------------------------------------------------------------------
step("doc_release / doc_release_item 테이블")("""
CREATE TABLE IF NOT EXISTS public.doc_release (
    release_id        bigserial PRIMARY KEY,
    application_id    bigint NOT NULL REFERENCES public.application(application_id),
    released_at       timestamptz NOT NULL DEFAULT now(),
    released_by_user_id bigint REFERENCES public.app_user(user_id),
    released_by       varchar(100),
    note              text
);
CREATE INDEX IF NOT EXISTS idx_doc_release_app ON public.doc_release (application_id);

-- 발행 시점의 개정번호와 파일 위치를 그대로 박제(이후 개정돼도 발행분 재현 가능)
CREATE TABLE IF NOT EXISTS public.doc_release_item (
    release_id    bigint NOT NULL REFERENCES public.doc_release(release_id) ON DELETE CASCADE,
    doc_id        bigint NOT NULL REFERENCES public.document_individual(doc_id),
    revision_no   integer NOT NULL,
    storage_path  varchar(500),
    PRIMARY KEY (release_id, doc_id)
);
""")

step("download_key / download_log 테이블")("""
CREATE TABLE IF NOT EXISTS public.download_key (
    key_id         bigserial PRIMARY KEY,
    release_id     bigint NOT NULL REFERENCES public.doc_release(release_id),
    key_hash       char(64) NOT NULL UNIQUE,   -- sha256 hex. 원문 키는 고객에게 1회만 표시
    expires_at     timestamptz,
    max_downloads  integer,
    used_count     integer NOT NULL DEFAULT 0,
    revoked_at     timestamptz,
    created_at     timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT download_key_count_chk
        CHECK (used_count >= 0 AND (max_downloads IS NULL OR max_downloads > 0))
);
-- 단순 사용자의 문서 단위 메타데이터(어떤 발행분을 언제 받았는지)
CREATE TABLE IF NOT EXISTS public.download_log (
    log_id         bigserial PRIMARY KEY,
    key_id         bigint NOT NULL REFERENCES public.download_key(key_id),
    downloaded_at  timestamptz NOT NULL DEFAULT now()
);
""")

# ---------------------------------------------------------------------------
# 3. 양방향 개정: 작성 주체 기록
#    document_individual은 (application_id, doc_type_id)당 1행 + revision_no UPDATE 구조이므로
#    별도 base_revision_id 없이 revision_no 자체를 낙관적 잠금 토큰으로 사용:
#      UPDATE ... SET revision_no = revision_no + 1 ... WHERE doc_id = %s AND revision_no = %s(편집 시작 시점 값)
#    영향받은 행이 0이면 "그 사이 다른 쪽이 개정함" → 저장 거부.
# ---------------------------------------------------------------------------
step("document_individual / document_revision_log 작성 주체 컬럼")("""
ALTER TABLE public.document_individual
    ADD COLUMN IF NOT EXISTS last_author_role varchar(10) NOT NULL DEFAULT 'operator';
ALTER TABLE public.document_revision_log
    ADD COLUMN IF NOT EXISTS author_role varchar(10) NOT NULL DEFAULT 'operator';
ALTER TABLE public.document_revision_log
    ADD COLUMN IF NOT EXISTS author_user_id bigint REFERENCES public.app_user(user_id);
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'document_individual_author_chk') THEN
        ALTER TABLE public.document_individual ADD CONSTRAINT document_individual_author_chk
            CHECK (last_author_role IN ('operator', 'customer'));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'document_revision_log_author_chk') THEN
        ALTER TABLE public.document_revision_log ADD CONSTRAINT document_revision_log_author_chk
            CHECK (author_role IN ('operator', 'customer'));
    END IF;
END $$;
""")

# ---------------------------------------------------------------------------
# 4. doc_type 확장: 기본 증빙, 개인정보 양식
# ---------------------------------------------------------------------------
step("doc_type.default_evidence / is_personal_data")("""
ALTER TABLE public.doc_type ADD COLUMN IF NOT EXISTS default_evidence jsonb;
ALTER TABLE public.doc_type ADD COLUMN IF NOT EXISTS is_personal_data boolean NOT NULL DEFAULT false;
""")

# ---------------------------------------------------------------------------
# 5. 양식 실적 기록 (허브 앱=클라우드 고객 및 운영자 입력 / 브랜치 앱=브랜치 고객 입력)
#    로컬 브랜치 고객의 실적 원본은 여기에 저장하지 않음(복구용 json은 고객 하드).
# ---------------------------------------------------------------------------
step("form_record / form_record_payload 테이블 + 정합성 트리거")("""
CREATE TABLE IF NOT EXISTS public.form_record (
    record_id          bigserial PRIMARY KEY,
    application_id     bigint NOT NULL REFERENCES public.application(application_id),
    doc_id             bigint NOT NULL REFERENCES public.document_individual(doc_id),
    form_revision_no   integer NOT NULL,      -- 작성 당시 양식 개정번호(양식이 개정돼도 과거 기록 유지)
    record_date        date NOT NULL,
    entry_app          varchar(10) NOT NULL,
    author_role        varchar(10) NOT NULL,
    entered_by_user_id bigint REFERENCES public.app_user(user_id),
    evidence_ref       jsonb,                 -- 내용 대신 증빙 위치(ERP/종이/파일/외부)
    is_deleted         boolean NOT NULL DEFAULT false,
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT form_record_entry_app_chk CHECK (entry_app IN ('hub', 'branch')),
    CONSTRAINT form_record_author_chk CHECK (author_role IN ('operator', 'customer')),
    CONSTRAINT form_record_evidence_type_chk CHECK (
        evidence_ref IS NULL OR (evidence_ref ? 'type'
            AND evidence_ref->>'type' IN ('erp', 'paper', 'file', 'external')))
);
CREATE INDEX IF NOT EXISTS idx_form_record_app_doc ON public.form_record (application_id, doc_id, record_date);

-- 실적 원본은 별도 테이블: 운영자 DB 권한 분리·고객별 암호화를 이 테이블에만 적용할 수 있게
CREATE TABLE IF NOT EXISTS public.form_record_payload (
    record_id     bigint PRIMARY KEY REFERENCES public.form_record(record_id) ON DELETE CASCADE,
    payload       jsonb NOT NULL,
    payload_hash  char(64) NOT NULL
);

CREATE OR REPLACE FUNCTION public.fn_form_record_check() RETURNS trigger AS $$
DECLARE
    v_app bigint;
    v_cat varchar;
BEGIN
    SELECT di.application_id, dt.category INTO v_app, v_cat
      FROM public.document_individual di
      JOIN public.doc_type dt ON dt.doc_type_id = di.doc_type_id
     WHERE di.doc_id = NEW.doc_id;
    IF v_cat IS DISTINCT FROM 'form' THEN
        RAISE EXCEPTION 'form_record.doc_id(%)는 양식(category=form) 문서가 아닙니다', NEW.doc_id;
    END IF;
    IF v_app IS DISTINCT FROM NEW.application_id THEN
        RAISE EXCEPTION 'form_record.doc_id(%)가 다른 신청건(%)의 문서입니다', NEW.doc_id, v_app;
    END IF;
    NEW.updated_at := now();
    RETURN NEW;
END $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_form_record_check ON public.form_record;
CREATE TRIGGER trg_form_record_check BEFORE INSERT OR UPDATE ON public.form_record
    FOR EACH ROW EXECUTE FUNCTION public.fn_form_record_check();
""")

# ---------------------------------------------------------------------------
# 6. 공개/비공개 설정 + 공용 기록 템플릿
# ---------------------------------------------------------------------------
step("form_disclosure_setting 테이블")("""
-- 행이 없으면 '공개'로 간주. 개인정보 양식(doc_type.is_personal_data)은 설정과 무관하게 항상 비공개.
CREATE TABLE IF NOT EXISTS public.form_disclosure_setting (
    application_id  bigint NOT NULL REFERENCES public.application(application_id),
    doc_type_id     bigint NOT NULL REFERENCES public.doc_type(doc_type_id),
    is_private      boolean NOT NULL DEFAULT false,
    updated_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (application_id, doc_type_id)
);
""")

step("record_template 테이블")("""
CREATE TABLE IF NOT EXISTS public.record_template (
    template_id                bigserial PRIMARY KEY,
    doc_type_id                bigint NOT NULL REFERENCES public.doc_type(doc_type_id),
    source                     varchar(10) NOT NULL,    -- operator(운영자 작성 예시) | customer(고객 제공)
    contributor_application_id bigint REFERENCES public.application(application_id),
    source_record_id           bigint REFERENCES public.form_record(record_id) ON DELETE SET NULL,
    form_revision_no           integer,
    anonymized_payload         jsonb NOT NULL,           -- 익명화·구간화가 끝난 값만 저장
    status                     varchar(10) NOT NULL DEFAULT 'submitted',
    is_published               boolean NOT NULL DEFAULT false,
    submitted_at               timestamptz NOT NULL DEFAULT now(),
    reviewed_by_user_id        bigint REFERENCES public.app_user(user_id),
    reviewed_at                timestamptz,
    review_note                text,
    CONSTRAINT record_template_source_chk CHECK (source IN ('operator', 'customer')),
    CONSTRAINT record_template_status_chk
        CHECK (status IN ('submitted', 'approved', 'rejected', 'withdrawn')),
    CONSTRAINT record_template_contrib_chk
        CHECK ((source = 'customer' AND contributor_application_id IS NOT NULL)
            OR (source = 'operator' AND contributor_application_id IS NULL)),
    -- 게시는 승인된 것만
    CONSTRAINT record_template_publish_chk CHECK (NOT is_published OR status = 'approved')
);
CREATE INDEX IF NOT EXISTS idx_record_template_doctype ON public.record_template (doc_type_id, is_published);
CREATE INDEX IF NOT EXISTS idx_record_template_contrib ON public.record_template (contributor_application_id, status);
""")

# ---------------------------------------------------------------------------
# 7. 사용 메타데이터 (3유형 공통 원칙. 실제로는 양식 작성이 있는 브랜치·로컬·클라우드 고객에서 발생)
# ---------------------------------------------------------------------------
step("form_field_usage 테이블")("""
CREATE TABLE IF NOT EXISTS public.form_field_usage (
    usage_id          bigserial PRIMARY KEY,
    application_id    bigint NOT NULL REFERENCES public.application(application_id),
    doc_type_id       bigint NOT NULL REFERENCES public.doc_type(doc_type_id),
    form_revision_no  integer,
    field_name        varchar(100) NOT NULL,     -- 고객 간 집계 키(같은 양식의 같은 필드)
    record_date       date,
    source            varchar(15) NOT NULL,      -- hub | branch | local_upload
    is_filled         boolean NOT NULL,
    char_count        integer,                   -- 글자 수
    display_width     integer,                   -- 표시 폭(전각=2, 반각=1)
    line_count        integer,                   -- 줄 수
    overflow          boolean,                   -- 현재 필드 폭 초과 여부
    numeric_bucket    varchar(10),               -- 숫자·금액 필드: 자릿수 구간만(정확한 길이 저장 안 함)
    collected_at      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT form_field_usage_source_chk CHECK (source IN ('hub', 'branch', 'local_upload')),
    CONSTRAINT form_field_usage_len_chk CHECK (
        (char_count IS NULL OR char_count >= 0)
        AND (display_width IS NULL OR display_width >= 0)
        AND (line_count IS NULL OR line_count >= 0)),
    -- 숫자 필드(구간 기록)는 정확한 길이를 남기지 않음
    CONSTRAINT form_field_usage_numeric_chk CHECK (
        numeric_bucket IS NULL OR (char_count IS NULL AND display_width IS NULL))
);
CREATE INDEX IF NOT EXISTS idx_form_field_usage_field ON public.form_field_usage (doc_type_id, field_name);
""")

# ---------------------------------------------------------------------------
# 8. 운영자 기한부 접근 승인 + 접근 기록(브랜치 앱에서 고객이 조회)
# ---------------------------------------------------------------------------
step("operator_access_grant / operator_access_log 테이블")("""
CREATE TABLE IF NOT EXISTS public.operator_access_grant (
    grant_id            bigserial PRIMARY KEY,
    application_id      bigint NOT NULL REFERENCES public.application(application_id),
    granted_by_user_id  bigint REFERENCES public.app_user(user_id),   -- 승인한 고객 관리자
    reason              text NOT NULL,
    granted_at          timestamptz NOT NULL DEFAULT now(),
    expires_at          timestamptz NOT NULL,
    revoked_at          timestamptz,
    CONSTRAINT operator_access_grant_period_chk CHECK (expires_at > granted_at)
);
CREATE TABLE IF NOT EXISTS public.operator_access_log (
    log_id            bigserial PRIMARY KEY,
    application_id    bigint NOT NULL REFERENCES public.application(application_id),
    grant_id          bigint REFERENCES public.operator_access_grant(grant_id),
    operator_user_id  bigint REFERENCES public.app_user(user_id),
    action            varchar(30) NOT NULL,     -- view_payload | export | support 등
    target_table      varchar(50),
    target_id         bigint,
    accessed_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_operator_access_log_app ON public.operator_access_log (application_id, accessed_at);
""")

# ---------------------------------------------------------------------------
# 9. 판정 뷰
#    - 대상 양식 = 그 신청건의 document_individual 중 category='form'
#    - 개인정보 양식은 공개 대상·분모에서 제외(30%/50% 한도와 별개)
#    - 신청건의 고객 유형 = application.company_id → customer_account (샘플 신청건은 NULL)
# ---------------------------------------------------------------------------
step("판정 뷰 4종 재생성")("""
DROP VIEW IF EXISTS public.v_template_visible_form;
DROP VIEW IF EXISTS public.v_procedure_template_access;
DROP VIEW IF EXISTS public.v_template_access;
DROP VIEW IF EXISTS public.v_form_disclosure_status;

-- (1) 신청건×양식: 공개 여부, 최근 승인 제출 건수
CREATE VIEW public.v_form_disclosure_status AS
SELECT a.application_id,
       ca.customer_type,
       di.doc_type_id,
       dt.doc_type_code,
       dt.clause_ref,
       dt.is_personal_data,
       CASE WHEN dt.is_personal_data THEN true
            ELSE COALESCE(fds.is_private, false) END            AS is_private,
       (SELECT COUNT(*) FROM public.record_template rt
         WHERE rt.contributor_application_id = a.application_id
           AND rt.doc_type_id = di.doc_type_id
           AND rt.status = 'approved'
           AND rt.submitted_at >= now() - make_interval(
                 months => COALESCE(ctp.contribution_window_months, 1200)))  AS recent_contributions
  FROM public.application a
  JOIN public.document_individual di ON di.application_id = a.application_id
  JOIN public.doc_type dt ON dt.doc_type_id = di.doc_type_id AND dt.category = 'form'
  LEFT JOIN public.customer_account ca ON ca.company_id = a.company_id
  LEFT JOIN public.customer_type_policy ctp ON ctp.customer_type = ca.customer_type
  LEFT JOIN public.form_disclosure_setting fds
         ON fds.application_id = a.application_id AND fds.doc_type_id = di.doc_type_id;

-- (2) 신청건 단위: 비공개 비율·한도 준수·전체 템플릿 활용 자격
CREATE VIEW public.v_template_access AS
WITH agg AS (
    SELECT application_id,
           customer_type,
           COUNT(*) FILTER (WHERE NOT is_personal_data)                      AS eligible_forms,
           COUNT(*) FILTER (WHERE NOT is_personal_data AND is_private)       AS private_forms,
           COUNT(*) FILTER (WHERE NOT is_personal_data AND NOT is_private)   AS public_forms,
           COUNT(*) FILTER (WHERE NOT is_personal_data AND NOT is_private
                              AND recent_contributions >= 1)                 AS public_forms_contributed,
           COUNT(*) FILTER (WHERE is_personal_data)                          AS personal_forms
      FROM public.v_form_disclosure_status
     GROUP BY application_id, customer_type
)
SELECT g.application_id,
       g.customer_type,
       g.eligible_forms, g.private_forms, g.public_forms,
       g.public_forms_contributed, g.personal_forms,
       CASE WHEN g.eligible_forms = 0 THEN 0
            ELSE ROUND(g.private_forms::numeric / g.eligible_forms, 3) END  AS private_ratio,
       p.max_private_ratio,
       (p.max_private_ratio IS NOT NULL AND g.eligible_forms > 0
        AND g.private_forms::numeric / g.eligible_forms <= p.max_private_ratio) AS within_private_limit,
       CASE
         WHEN p.template_access_rule = 'disclose_ratio' THEN
              g.eligible_forms > 0
              AND g.private_forms::numeric / g.eligible_forms <= p.max_private_ratio
         WHEN p.template_access_rule = 'ratio_or_procedure' THEN
              g.eligible_forms > 0
              AND g.private_forms::numeric / g.eligible_forms <= p.max_private_ratio
              -- 로컬: 지정만으로는 부족, 공개 양식마다 실제 승인 제출이 있어야 함
              AND g.public_forms_contributed = g.public_forms
         ELSE false
       END                                                                    AS full_template_access
  FROM agg g
  LEFT JOIN public.customer_type_policy p ON p.customer_type = g.customer_type;

-- (3) 로컬 브랜치 B안: 절차서 단위 자격
--     절차서↔양식 연결은 기존 규칙대로 doc_type.clause_ref 공유로 판단.
--     해당 절차서의 (개인정보 제외) 양식이 전부 공개 + 각각 최근 승인 제출이 있으면 활용 가능.
CREATE VIEW public.v_procedure_template_access AS
SELECT di.application_id,
       ca.customer_type,
       dp.doc_type_id                                     AS procedure_doc_type_id,
       dp.doc_type_code                                   AS procedure_code,
       dp.clause_ref,
       COUNT(s.doc_type_id) FILTER (WHERE NOT s.is_personal_data)              AS eligible_forms,
       COUNT(s.doc_type_id) FILTER (WHERE NOT s.is_personal_data AND NOT s.is_private
                                      AND s.recent_contributions >= 1)        AS ready_forms,
       (p.template_access_rule = 'ratio_or_procedure'
        AND COUNT(s.doc_type_id) FILTER (WHERE NOT s.is_personal_data) > 0
        AND COUNT(s.doc_type_id) FILTER (WHERE NOT s.is_personal_data)
          = COUNT(s.doc_type_id) FILTER (WHERE NOT s.is_personal_data AND NOT s.is_private
                                           AND s.recent_contributions >= 1)) AS procedure_access
  FROM public.document_individual di
  JOIN public.doc_type dp ON dp.doc_type_id = di.doc_type_id AND dp.category = 'procedure'
  JOIN public.application a ON a.application_id = di.application_id
  LEFT JOIN public.customer_account ca ON ca.company_id = a.company_id
  LEFT JOIN public.customer_type_policy p ON p.customer_type = ca.customer_type
  LEFT JOIN public.v_form_disclosure_status s
         ON s.application_id = di.application_id AND s.clause_ref = dp.clause_ref
 GROUP BY di.application_id, ca.customer_type, dp.doc_type_id, dp.doc_type_code,
          dp.clause_ref, p.template_access_rule;

-- (4) 템플릿 코너 필터: 이 신청건이 템플릿을 볼 수 있는 양식 목록
CREATE VIEW public.v_template_visible_form AS
SELECT s.application_id, s.doc_type_id, 'full'::varchar(10) AS access_basis
  FROM public.v_form_disclosure_status s
  JOIN public.v_template_access t ON t.application_id = s.application_id
 WHERE t.full_template_access
UNION
SELECT s.application_id, s.doc_type_id, 'procedure'::varchar(10)
  FROM public.v_form_disclosure_status s
  JOIN public.v_template_access t ON t.application_id = s.application_id
  JOIN public.v_procedure_template_access pa
    ON pa.application_id = s.application_id AND pa.clause_ref = s.clause_ref
 WHERE pa.procedure_access AND NOT t.full_template_access;
""")


def main():
    conn = get_conn()
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            for i, (title, sql) in enumerate(STEPS, 1):
                print(f"[{i:02d}/{len(STEPS)}] {title}")
                cur.execute(sql)
        conn.commit()
        print("완료: 12번 마이그레이션(허브/브랜치 체제) 적용")
    except Exception as e:
        conn.rollback()
        print(f"오류 — 전체 롤백했습니다: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
