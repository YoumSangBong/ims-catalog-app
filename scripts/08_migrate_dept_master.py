"""
8단계: "조직 마스터 DB"(dept_code/dept_name 표준 부서 카탈로그) 추가 — 수정검토2.5 반영.

dept_code 체계(사용자 확정, 2026-09-07):
  {대분류: 한글 약칭}{중분류: 영문 소문자 1자}{세분류: 숫자 1자}
  예: 품질a1 = 대분류'품질'-중분류a-세분류1(품질보증팀), 회계a1(회계팀), 환경a1(환경팀).
  화면에서 마스터에 없는 새 부서명을 직접 등록하면 중분류를 'z'로 고정해 자동 채번한다
  (예: 품질z1) — 'z'가 붙은 코드는 사용자가 화면에서 추가한 항목임을 뜻한다.

표시 순서(중요, 2026-09-07 확정): dept_code 자체는 가나다순이 아니므로, 표준 표시순서는
dept_code 정렬이 아니라 별도의 category_seq 컬럼(대분류별 10,20,30...) 기준으로 정렬한다.
사용자가 확정한 대분류 순서:
  인사·회계·총무 → 경영·기획·관리 → 영업·구매·생산 → 품질·환경·안전보건 → 연구개발
parent_id 컬럼은 두지 않는다 — 신청건별 실제 조직 계층은 기존처럼
org_chart_role.parent_role_id로 별도 관리하고, 마스터는 표준 카탈로그 역할만 한다.

변경 내용:
  1) dept_master 테이블 신규 생성(category_seq 포함) + 대분류 13개 기준 시드 부서 16건 적재
  2) org_chart_role에 dept_code 컬럼 추가(dept_master 참조)

여러 번 실행해도 안전합니다(이미 적용된 항목/시드는 건너뜁니다).
실행: python scripts/08_migrate_dept_master.py
"""
from db import get_conn

# (category_code, category_name, category_seq) — category_code가 곧 dept_code의 대분류 부분.
# category_seq: 인사/회계/총무 → 경영/기획/관리 → 영업/구매/생산 → 품질/환경/안전보건 → 연구개발
CATEGORIES = [
    ("인사", "인사", 10), ("회계", "회계", 20), ("총무", "총무", 30),
    ("경영", "경영", 40), ("기획", "기획", 50), ("관리", "경영관리", 60),
    ("영업", "영업", 70), ("구매", "구매", 80), ("생산", "생산", 90),
    ("품질", "품질", 100), ("환경", "환경", 110), ("안전보건", "안전보건", 120),
    ("연구", "연구개발", 130),
]

# (dept_code, dept_name, category_code, relevant_std jsonb 문자열 또는 None)
# relevant_std: 신청건 active_stds와 교집합이 있으면 "자동생성" 화면에서 기본 추천으로 표시.
# None이면 업종/규격 무관하게 항상 추천(공통부서).
SEED_DEPTS = [
    ("인사a1", "인사팀", "인사", None),
    ("회계a1", "회계팀", "회계", None),
    ("총무a1", "총무팀", "총무", None),
    ("경영a1", "경영지원팀", "경영", None),
    ("기획a1", "기획팀", "기획", None),
    ("관리a1", "경영관리팀", "관리", None),
    ("영업a1", "영업팀", "영업", None),
    ("구매a1", "구매팀", "구매", None),
    ("생산a1", "생산팀", "생산", None),
    ("생산a2", "기술팀", "생산", None),
    ("품질a1", "품질보증팀", "품질", '["q"]'),
    ("품질a2", "품질관리팀", "품질", '["q"]'),
    ("환경a1", "환경팀", "환경", '["e"]'),
    ("안전보건a1", "안전보건팀", "안전보건", '["hs"]'),
    ("안전보건a2", "환경안전보건팀", "안전보건", '["e", "hs"]'),
    ("연구a1", "연구개발팀", "연구", None),
]


def main():
    conn = get_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS dept_master (
                        dept_code       varchar(10) PRIMARY KEY,
                        dept_name       varchar(100) NOT NULL,
                        category_code   varchar(10) NOT NULL,
                        category_name   varchar(50) NOT NULL,
                        category_seq    int NOT NULL DEFAULT 999,
                        relevant_std    jsonb,
                        is_custom       boolean NOT NULL DEFAULT false,
                        created_at      timestamptz NOT NULL DEFAULT now()
                    )
                    """
                )
                # 기존에 이 마이그레이션을 이미 실행한 적이 있어도(v1: category_seq 없이 생성된 경우)
                # 안전하게 컬럼을 보강한다.
                cur.execute(
                    "ALTER TABLE dept_master ADD COLUMN IF NOT EXISTS category_seq int NOT NULL DEFAULT 999"
                )
                cur.execute("CREATE INDEX IF NOT EXISTS ix_dept_master_category ON dept_master(category_code)")
                cur.execute("CREATE INDEX IF NOT EXISTS ix_dept_master_seq ON dept_master(category_seq)")
                print("dept_master 테이블 생성/보강 완료.")

                cat_by_code = {c: (n, s) for c, n, s in CATEGORIES}

                # 대분류 순서가 바뀌었을 수 있으니(예: 재실행), 이미 있는 행도 category_seq를 최신화한다.
                for category_code, (category_name, category_seq) in cat_by_code.items():
                    cur.execute(
                        "UPDATE dept_master SET category_name=%s, category_seq=%s WHERE category_code=%s",
                        (category_name, category_seq, category_code),
                    )

                for dept_code, dept_name, category_code, relevant_std in SEED_DEPTS:
                    category_name, category_seq = cat_by_code[category_code]
                    cur.execute(
                        """
                        INSERT INTO dept_master
                            (dept_code, dept_name, category_code, category_name, category_seq, relevant_std)
                        VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                        ON CONFLICT (dept_code) DO NOTHING
                        """,
                        (dept_code, dept_name, category_code, category_name, category_seq, relevant_std),
                    )
                print(f"dept_master 시드 {len(SEED_DEPTS)}건 적재 완료(이미 있으면 건너뜀).")

                cur.execute(
                    "ALTER TABLE org_chart_role ADD COLUMN IF NOT EXISTS dept_code "
                    "varchar(10) REFERENCES dept_master(dept_code)"
                )
                print("org_chart_role.dept_code 컬럼 추가 완료.")

        print("\n마이그레이션 완료. app.py를 최신 버전으로 교체한 뒤 streamlit run app.py로 확인해주세요.")
    except Exception as e:
        conn.rollback()
        print("오류 발생:", e)
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
