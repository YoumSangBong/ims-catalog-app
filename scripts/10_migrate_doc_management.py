"""
10_migrate_doc_management.py
경영시스템문서 플랫폼 — 4순위 최종단계("문서관리") 스키마 마이그레이션

이 스크립트가 반영하는 내용(2026-09-13 협의 확정, 1~7번):
  1) document_content: content_text 제거, format/storage_path 추가
     (내용본을 완성본과 동일한 "파일 관리" 방식으로 전환)
  2) document_integrated: status 컬럼 추가 (실제 물리 병합까지 하므로 진행상태 추적 필요)
  3) legacy_source_document: application_id 컬럼 추가 (상시 "문서분리" 기능 지원)
  4) sample_original 마스터 테이블 신설 — application.sample_original(자유텍스트)을
     application.original_no(FK, 번호)로 전환. 기존 값은 새 테이블로 이관 후 매칭.
  5) document_individual: form_seq_no 컬럼 추가
     (마스터 doc_code와 별개로, 신청건별 양식 일련번호 — "분류문서 보기"의
      "doc_code(양식번호)" 컬럼에 대응)
  6) document_individual: UNIQUE(application_id, doc_type_id) 추가
     ("문서관리" 화면 업로드가 UPSERT로 동작 — 개정은 UPDATE, 이력은 document_revision_log)
  7) document_content: UNIQUE(doc_id) 추가 (내용본도 동일하게 UPSERT)

멱등성: 이미 적용된 항목은 건너뛰고 안내만 출력합니다 — 재실행해도 안전합니다.
실행 전 DB 백업을 권장합니다(특히 document_content.content_text를 실제로 쓰고
계셨다면, 이 스크립트가 그 컬럼을 삭제하기 전에 값이 있는지 알려줍니다).

사용법: (scripts 폴더 안에서, 가상환경 활성화 후)
    python 10_migrate_doc_management.py
"""
from db import get_conn

# 2026-09-12 "Original 현황" 시트에서 확정한 9개 값(번호 1~9, 순서 그대로 시드)
SAMPLE_ORIGINAL_SEED = [
    "예스폼_ISO안전보건경영시스템패키지<건설업>ISO45001-2018",
    "예스폼_ISO안전보건경영시스템패키지<제조업>ISO45001-2018",
    "예스폼_ISO표준문서패키지<유통업>ISO9001,ISO14001-2015",
    "예스폼_ISO표준문서패키지ISO9001,ISO14001-2015",
    "예스폼_ISO표준문서패키지<건설업>ISO9001,ISO14001-2015",
    "예스폼_ISO표준문서패키지<서비스업>ISO9001-2008",
    "품질환경안전경영통합.zip-20221202123347(크몽품질관리실무자)",
    "ISO+45001+2018+(2).zip-20221202195207(크몽)",
    "[ hwp,36종지침절차,A형 ] ISO9001 품질경영시스템 절차서 (166)",
]


def column_exists(cur, table, column):
    cur.execute(
        "SELECT 1 FROM information_schema.columns WHERE table_name=%s AND column_name=%s",
        (table, column),
    )
    return cur.fetchone() is not None


def table_exists(cur, table):
    cur.execute("SELECT to_regclass(%s)", (table,))
    return cur.fetchone()[0] is not None


def step1_document_content(cur):
    if column_exists(cur, "document_content", "content_text"):
        cur.execute("SELECT count(*) FROM document_content WHERE content_text IS NOT NULL")
        n = cur.fetchone()[0]
        if n:
            print(f"  [경고] document_content.content_text에 값이 {n}건 있습니다 — "
                  "삭제 전에 필요하면 별도로 백업하세요(이 스크립트는 그대로 삭제합니다).")
        cur.execute("ALTER TABLE document_content DROP COLUMN content_text")
        print("[1] document_content.content_text 제거 완료")
    else:
        print("[1] document_content.content_text 이미 제거됨 — 건너뜀")

    if not column_exists(cur, "document_content", "format"):
        cur.execute("ALTER TABLE document_content ADD COLUMN format varchar(10) NOT NULL DEFAULT 'hwp'")
        print("[1] document_content.format 추가 완료")
    else:
        print("[1] document_content.format 이미 있음 — 건너뜀")

    if not column_exists(cur, "document_content", "storage_path"):
        cur.execute("ALTER TABLE document_content ADD COLUMN storage_path varchar(500)")
        print("[1] document_content.storage_path 추가 완료")
    else:
        print("[1] document_content.storage_path 이미 있음 — 건너뜀")


