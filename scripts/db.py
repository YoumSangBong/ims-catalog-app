"""
공용 DB 연결 헬퍼.
.env 파일(프로젝트 루트)에서 접속정보를 읽어 psycopg2 커넥션을 만든다.
"""
import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

REQUIRED_VARS = ["DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD"]


def get_conn():
    missing = [v for v in REQUIRED_VARS if not os.environ.get(v)]
    if missing:
        raise RuntimeError(
            f".env 파일에 다음 값이 없습니다: {', '.join(missing)}. "
            f".env.example을 복사해서 .env로 만들고 값을 채워주세요."
        )
    return psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=os.environ.get("DB_PORT", "5432"),
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        sslmode=os.environ.get("DB_SSLMODE", "prefer"),
        connect_timeout=10,
    )
