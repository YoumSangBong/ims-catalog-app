"""
11_migrate_standard_editions.py
경영시스템문서 플랫폼 — 규격 개정판(예: ISO 9001/14001 2026년판) 지원 마이그레이션

이 스크립트가 반영하는 내용(2026-09-18 협의 확정):
  1) standard: 규격별로 여러 개정판을 등록할 수 있도록 컬럼 추가
     - edition_label(표시용, 예 "2015년판"/"2026년판")
     - valid_from / valid_until(유효기간 — 만료되면 신규 등록 시 선택 불가)
     - is_current_default(신규 등록 폼 기본 선택 여부)
     - sort_order(조합 코드 생성 순서 — 기존 q=10,e=20,hs=30, 새 규격은 그보다
       작은 값을 받아 조합 코드에서 항상 앞에 옴)
     - is_active(소프트 비활성화 — 참조무결성 때문에 하드 삭제는 지원하지 않음)
     기존 q/e/hs 3행은 is_active=true, is_current_default=true, sort_order=10/20/30으로 채움.
  2) application:
     - std_code_normalized 폭을 varchar(4) -> varchar(40)으로 확장
       (신규 규격이 계속 추가되면 조합 코드 길이가 늘어날 수 있음)
     - superseded_application_id 컬럼 추가(bigint, application 자기참조 FK) —
       "규격 개정은 기존 프로젝트 수정이 아니라 새 프로젝트 등록"이라는 워크플로우를
       지원하기 위해, 새로 등록된 개정판 프로젝트가 어느 기존 프로젝트를 대체하는지
       추적한다.
  3) doc_type:
     - clause_ref_overrides 컬럼 추가(jsonb, 기본 NULL) — 개정판마다 조항번호가
       다르거나(예: 9001 2026년판의 6.1.3 신설) 아예 없어진 경우(예: 14001 2026년판의
       6.1.1 소멸)를 표현. 형식: {"Q": "6.1.3"} 처럼 std_code -> 그 개정판에서의
       조항번호(문자열), 조항 자체가 없어졌으면 값을 null로 저장.

멱등성: 이미 적용된 항목은 건너뛰고 안내만 출력합니다 — 재실행해도 안전합니다.

사용법: (scripts 폴더 안에서, 가상환경 활성화 후)
    python 11_migrate_standard_editions.py
"""
from db import get_conn


def column_exists(cur, table, column):
    cur.execute(
        "SELECT 1 FROM information_schema.columns WHERE table_name=%s AND column_name=%s",
        (table, column),
    )
    return cur.fetchone() is not None


def constraint_exists(cur, table, constraint_name):
    cur.execute(
        "SELECT 1 FROM information_schema.table_constraints "
        "WHERE table_name=%s AND constraint_name=%s",
        (table, constraint_name),
    )
    return cur.fetchone() is not None


def step1_standard_edition_columns(cur):
    added = []
    if not column_exists(cur, "standard", "edition_label"):
        cur.execute("ALTER TABLE standard ADD COLUMN edition_label varchar(30)")
        added.append("edition_label")
    if not column_exists(cur, "standard", "valid_from"):
        cur.execute("ALTER TABLE standard ADD COLUMN valid_from date")
        added.append("valid_from")
    if not column_exists(cur, "standard", "valid_until"):
        cur.execute("ALTER TABLE standard ADD COLUMN valid_until date")
        added.append("valid_until")
    if not column_exists(cur, "standard", "is_current_default"):
        cur.execute(
            "ALTER TABLE standard ADD COLUMN is_current_default boolean NOT NULL DEFAULT false"
        )
        added.append("is_current_default")
    if not column_exists(cur, "standard", "sort_order"):
        cur.execute("ALTER TABLE standard ADD COLUMN sort_order integer NOT NULL DEFAULT 100")
        added.append("sort_order")
    if not column_exists(cur, "standard", "is_active"):
        cur.execute("ALTER TABLE standard ADD COLUMN is_active boolean NOT NULL DEFAULT true")
        added.append("is_active")

    if added:
        print(f"[1] standard 컬럼 추가: {', '.join(added)}")
    else:
        print("[1] standard 개정판 관련 컬럼 이미 있음 — 건너뜀")

    # 기존 q/e/hs 3행 기본값 시드(이미 값이 들어있으면 건드리지 않음 — sort_order
    # 기본값 100인 행만 대상으로 해서 재실행해도 안전)
    cur.execute(
        """
        UPDATE standard SET sort_order = 10, is_current_default = true,
               edition_label = COALESCE(edition_label, '2015년판')
        WHERE std_code = 'q' AND sort_order = 100
        """
    )
    cur.execute(
        """
        UPDATE standard SET sort_order = 20, is_current_default = true,
               edition_label = COALESCE(edition_label, '2015년판')
        WHERE std_code = 'e' AND sort_order = 100
        """
    )
    cur.execute(
        """
        UPDATE standard SET sort_order = 30, is_current_default = true,
               edition_label = COALESCE(edition_label, '2018년판')
        WHERE std_code = 'hs' AND sort_order = 100
        """
    )
    print("[1] 기존 q/e/hs sort_order·edition_label 기본 시드 완료(이미 채워진 행은 유지)")


def step2_application_columns(cur):
    cur.execute(
        "SELECT character_maximum_length FROM information_schema.columns "
        "WHERE table_name='application' AND column_name='std_code_normalized'"
    )
    row = cur.fetchone()
    if row and row[0] and row[0] < 40:
        cur.execute("ALTER TABLE application ALTER COLUMN std_code_normalized TYPE varchar(40)")
        print("[2] application.std_code_normalized 폭을 varchar(40)으로 확장 완료")
    else:
        print("[2] application.std_code_normalized 이미 충분히 넓음 — 건너뜀")

    if column_exists(cur, "application", "superseded_application_id"):
        print("[2] application.superseded_application_id 이미 있음 — 건너뜀")
        return
    cur.execute(
        "ALTER TABLE application ADD COLUMN superseded_application_id bigint "
        "REFERENCES application(application_id)"
    )
    print("[2] application.superseded_application_id 컬럼 추가 완료")


def step3_doc_type_clause_overrides(cur):
    if column_exists(cur, "doc_type", "clause_ref_overrides"):
        print("[3] doc_type.clause_ref_overrides 이미 있음 — 건너뜀")
        return
    cur.execute("ALTER TABLE doc_type ADD COLUMN clause_ref_overrides jsonb")
    print("[3] doc_type.clause_ref_overrides 컬럼 추가 완료")


def main():
    conn = get_conn()
    conn.autocommit = False
    with conn:
        with conn.cursor() as cur:
            step1_standard_edition_columns(cur)
            step2_application_columns(cur)
            step3_doc_type_clause_overrides(cur)
    print("완료.")


if __name__ == "__main__":
    main()
