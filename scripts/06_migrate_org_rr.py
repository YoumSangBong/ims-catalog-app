"""
6단계: "조직 책임과 권한" 화면 반영 — Cloud SQL DB 스키마 변경사항 적용.

배경: 기존 org_chart는 application과 무관하게 존재하는 "공용 템플릿" 성격이었으나
(application.org_chart_id로 참조), 검토 결과 조직도/부서목록/책임과 권한은 신청건
전용으로 관리하기로 확정(수정검토2.x). 대신 재사용은 "복사(유사 신청건 우선정렬)"
기능으로 제공한다. 기존 application.org_chart_id 컬럼은 더 이상 app.py에서 쓰지
않지만, 데이터 보존을 위해 DROP하지 않고 그대로 둔다.

변경 내용:
  1) org_chart에 application_id 컬럼 추가 (신청건 1건당 조직도 1개, UNIQUE)
  2) org_chart_role에 mission(부서 미션) 컬럼 추가
  3) dept_responsibility 테이블 신규 생성 ([2] 부서별 책임과 권한)
  4) application에 org_rr_status 컬럼 추가 (기본값 '미시작')
  5) org_rr_approval_log 테이블 신규 생성 ([4] 확정 시 스냅샷 이력)
  6) responsibility_matrix.resp_type 기존 한글 값('수행'/'검토'/'승인')을
     RACI 코드('R'/'C'/'A')로 변환 (해당 데이터가 있는 경우에만)

여러 번 실행해도 안전합니다(이미 적용된 항목은 건너뜁니다).

실행: python scripts/06_migrate_org_rr.py
"""
from db import get_conn


def main():
    conn = get_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                # 1) org_chart.application_id 추가 + UNIQUE
                cur.execute(
                    "ALTER TABLE org_chart ADD COLUMN IF NOT EXISTS application_id "
                    "bigint REFERENCES application(application_id)"
                )
                cur.execute(
                    """
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM pg_constraint WHERE conname = 'uq_org_chart_application'
                        ) THEN
                            ALTER TABLE org_chart ADD CONSTRAINT uq_org_chart_application UNIQUE (application_id);
                        END IF;
                    END $$;
                    """
                )
                print("org_chart.application_id 컬럼/UNIQUE 제약 추가 완료.")

                # 2) org_chart_role.mission 추가
                cur.execute(
                    "ALTER TABLE org_chart_role ADD COLUMN IF NOT EXISTS mission text"
                )
                print("org_chart_role.mission 컬럼 추가 완료.")

                # 3) dept_responsibility 신규 테이블
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS dept_responsibility (
                        resp_id               bigserial PRIMARY KEY,
                        role_id               bigint NOT NULL REFERENCES org_chart_role(role_id),
                        category              varchar(10) NOT NULL,   -- '책임'|'권한'
                        seq                   int NOT NULL DEFAULT 0,
                        content               text NOT NULL,
                        authority_criteria    varchar(300),           -- '권한'일 때 해당 시에만 수동 입력(공란 허용)
                        related_step_id       bigint REFERENCES process_step(step_id),
                        basis_doc             varchar(300),
                        required_competency   varchar(300),
                        created_at            timestamptz NOT NULL DEFAULT now()
                    )
                    """
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS ix_dept_responsibility_role "
                    "ON dept_responsibility(role_id)"
                )
                print("dept_responsibility 테이블 생성 완료.")

                # 4) application.org_rr_status 추가
                cur.execute(
                    "ALTER TABLE application ADD COLUMN IF NOT EXISTS org_rr_status "
                    "varchar(20) NOT NULL DEFAULT '미시작'"
                )
                print("application.org_rr_status 컬럼 추가 완료.")

                # 5) org_rr_approval_log 신규 테이블
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS org_rr_approval_log (
                        log_id          bigserial PRIMARY KEY,
                        application_id  bigint NOT NULL REFERENCES application(application_id),
                        rev_no          int NOT NULL,
                        snapshot        jsonb NOT NULL,
                        approved_by     varchar(100),
                        approved_at     timestamptz NOT NULL DEFAULT now()
                    )
                    """
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS ix_org_rr_approval_log_application "
                    "ON org_rr_approval_log(application_id)"
                )
                print("org_rr_approval_log 테이블 생성 완료.")

                # 6) responsibility_matrix 기존 한글 값 -> RACI 코드 변환 (있는 경우만)
                cur.execute("UPDATE responsibility_matrix SET resp_type = 'R' WHERE resp_type = '수행'")
                cur.execute("UPDATE responsibility_matrix SET resp_type = 'C' WHERE resp_type = '검토'")
                cur.execute("UPDATE responsibility_matrix SET resp_type = 'A' WHERE resp_type = '승인'")
                print("responsibility_matrix.resp_type 기존 값 RACI 코드 변환 완료(해당 데이터 없으면 변화 없음).")

        print("\n마이그레이션 완료. app.py를 최신 버전으로 교체한 뒤 streamlit run app.py로 확인해주세요.")
    except Exception as e:
        conn.rollback()
        print("오류 발생:", e)
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