def step2_document_integrated(cur):
    if not column_exists(cur, "document_integrated", "status"):
        cur.execute(
            "ALTER TABLE document_integrated ADD COLUMN status varchar(20) NOT NULL DEFAULT 'draft'"
        )
        print("[2] document_integrated.status 추가 완료")
    else:
        print("[2] document_integrated.status 이미 있음 — 건너뜀")


def step3_legacy_source_document(cur):
    if not column_exists(cur, "legacy_source_document", "application_id"):
        cur.execute(
            "ALTER TABLE legacy_source_document ADD COLUMN application_id "
            "bigint REFERENCES application(application_id)"
        )
        print("[3] legacy_source_document.application_id 추가 완료")
    else:
        print("[3] legacy_source_document.application_id 이미 있음 — 건너뜀")


def step4_sample_original(cur):
    if not table_exists(cur, "sample_original"):
        cur.execute(
            """
            CREATE TABLE sample_original (
                original_no    smallserial PRIMARY KEY,
                original_name  varchar(300) NOT NULL UNIQUE
            )
            """
        )
        print("[4] sample_original 테이블 생성 완료")
    else:
        print("[4] sample_original 테이블 이미 있음 — 건너뜀")

    cur.execute("SELECT count(*) FROM sample_original")
    if cur.fetchone()[0] == 0:
        for name in SAMPLE_ORIGINAL_SEED:
            cur.execute(
                "INSERT INTO sample_original (original_name) VALUES (%s) "
                "ON CONFLICT (original_name) DO NOTHING",
                (name,),
            )
        print(f"[4] sample_original 시드 {len(SAMPLE_ORIGINAL_SEED)}건 삽입 완료")
    else:
        print("[4] sample_original에 이미 데이터가 있음 — 시드 삽입 건너뜀")

    if not column_exists(cur, "application", "original_no"):
        cur.execute(
            "ALTER TABLE application ADD COLUMN original_no "
            "smallint REFERENCES sample_original(original_no)"
        )
        print("[4] application.original_no 컬럼 추가 완료")

        if column_exists(cur, "application", "sample_original"):
            cur.execute(
                "SELECT DISTINCT sample_original FROM application "
                "WHERE sample_original IS NOT NULL AND sample_original != ''"
            )
            existing_texts = [r[0] for r in cur.fetchall()]
            migrated, newly_added = 0, 0
            for text in existing_texts:
                cur.execute("SELECT original_no FROM sample_original WHERE original_name = %s", (text,))
                row = cur.fetchone()
                if row is None:
                    cur.execute(
                        "INSERT INTO sample_original (original_name) VALUES (%s) RETURNING original_no",
                        (text,),
                    )
                    row = cur.fetchone()
                    newly_added += 1
                cur.execute(
                    "UPDATE application SET original_no = %s WHERE sample_original = %s",
                    (row[0], text),
                )
                migrated += 1
            if migrated:
                print(f"[4] 기존 application.sample_original 값 {migrated}종을 번호로 매칭 완료"
                      + (f" (시드 9건에 없어 새로 추가된 값 {newly_added}건)" if newly_added else ""))
            else:
                print("[4] 기존 application.sample_original에 이관할 값 없음")
    else:
        print("[4] application.original_no 이미 있음 — 건너뜀")

    if column_exists(cur, "application", "sample_original"):
        cur.execute("ALTER TABLE application DROP COLUMN sample_original")
        print("[4] application.sample_original(옛 자유텍스트 컬럼) 제거 완료")
    else:
        print("[4] application.sample_original 이미 제거됨 — 건너뜀")


