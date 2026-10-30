"""
15_migrate_member_sso.py — 회원 정보 보완(경영시스템 문서 SNS 커뮤니티 SSO 준비) (멱등). 14번 실행 후.

커뮤니티(Discourse 등) SSO 체크리스트 대응:
  1) 회원 등급 단일 필드  — v_member_sso.member_tier (회사 회원은 customer_account.customer_type,
                            개인 회원은 app_user.member_tier). 등급 목록은 customer_type_policy 참조 테이블.
  2) 고유·불변 ID         — app_user.user_id (SSO external_id로 사용, 이메일이 바뀌어도 동일인)
  3) 이메일               — app_user.email(대소문자 무시 고유) + email_verified
  4) 회사·업종 연결       — app_user.company_id → company.sector_main(대표 업종 = IAF 대분류, 신규)
                            기존 데이터는 최근 신청건 → 신청 입력값 순으로 자동 채움,
                            이후 신청건이 생기면 트리거가 비어 있을 때만 자동 채움
  5) 무료 일반 회원       — customer_type_policy에 'free' 추가, app_user.role에 'member'(회사 없는 개인) 추가

실행:  python scripts/15_migrate_member_sso.py   (scripts/db.py의 get_conn() 사용)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import get_conn  # noqa: E402

SQL = r"""
DO $$ BEGIN
    IF to_regclass('public.intake_request') IS NULL THEN
        RAISE EXCEPTION '14번 마이그레이션(14_migrate_intake.py)을 먼저 실행하세요.';
    END IF;
END $$;

-- 3) 이메일
ALTER TABLE public.app_user ADD COLUMN IF NOT EXISTS email varchar(254);
ALTER TABLE public.app_user ADD COLUMN IF NOT EXISTS email_verified boolean NOT NULL DEFAULT false;
CREATE UNIQUE INDEX IF NOT EXISTS app_user_email_uniq ON public.app_user (lower(email)) WHERE email IS NOT NULL;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'app_user_email_fmt_chk') THEN
        ALTER TABLE public.app_user ADD CONSTRAINT app_user_email_fmt_chk
            CHECK (email IS NULL OR email ~ '^[^@\s]+@[^@\s]+\.[^@\s]+$');
    END IF;
END $$;

-- 5) 무료 일반 회원 등급 + 개인 회원 역할
INSERT INTO public.customer_type_policy (customer_type, type_label, max_private_ratio, template_access_rule, note)
VALUES ('free', '무료 일반 회원', NULL, 'none', '커뮤니티 참여용 개인 회원. 문서·기록 서비스 없음.')
ON CONFLICT (customer_type) DO NOTHING;

ALTER TABLE public.app_user ADD COLUMN IF NOT EXISTS member_tier varchar(20)
    REFERENCES public.customer_type_policy(customer_type);

ALTER TABLE public.app_user DROP CONSTRAINT IF EXISTS app_user_role_chk;
ALTER TABLE public.app_user ADD CONSTRAINT app_user_role_chk
    CHECK (role IN ('operator', 'customer_admin', 'customer_user', 'member'));
ALTER TABLE public.app_user DROP CONSTRAINT IF EXISTS app_user_company_chk;
ALTER TABLE public.app_user ADD CONSTRAINT app_user_company_chk CHECK (
       (role = 'operator' AND company_id IS NULL)
    OR (role = 'member' AND company_id IS NULL AND member_tier IS NOT NULL)        -- 개인 회원: 등급은 본인 행에
    OR (role IN ('customer_admin', 'customer_user') AND company_id IS NOT NULL AND member_tier IS NULL)  -- 회사 등급 따름
);

-- 4) 회사 대표 업종(IAF 대분류)
ALTER TABLE public.company ADD COLUMN IF NOT EXISTS sector_main char(1);
DO $$ BEGIN
    IF to_regclass('public.sector_main') IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'company_sector_main_fkey') THEN
        ALTER TABLE public.company ADD CONSTRAINT company_sector_main_fkey
            FOREIGN KEY (sector_main) REFERENCES public.sector_main(code);
    END IF;
END $$;

-- 기존 데이터 채우기: (a) 회사의 최근 신청건 업종코드 첫 글자
UPDATE public.company c SET sector_main = s.code
FROM (
    SELECT DISTINCT ON (a.company_id) a.company_id, left(a.sector_code, 1) AS code
    FROM public.application a WHERE a.company_id IS NOT NULL
    ORDER BY a.company_id, a.application_id DESC
) s
WHERE c.company_id = s.company_id AND c.sector_main IS NULL
  AND EXISTS (SELECT 1 FROM public.sector_main m WHERE m.code = s.code);

-- (b) 신청건이 없으면 최근 신청 입력값의 산업 대분류
UPDATE public.company c SET sector_main = s.code
FROM (
    SELECT DISTINCT ON (r.company_id) r.company_id, v.value #>> '{}' AS code
    FROM public.intake_request r
    JOIN public.intake_value v ON v.intake_id = r.intake_id AND v.field_code = 'sector_main'
    ORDER BY r.company_id, r.intake_id DESC
) s
WHERE c.company_id = s.company_id AND c.sector_main IS NULL
  AND EXISTS (SELECT 1 FROM public.sector_main m WHERE m.code = s.code);

-- 이후 신청건이 생기면 대표 업종이 비어 있을 때만 자동 채움(운영자가 지정한 값은 덮어쓰지 않음)
CREATE OR REPLACE FUNCTION public.fn_company_sector_fill() RETURNS trigger AS $$
BEGIN
    IF NEW.company_id IS NOT NULL THEN
        UPDATE public.company c SET sector_main = left(NEW.sector_code, 1)
         WHERE c.company_id = NEW.company_id AND c.sector_main IS NULL
           AND EXISTS (SELECT 1 FROM public.sector_main m WHERE m.code = left(NEW.sector_code, 1));
    END IF;
    RETURN NEW;
END $$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_company_sector_fill ON public.application;
CREATE TRIGGER trg_company_sector_fill AFTER INSERT ON public.application
    FOR EACH ROW EXECUTE FUNCTION public.fn_company_sector_fill();

-- SSO 연동이 읽을 단일 뷰(운영자 계정 제외). 커뮤니티에는 회사명을 넘기지 않음.
DROP VIEW IF EXISTS public.v_member_sso;
CREATE VIEW public.v_member_sso AS
SELECT u.user_id                                          AS external_id,
       u.login_id                                         AS username,
       COALESCE(u.display_name, u.login_id)               AS display_name,
       u.email,
       u.email_verified,
       COALESCE(ca.customer_type, u.member_tier)          AS member_tier,
       u.role,
       c.sector_main,
       sm.name                                            AS sector_main_name,
       (u.is_active AND COALESCE(ca.is_active, true))     AS is_active,
       (u.is_active AND COALESCE(ca.is_active, true)
        AND u.email IS NOT NULL AND u.email_verified)     AS community_ready
FROM public.app_user u
LEFT JOIN public.company c ON c.company_id = u.company_id
LEFT JOIN public.customer_account ca ON ca.company_id = u.company_id
LEFT JOIN public.sector_main sm ON sm.code = c.sector_main
WHERE u.role <> 'operator';
"""


def main():
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(SQL)
            cur.execute("SELECT COUNT(*) FILTER (WHERE sector_main IS NOT NULL), COUNT(*) FROM company")
            filled, total = cur.fetchone()
        conn.commit()
        print(f"완료: 15번 마이그레이션(회원·SSO 준비) 적용 — 회사 대표 업종 {filled}/{total}개 채움")
    except Exception as e:
        conn.rollback()
        print(f"오류 — 전체 롤백했습니다: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
