"""
5-1단계(선택): company.biz_reg_no 중복 정리 — 05번 마이그레이션이 "중복값 있어 건너뜀" 경고를
낸 경우에만 실행하세요. 같은 사업자등록번호로 여러 번 등록된 company 행을 가장 먼저 만들어진
1건으로 합칩니다(데이터 삭제 아님 — application/org_chart/sector_profile의 연결만 그 1건으로
옮긴 뒤, 남은 중복 company 행만 지웁니다).

실행: python scripts/06_cleanup_dup_company.py
실행 후 다시: python scripts/05_migrate_review1_6.py  (UNIQUE 제약이 마저 걸립니다)
"""
from db import get_conn


def main():
    conn = get_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT biz_reg_no, array_agg(company_id ORDER BY company_id) AS ids
                    FROM company
                    WHERE biz_reg_no IS NOT NULL
                    GROUP BY biz_reg_no
                    HAVING count(*) > 1
                    """
                )
                groups = cur.fetchall()
                if not groups:
                    print("중복된 biz_reg_no가 없습니다. 정리할 게 없어요.")
                    return

                for biz_reg_no, ids in groups:
                    keep_id = ids[0]
                    dup_ids = ids[1:]
                    print(f"\n[{biz_reg_no}] company_id {ids} 중 {keep_id}번으로 통합, {dup_ids} 삭제 예정")

                    cur.execute(
                        "UPDATE application SET company_id = %s WHERE company_id = ANY(%s)",
                        (keep_id, dup_ids),
                    )
                    print(f"  - application {cur.rowcount}건 company_id를 {keep_id}로 이동")

                    cur.execute(
                        "UPDATE org_chart SET source_company_id = %s WHERE source_company_id = ANY(%s)",
                        (keep_id, dup_ids),
                    )
                    print(f"  - org_chart {cur.rowcount}건 source_company_id를 {keep_id}로 이동")

                    cur.execute(
                        "UPDATE sector_profile SET created_by_company_id = %s WHERE created_by_company_id = ANY(%s)",
                        (keep_id, dup_ids),
                    )
                    print(f"  - sector_profile {cur.rowcount}건 created_by_company_id를 {keep_id}로 이동")

                    cur.execute("DELETE FROM company WHERE company_id = ANY(%s)", (dup_ids,))
                    print(f"  - company 중복 {cur.rowcount}건 삭제 완료")

        print("\n중복 정리 완료. 이제 다시 실행하세요: python 05_migrate_review1_6.py")
    except Exception as e:
        conn.rollback()
        print("오류 발생:", e)
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()