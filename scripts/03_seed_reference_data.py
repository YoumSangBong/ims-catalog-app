"""
3단계: 기준정보 적재 — sector_main(6건) + iaf_group(39건) + sector_profile(IAF_sector_profile.csv, 562건).
반드시 01_init_schema.py 를 먼저 실행한 뒤에 실행하세요 (doc_type 시드와는 순서 무관).

sector_main / iaf_group 값은 Dify Code 노드(dify_sector_code_parser.py)의
MAIN_SECTOR / IAF_GROUP 딕셔너리를 그대로 옮긴 것이라 CSV와 별개로 항상 완전한
6건 / 39건이 들어간다.

실행: python scripts/03_seed_reference_data.py
"""
import csv
import json
from pathlib import Path

from db import get_conn

CSV_FILE = Path(__file__).resolve().parent.parent / "data" / "IAF_sector_profile.csv"

# Dify Code 노드(dify_sector_code_parser.py)와 동일한 값 — 대분류(6개)
MAIN_SECTOR = {
    "M": "제조업",
    "U": "유틸리티",
    "C": "건설업",
    "S": "서비스업",
    "I": "정보기술(IT)",
    "E": "교육·공공·금융",
}

# 동일 소스 — IAF 그룹명(39개, 번호는 2자리로 zero-pad)
IAF_GROUP = {
    "01": "농업·사냥·임업 및 어업", "02": "채광 및 채석", "03": "식품·음료 및 담배 제조",
    "04": "직물 및 직물 제품", "05": "가죽 및 가죽 제품", "06": "목재 및 나무 제품",
    "07": "펄프 및 종이 제품", "08": "출판업", "09": "인쇄업",
    "10": "코크스 및 석유 정제품", "11": "핵 원료", "12": "화학물과 화학물 제품의 제조",
    "13": "약품", "14": "고무 및 플라스틱 제품", "15": "비금속 광물 제품",
    "16": "콘크리트·시멘트·석회·석고", "17": "기초금속 및 조립금속 제품", "18": "기계 및 장비",
    "19": "컴퓨터·전기장비·전자광학기기 제조", "20": "선박 제조", "21": "항공",
    "22": "기타 수송장비", "23": "기타 명시되지 않은 제조", "24": "재활용",
    "25": "전기공급", "26": "가스공급", "27": "수도공급",
    "28": "건설", "29": "도소매", "30": "숙박 및 음식점",
    "31": "운송·창고", "32": "금융·부동산·임대", "33": "정보기술",
    "34": "엔지니어링 서비스", "35": "기타 서비스 (시설보수·인력파견 등)", "36": "공공행정",
    "37": "교육", "38": "보건 및 사회복지", "39": "기타 사회 서비스",
}


def split_list(value: str) -> list:
    """CSV의 '항목1 / 항목2 / 항목3' 형태를 리스트로 분리. 빈 값이면 빈 리스트."""
    value = (value or "").strip()
    if not value:
        return []
    return [part.strip() for part in value.split("/") if part.strip()]


def main():
    with open(CSV_FILE, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    print(f"{CSV_FILE.name}: {len(rows)}행 로드")

    conn = get_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                # 1) sector_main (6건)
                for code, name in MAIN_SECTOR.items():
                    cur.execute(
                        "INSERT INTO sector_main (code, name) VALUES (%s, %s) "
                        "ON CONFLICT (code) DO NOTHING",
                        (code, name),
                    )

                # 2) iaf_group (39건)
                for num, name in IAF_GROUP.items():
                    cur.execute(
                        "INSERT INTO iaf_group (iaf_num, name) VALUES (%s, %s) "
                        "ON CONFLICT (iaf_num) DO NOTHING",
                        (num, name),
                    )

                # 3) sector_profile (562건)
                inserted = 0
                for row in rows:
                    iaf_num = row["IAF번호"].strip().zfill(2)
                    cur.execute(
                        """
                        INSERT INTO sector_profile (
                            sector_code, profile_seq, sector_main, iaf_num,
                            sector_detail, sector_name, is_default,
                            hazards, env_aspects, quality_chars,
                            key_laws_sh, key_laws_env, process_hints,
                            source_type
                        ) VALUES (
                            %s, %s, %s, %s,
                            %s, %s, %s,
                            %s, %s, %s,
                            %s, %s, %s,
                            %s
                        )
                        ON CONFLICT (sector_code, profile_seq) DO NOTHING
                        """,
                        (
                            row["업종코드"].strip(),
                            int(row["profile_seq"]),
                            row["대분류"].strip(),
                            iaf_num,
                            row["세분류"].strip(),
                            row["업종명"].strip(),
                            row["is_default"].strip().upper() == "Y",
                            json.dumps(split_list(row["위험성형태"]), ensure_ascii=False),
                            json.dumps(split_list(row["환경측면"]), ensure_ascii=False),
                            json.dumps(split_list(row["품질특성"]), ensure_ascii=False),
                            json.dumps(split_list(row["안전보건법령"]), ensure_ascii=False),
                            json.dumps(split_list(row["환경법령"]), ensure_ascii=False),
                            json.dumps(split_list(row["공정구조"]), ensure_ascii=False),
                            "iaf_csv",
                        ),
                    )
                    inserted += cur.rowcount

        print(f"sector_main 6건 / iaf_group 39건 적재 완료.")
        print(f"sector_profile: {inserted}건 신규 적재 (전체 {len(rows)}행 중 — 이미 있던 행은 건너뜀).")
    except Exception as e:
        conn.rollback()
        print("오류 발생:", e)
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
