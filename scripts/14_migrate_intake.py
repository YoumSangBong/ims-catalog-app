"""
14_migrate_intake.py — 고객 신청 정보 일괄 입력(입력은 고객, 생성은 운영자) 스키마 (멱등). 13번 실행 후.

흐름: 입력중(draft) → 제출(submitted) → 운영자 보완(completing) → 생성중(generating)
      → 고객 확인(customer_review) → 확정(finalized)
  - 신청 시 한 화면에서 일괄 입력, 필수 항목만 채우면 제출 가능
  - 선택 항목은 비워도 됨 → 운영자가 유추·판단(출처 = operator_inferred)
  - 피드백은 고객 확인 단계에서 추정값에 [맞음/수정]으로 한 번에. 미응답은 확정 시 운영자 판단값 적용
  - 생성 전 꼭 필요한 예외만 운영자가 '확인 필요' 지정

테이블: intake_field(항목 마스터, 시드) / intake_request / intake_value / intake_file / intake_stage_log
기존 대행 방식 신청건(application)은 영향 없음(intake_request가 없으면 대행 방식).

실행:  python scripts/14_migrate_intake.py   (scripts/db.py의 get_conn() 사용)
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import get_conn  # noqa: E402

DDL = """
DO $$ BEGIN
    IF to_regclass('public.customer_file') IS NULL THEN
        RAISE EXCEPTION '13번 마이그레이션(13_migrate_branch_app.py)을 먼저 실행하세요.';
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS public.intake_field (
    field_code   varchar(40) PRIMARY KEY,
    section      varchar(40) NOT NULL,
    section_seq  integer NOT NULL,
    label        varchar(100) NOT NULL,
    input_type   varchar(20) NOT NULL,
    is_required  boolean NOT NULL DEFAULT false,
    options      jsonb,          -- 선택지/출처/적용 규격 등
    help_text    text,           -- 고객에게 보이는 설명
    infer_note   text,           -- 미입력 시 운영자 유추 방법(운영자용)
    sort_order   integer NOT NULL DEFAULT 100,
    is_active    boolean NOT NULL DEFAULT true,
    CONSTRAINT intake_field_type_chk CHECK (input_type IN
        ('text','textarea','select','multiselect','yesno_reason','dept_list','checklist','file'))
);

CREATE TABLE IF NOT EXISTS public.intake_request (
    intake_id            bigserial PRIMARY KEY,
    company_id           bigint NOT NULL REFERENCES public.company(company_id),
    application_id       bigint UNIQUE REFERENCES public.application(application_id),
    stage                varchar(20) NOT NULL DEFAULT 'draft',
    created_by_user_id   bigint REFERENCES public.app_user(user_id),
    created_at           timestamptz NOT NULL DEFAULT now(),
    submitted_at         timestamptz,
    customer_reviewed_at timestamptz,
    finalized_at         timestamptz,
    operator_note        text,
    CONSTRAINT intake_request_stage_chk CHECK (stage IN
        ('draft','submitted','completing','generating','customer_review','finalized'))
);
CREATE INDEX IF NOT EXISTS idx_intake_request_company ON public.intake_request (company_id, stage);

CREATE TABLE IF NOT EXISTS public.intake_value (
    intake_id           bigint NOT NULL REFERENCES public.intake_request(intake_id) ON DELETE CASCADE,
    field_code          varchar(40) NOT NULL REFERENCES public.intake_field(field_code),
    value               jsonb,
    source              varchar(20) NOT NULL DEFAULT 'customer',
    confirm_required    boolean NOT NULL DEFAULT false,    -- 생성 전 꼭 확인(예외)
    confirm_status      varchar(15),                       -- pending | confirmed | corrected | auto_accepted
    customer_comment    text,
    updated_by_user_id  bigint REFERENCES public.app_user(user_id),
    updated_role        varchar(10) NOT NULL DEFAULT 'customer',
    updated_at          timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (intake_id, field_code),
    CONSTRAINT intake_value_source_chk CHECK (source IN
        ('customer','profile_default','operator_inferred','customer_confirmed')),
    CONSTRAINT intake_value_confirm_chk CHECK (confirm_status IS NULL OR confirm_status IN
        ('pending','confirmed','corrected','auto_accepted')),
    CONSTRAINT intake_value_role_chk CHECK (updated_role IN ('operator','customer'))
);

