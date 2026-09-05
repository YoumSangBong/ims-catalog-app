"""
4단계: 적재 결과 검증 — 30개 테이블 존재 여부 + 주요 테이블 행 수 확인.

실행: python scripts/04_verify.py
"""
from db import get_conn

EXPECTED_TABLES = [
    "standard", "sector_main", "iaf_group", "company", "sector_profile",
    "form_pattern", "doc_type", "sample_project_analysis", "sample_doc_classification",
    "org_chart", "org_chart_role", "application", "conversion_project",
    "process_step", "process_step_io", "process_step_activity", "process_dependency",
    "term_dictionary", "process_term_usage", "responsibility_matrix", "guideline_item",
    "form_template", "form_field", "document_individual", "document_content",
    "document_integrated", "document_revision_log", "hwp_render_job",
    "legacy_source_document", "legacy_split_mapping",
]

ROW_COUNT_TABLES = ["standard", "sector_main", "iaf_group", "sector_profile", "form_pattern", "doc_type"]


def main():
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
            )
            existing = {r[0] for r in cur.fetchall()}

            print(f"테이블 {len(existing)}/{len(EXPECTED_TABLES)}개 존재")
            missing = [t for t in EXPECTED_TABLES if t not in existing]
            if missing:
                print("누락된 테이블:", ", ".join(missing))
            else:
                print("30개 테이블 전부 확인됨.")

            print()
            print("주요 테이블 행 수:")
            for t in ROW_COUNT_TABLES:
                if t in existing:
                    cur.execute(f"SELECT count(*) FROM {t}")
                    (cnt,) = cur.fetchone()
                    print(f"  - {t}: {cnt}건")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
