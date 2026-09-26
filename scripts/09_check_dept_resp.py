"""
진단 스크립트: 특정 dept_code(기본 '회계a1')로 등록된 org_chart_role과 그 아래
dept_responsibility 항목들을 있는 그대로 전부 보여준다.

"항목을 두 번 추가했는데 하나만 남는다"는 문제를 화면(Streamlit) 캐시나 표시 순서
문제와 실제 DB 데이터 문제를 구분해서 확인하기 위한 용도 — 여기서 보여주는 게 곧
DB에 실제로 저장된 값이다.

사용법:
  python scripts/09_check_dept_resp.py            # 기본값 '회계a1' 조회
  python scripts/09_check_dept_resp.py 품질z1      # 다른 dept_code 조회
"""
import sys

from db import get_conn


def main():
    dept_code = sys.argv[1] if len(sys.argv) > 1 else "회계a1"
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT r.role_id, r.org_chart_id, r.dept_code, r.role_name, r.mission,
                       oc.application_id
                FROM org_chart_role r
                JOIN org_chart oc ON oc.org_chart_id = r.org_chart_id
                WHERE r.dept_code = %s
                ORDER BY r.role_id
                """,
                (dept_code,),
            )
            roles = cur.fetchall()

            print(f"=== dept_code = '{dept_code}' 인 org_chart_role 행: {len(roles)}건 ===")
            if not roles:
                print("(해당 dept_code로 등록된 부서가 없습니다.)")
                return

            for role_id, org_chart_id, code, name, mission, application_id in roles:
                print(
                    f"\n[role_id={role_id}] org_chart_id={org_chart_id} "
                    f"application_id={application_id} dept_code={code} "
                    f"role_name={name!r} mission={mission!r}"
                )
                cur.execute(
                    """
                    SELECT resp_id, category, seq, content, created_at
                    FROM dept_responsibility
                    WHERE role_id = %s
                    ORDER BY category, seq, created_at
                    """,
                    (role_id,),
                )
                items = cur.fetchall()
                if not items:
                    print("  (이 부서에는 dept_responsibility 항목이 없습니다.)")
                for resp_id, category, seq, content, created_at in items:
                    print(
                        f"  - resp_id={resp_id} 구분={category} 순번={seq} "
                        f"내용={content!r} 등록시각={created_at}"
                    )

            # org_chart_role에 (org_chart_id, dept_code) 유니크 제약이 있는지도 같이 확인
            cur.execute(
                """
                SELECT conname, pg_get_constraintdef(oid)
                FROM pg_constraint
                WHERE conrelid = 'org_chart_role'::regclass AND contype IN ('u', 'p')
                """
            )
            print("\n=== org_chart_role의 UNIQUE/PK 제약 ===")
            for conname, condef in cur.fetchall():
                print(f"  {conname}: {condef}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
