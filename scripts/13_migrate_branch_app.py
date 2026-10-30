"""
13_migrate_branch_app.py — 브랜치 앱(고객용) 보조 스키마 (멱등). 12번 실행 후 실행.

  - customer_file: 고객 자체 파일 보관함(브랜치 앱 '📁 파일 보관함')
  - app_user.must_change_password / last_login_at / failed_login_count
  - download_key 사용 처리용 인덱스

실행:  python scripts/13_migrate_branch_app.py   (scripts/db.py의 get_conn() 사용)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import get_conn  # noqa: E402

SQL = """
DO $$ BEGIN
    IF to_regclass('public.app_user') IS NULL THEN
        RAISE EXCEPTION '12번 마이그레이션(12_migrate_hub_branch.py)을 먼저 실행하세요.';
    END IF;
END $$;

ALTER TABLE public.app_user ADD COLUMN IF NOT EXISTS must_change_password boolean NOT NULL DEFAULT true;
ALTER TABLE public.app_user ADD COLUMN IF NOT EXISTS last_login_at timestamptz;
ALTER TABLE public.app_user ADD COLUMN IF NOT EXISTS failed_login_count integer NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS public.customer_file (
    file_id              bigserial PRIMARY KEY,
    application_id       bigint NOT NULL REFERENCES public.application(application_id),
    file_name            varchar(300) NOT NULL,
    storage_path         varchar(500) NOT NULL,
    size_bytes           bigint,
    note                 text,
    uploaded_by_user_id  bigint REFERENCES public.app_user(user_id),
    uploaded_at          timestamptz NOT NULL DEFAULT now(),
    is_deleted           boolean NOT NULL DEFAULT false
);
CREATE INDEX IF NOT EXISTS idx_customer_file_app ON public.customer_file (application_id, is_deleted);
CREATE INDEX IF NOT EXISTS idx_app_user_company ON public.app_user (company_id);
"""


def main():
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(SQL)
        conn.commit()
        print("완료: 13번 마이그레이션(브랜치 앱 보조 스키마) 적용")
    except Exception as e:
        conn.rollback()
        print(f"오류 — 전체 롤백했습니다: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
