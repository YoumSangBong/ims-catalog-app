"""
0단계: DB 접속 테스트.
가장 먼저 이 스크립트부터 실행해서 .env 설정이 맞는지 확인하세요.

실행: python scripts/00_test_connection.py
"""
from db import get_conn


def main():
    print("Cloud SQL(ims-doc-instance) 접속을 시도합니다...")
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT version();")
            (version,) = cur.fetchone()
            cur.execute("SELECT current_database();")
            (dbname,) = cur.fetchone()
        print("접속 성공!")
        print(f"  - 데이터베이스: {dbname}")
        print(f"  - 서버 버전: {version}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
