"""
5단계: 수정검토 1.6 반영 — 이미 A단계로 만들어두신 Cloud SQL DB에 스키마 변경사항을 적용.

새로 스키마를 만드는 경우(01_init_schema.py를 처음 실행하는 경우)는 이미
schema/dify_platform_schema.sql에 아래 변경사항이 반영되어 있어 이 스크립트가 필요 없습니다.
이미 A단계를 완료해 데이터가 들어있는 기존 DB에만 이 스크립트를 실행하세요.

변경 내용:
  1) application.company_id를 nullable로 변경 (샘플 등록 시 NULL 허용)
  2) application에 sample_name / sample_original / org_scale 컬럼 추가
  3) application에 "company_id 또는 sample_name 중 하나만" CHECK 제약 추가
  4) company.biz_reg_no에 UNIQUE 제약 추가 (사업자등록번호 중복등록 방지)

여러 번 실행해도 안전합니다(이미 적용된 항목은 건너뜁니다).

실행: python scripts/05_migrate_review1_6.py
"""
from db import get_conn


def main():
    conn = get_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                # 1) company_id nullable
                cur.execute("ALTER TABLE application ALTER COLUMN company_id DROP NOT NULL")

                # 2) 신규 컬럼 3개
                cur.execute("ALTER TABLE application ADD COLUMN IF NOT EXISTS sample_name varchar(200)")
                cur.execute("ALTER TABLE application ADD COLUMN IF NOT EXISTS sample_original varchar(300)")
                cur.execute("ALTER TABLE application ADD COLUMN IF NOT EXISTS org_scale varchar(20)")

                # 3) 양자택일 CHECK 제약 (이미 있으면 건너뜀)
                cur.execute(
                    """
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM pg_constraint WHERE conname = 'chk_application_source'
                        ) THEN
                            ALTER TABLE application ADD CONSTRAINT chk_application_source CHECK (
                                (company_id IS NOT NULL AND sample_name IS NULL)
                                OR (company_id IS NULL AND sample_name IS NOT NULL)
                            );
                        END IF;
                    END $$;
                    """
                )
                print("application 테이블 변경 완료: company_id nullable / sample_name·sample_original·org_scale 추가 / 양자택일 제약.")

                # 4) company.biz_reg_no UNIQUE — 기존 중복값이 있으면 건너뛰고 알려줌
                cur.execute(
                    """
                    SELECT biz_reg_no, count(*) FROM company
                    WHERE biz_reg_no IS NOT NULL
                    GROUP BY biz_reg_no HAVING count(*) > 1
                    """
                )
                dupes = cur.fetchall()
                if dupes:
                    print("\n경고: biz_reg_no 중복값이 있어 UNIQUE 제약을 추가하지 않았습니다:")
                    for biz_reg_no, cnt in dupes:
                        print(f"  - {biz_reg_no}: {cnt}건")
                    print("먼저 중복된 회사 데이터를 정리한 뒤 이 스크립트를 다시 실행해주세요.")
                else:
                    cur.execute(
                        """
                        DO $$
                        BEGIN
                            IF NOT EXISTS (
                                SELECT 1 FROM pg_constraint WHERE conname = 'uq_company_biz_reg_no'
                            ) THEN
                                ALTER TABLE company ADD CONSTRAINT uq_company_biz_reg_no UNIQUE (biz_reg_no);
                            END IF;
                        END $$;
                        """
                    )
                    print("company.biz_reg_no UNIQUE 제약 추가 완료.")

        print("\n마이그레이션 완료. (org_chart.company_size_tag의 값 종류 변경은 컬럼 정의가 아니라 화면 입력값만\n바뀌는 부분이라 DB 변경 없이 app.py에만 반영되어 있습니다.)")
    except Exception as e:
        conn.rollback()
        print("오류 발생:", e)
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
