"""
1단계: 스키마 실행 (30개 테이블 생성 + standard 3건 INSERT).
ims_docs 데이터베이스가 비어있는 상태를 전제로 합니다 — 이미 테이블이 있으면
'already exists' 오류가 나는데, 그건 정상입니다(이미 실행했다는 뜻).

실행: python scripts/01_init_schema.py
"""
from pathlib import Path

from db import get_conn

SCHEMA_FILE = Path(__file__).resolve().parent.parent / "schema" / "dify_platform_schema.sql"


def main():
    sql = SCHEMA_FILE.read_text(encoding="utf-8")
    print(f"{SCHEMA_FILE.name} 실행 중 (30개 테이블 + standard 3건)...")

    conn = get_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(sql)
        print("스키마 생성 완료.")
    except Exception as e:
        conn.rollback()
        msg = str(e)
        if "already exists" in msg:
            print("일부 테이블이 이미 존재합니다 (이전에 이미 실행한 것으로 보입니다).")
            print("전체를 다시 만들려면 DBeaver에서 public 스키마를 DROP 후 재실행하세요:")
            print("  DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        else:
            print("오류 발생:", e)
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
