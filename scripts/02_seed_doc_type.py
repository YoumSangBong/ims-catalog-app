"""
2단계: doc_type 마스터 시드 적재 (form_pattern 4건 + doc_type 66건: manual 1 + procedure 52 + guideline 13).
반드시 01_init_schema.py 를 먼저 실행한 뒤에 실행하세요.

실행: python scripts/02_seed_doc_type.py
"""
from pathlib import Path

from db import get_conn

SEED_FILE = Path(__file__).resolve().parent.parent / "schema" / "dify_doc_type_seed.sql"


def main():
    sql = SEED_FILE.read_text(encoding="utf-8")
    print(f"{SEED_FILE.name} 실행 중 (form_pattern 4건 + doc_type 66건)...")

    conn = get_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(sql)
        print("doc_type 시드 적재 완료.")
    except Exception as e:
        conn.rollback()
        msg = str(e)
        if "duplicate key" in msg:
            print("이미 적재되어 있는 것으로 보입니다(중복 키 오류). 다시 실행할 필요 없습니다.")
        else:
            print("오류 발생:", e)
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