CREATE TABLE IF NOT EXISTS public.intake_file (
    file_id              bigserial PRIMARY KEY,
    intake_id            bigint NOT NULL REFERENCES public.intake_request(intake_id) ON DELETE CASCADE,
    field_code           varchar(40) NOT NULL REFERENCES public.intake_field(field_code),
    file_name            varchar(300) NOT NULL,
    storage_path         varchar(500) NOT NULL,
    size_bytes           bigint,
    uploaded_by_user_id  bigint REFERENCES public.app_user(user_id),
    uploaded_at          timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.intake_stage_log (
    log_id      bigserial PRIMARY KEY,
    intake_id   bigint NOT NULL REFERENCES public.intake_request(intake_id) ON DELETE CASCADE,
    from_stage  varchar(20),
    to_stage    varchar(20) NOT NULL,
    actor_role  varchar(10) NOT NULL,
    actor_user_id bigint REFERENCES public.app_user(user_id),
    note        text,
    changed_at  timestamptz NOT NULL DEFAULT now()
);
"""

# (field_code, section, section_seq, label, input_type, required, options, help, infer_note, sort)
FIELDS = [
    ("company_name", "회사 기본", 1, "회사명", "text", True, None, None, None, 10),
    ("biz_reg_no", "회사 기본", 1, "사업자등록번호", "text", True, None, "예: 123-45-67890", None, 20),
    ("site_address", "회사 기본", 1, "본사(인증 대상) 사업장 주소", "text", True, None, None, None, 30),
    ("org_scale", "회사 기본", 1, "인원 규모", "select", True,
     {"choices": ["10인미만", "10~49인", "50~99인", "100~299인", "300~999인", "1000인 이상"]}, None, None, 40),
    ("other_sites", "회사 기본", 1, "추가 사업장(공장·현장 등)", "textarea", False, None,
     "인증 범위에 포함할 다른 사업장이 있으면 이름과 주소", "없으면 본사 단일 사업장으로 판단", 50),
    ("standards", "인증 범위", 2, "인증 받을 규격", "multiselect", True, {"source": "standard"},
     "여러 개를 고르면 통합경영시스템으로 만듭니다", None, 10),
    ("cert_scope", "인증 범위", 2, "인증 범위(제품·서비스)", "textarea", True, None,
     "예: 자동차용 플라스틱 사출 부품의 제조", None, 20),
    ("sector_main", "업종·제품", 3, "산업 대분류", "select", True, {"source": "sector_main"}, None, None, 10),
    ("sector_profile", "업종·제품", 3, "세부 업종(아시면 선택)", "select", False, {"source": "sector_profile"},
     "고르면 아래 환경·안전 항목이 업종에 맞게 미리 채워집니다",
     "주요 제품·공정으로 운영자가 IAF 업종·프로필 판단(미정이면 대분류 임시코드)", 20),
    ("main_products", "업종·제품", 3, "주요 제품·서비스", "textarea", True, None, "매출 비중이 큰 순서로", None, 30),
    ("process_flow", "업종·제품", 3, "주요 공정(업무) 흐름", "textarea", False, None,
     "예: 원자재 입고 → 사출 → 검사 → 포장 → 출하", "업종 프로필의 공정 힌트로 운영자가 구성", 40),
    ("outsourcing", "업종·제품", 3, "외주(위탁) 공정", "textarea", False, None, None,
     "없음으로 간주하되 고객 확인 단계에서 확인", 50),
    ("has_design_dev", "업무 특성", 4, "설계·개발 업무", "yesno_reason", True, {"default": "있음"},
     "'없음'이면 그 사유를 적어 주세요(심사 시 적용 제외 근거)", None, 10),
    ("has_customer_prop", "업무 특성", 4, "고객 소유물(고객이 제공한 자재·금형·정보 등)", "yesno_reason", True,
     {"default": "있음"}, "'없음'이면 그 사유를 적어 주세요", None, 20),
    ("equipment", "업무 특성", 4, "주요 생산·작업 설비", "textarea", False, None, None,
     "업종 프로필 기준 일반 설비로 작성", 30),
    ("measuring", "업무 특성", 4, "측정·검사 장비", "textarea", False, None, None, "업종 일반 측정장비로 작성", 40),
    ("departments", "조직", 5, "부서 목록", "dept_list", True, None,
     "부서명만 필수입니다. 부서장·상위부서는 아시면 적어 주세요", None, 10),
    ("org_chart_file", "조직", 5, "조직도 파일(있으면)", "file", False, None,
     "파일이 있으면 위 부서 목록은 부서명만 적어도 충분합니다", "파일에서 상하 관계 판독", 20),
    ("env_aspects", "환경·안전", 6, "주요 환경측면", "checklist", False,
     {"profile_key": "env_aspects", "std": "e"}, "해당 없는 것은 체크를 해제하고, 빠진 것은 아래에 적어 주세요",
     "업종 프로필 기본값 사용", 10),
    ("hazards", "환경·안전", 6, "주요 유해·위험요인", "checklist", False,
     {"profile_key": "hazards", "std": "hs"}, None, "업종 프로필 기본값 사용", 20),
    ("key_laws", "환경·안전", 6, "적용 법규", "checklist", False,
     {"profile_key": ["key_laws_env", "key_laws_sh"], "std": ["e", "hs"]}, None, "업종 프로필 기본값 사용", 30),
    ("existing_docs", "기존 자료", 7, "기존 문서·양식(있으면)", "file", False, None,
     "기존에 쓰던 규정·양식이 있으면 반영합니다", None, 10),
    ("notes", "기존 자료", 7, "기타 특이사항", "textarea", False, None, None, None, 20),
]


def main():
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(DDL)
            for f in FIELDS:
                cur.execute(
                    "INSERT INTO intake_field (field_code, section, section_seq, label, input_type, is_required, "
                    "options, help_text, infer_note, sort_order) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                    "ON CONFLICT (field_code) DO NOTHING",   # 운영자가 바꾼 필수/선택 설정은 보존
                    (*f[:6], json.dumps(f[6], ensure_ascii=False) if f[6] else None, *f[7:]),
                )
        conn.commit()
        print(f"완료: 14번 마이그레이션(신청 정보 입력) 적용 — 항목 마스터 {len(FIELDS)}개 기준")
    except Exception as e:
        conn.rollback()
        print(f"오류 — 전체 롤백했습니다: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
