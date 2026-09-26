"""
7단계(진단용): 06_migrate_org_rr.py가 응답 없이 멈출 때, 어떤 세션이 org_chart/
org_chart_role/application 테이블에 잠금을 걸고 있는지 확인한다.

06_migrate_org_rr.py가 실행 중(또는 멈춘 상태)인 터미널은 그대로 두고,
"새 터미널"을 열어서 이 스크립트를 실행하세요.

실행: python scripts/07_check_locks.py

목록에 나온 항목 중 "내가 다른 데서 열어둔 걸로 아는" pid가 있으면,
아래 "종료(kill)" 프롬프트에 그 pid를 입력하면 해당 세션을 강제 종료합니다.
(내가 지금 이 스크립트로 실행 중인 연결은 제외하고 표시합니다.)
"""
from db import get_conn


def main():
    conn = get_conn()
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    a.pid,
                    a.usename,
                    a.application_name,
                    a.state,
                    a.query_start,
                    now() - a.query_start AS elapsed,
                    left(a.query, 120) AS query,
                    c.relname AS locked_table,
                    l.mode,
                    l.granted
                FROM pg_locks l
                JOIN pg_stat_activity a ON a.pid = l.pid
                JOIN pg_class c ON c.oid = l.relation
                WHERE c.relname IN ('org_chart', 'org_chart_role', 'application',
                                     'dept_responsibility', 'org_rr_approval_log',
                                     'responsibility_matrix')
                  AND a.pid <> pg_backend_pid()
                ORDER BY a.query_start
                """
            )
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description]

        if not rows:
            print("현재 org_chart/application 관련 테이블에 걸린 잠금이 없습니다.")
            print("→ 그렇다면 원인은 잠금이 아닐 수 있습니다. 06_migrate_org_rr.py가 정말 멈춘 게 맞는지,")
            print("  1~2분 더 기다려도 반응이 없는지 다시 확인해주세요.")
            return

        print(f"{len(rows)}건의 잠금/대기 세션이 발견되었습니다:\n")
        for row in rows:
            d = dict(zip(cols, row))
            granted = "확보함(GRANTED)" if d["granted"] else "대기중(WAITING)"
            print(
                f"- pid={d['pid']} | user={d['usename']} | app={d['application_name']} | "
                f"state={d['state']} | table={d['locked_table']} | mode={d['mode']} | {granted}\n"
                f"  경과시간={d['elapsed']} | query={d['query']!r}"
            )

        print(
            "\n'granted' 상태이면서 state가 'idle in transaction'인 pid가 있으면 그게 범인일 "
            "가능성이 큽니다(트랜잭션을 커밋/롤백하지 않고 방치된 세션)."
        )
        target = input("\n강제 종료할 pid를 입력하세요 (그냥 Enter면 종료하지 않고 끝냄): ").strip()
        if target:
            with conn.cursor() as cur:
                cur.execute("SELECT pg_terminate_backend(%s)", (int(target),))
                print(f"pid {target} 세션을 종료했습니다. 06_migrate_org_rr.py를 다시 실행해보세요.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