def step5_form_seq_no(cur):
    if not column_exists(cur, "document_individual", "form_seq_no"):
        cur.execute("ALTER TABLE document_individual ADD COLUMN form_seq_no varchar(20)")
        print("[5] document_individual.form_seq_no 추가 완료 "
              "(category='form' 문서에서만 사용 — 신청건별 양식 일련번호)")
    else:
        print("[5] document_individual.form_seq_no 이미 있음 — 건너뜀")


def constraint_exists(cur, table, constraint_name):
    cur.execute(
        "SELECT 1 FROM information_schema.table_constraints "
        "WHERE table_name=%s AND constraint_name=%s",
        (table, constraint_name),
    )
    return cur.fetchone() is not None


def step6_document_individual_unique(cur):
    """document_individual: (application_id, doc_type_id)당 1행만 유지(개정은 UPDATE로 반영,
    이력은 document_revision_log에 별도 기록) — "문서관리" 화면의 업로드/개정 UPSERT 로직 전제조건."""
    cname = "document_individual_app_doctype_uniq"
    if constraint_exists(cur, "document_individual", cname):
        print("[6] document_individual UNIQUE(application_id, doc_type_id) 이미 있음 — 건너뜀")
        return
    cur.execute(
        """
        SELECT application_id, doc_type_id, count(*)
        FROM document_individual
        WHERE application_id IS NOT NULL AND doc_type_id IS NOT NULL
        GROUP BY application_id, doc_type_id
        HAVING count(*) > 1
        """
    )
    dups = cur.fetchall()
    if dups:
        print(f"  [경고] document_individual에 (application_id, doc_type_id) 중복이 {len(dups)}건 있어 "
              "UNIQUE 제약을 건너뜁니다 — 먼저 중복 행을 정리한 뒤 이 스크립트를 다시 실행해주세요.")
        for row in dups[:10]:
            print(f"    application_id={row[0]}, doc_type_id={row[1]}, 중복행수={row[2]}")
        return
    cur.execute(
        f"ALTER TABLE document_individual ADD CONSTRAINT {cname} "
        "UNIQUE (application_id, doc_type_id)"
    )
    print("[6] document_individual UNIQUE(application_id, doc_type_id) 추가 완료")


def step7_document_content_unique(cur):
    """document_content: doc_id당 1행(내용본도 완성본과 동일하게 개정은 UPDATE로 갱신)."""
    cname = "document_content_doc_id_uniq"
    if constraint_exists(cur, "document_content", cname):
        print("[7] document_content UNIQUE(doc_id) 이미 있음 — 건너뜀")
        return
    cur.execute(
        "SELECT doc_id, count(*) FROM document_content "
        "WHERE doc_id IS NOT NULL GROUP BY doc_id HAVING count(*) > 1"
    )
    dups = cur.fetchall()
    if dups:
        print(f"  [경고] document_content에 doc_id 중복이 {len(dups)}건 있어 "
              "UNIQUE 제약을 건너뜁니다 — 먼저 중복 행을 정리한 뒤 다시 실행해주세요.")
        return
    cur.execute(f"ALTER TABLE document_content ADD CONSTRAINT {cname} UNIQUE (doc_id)")
    print("[7] document_content UNIQUE(doc_id) 추가 완료")


def main():
    conn = get_conn()
    conn.autocommit = False
    with conn:
        with conn.cursor() as cur:
            step1_document_content(cur)
            step2_document_integrated(cur)
            step3_legacy_source_document(cur)
            step4_sample_original(cur)
            step5_form_seq_no(cur)
            step6_document_individual_unique(cur)
            step7_document_content_unique(cur)
    print("\n모든 마이그레이션 적용 완료.")


if __name__ == "__main__":
    main()
