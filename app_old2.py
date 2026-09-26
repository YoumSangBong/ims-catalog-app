"""
경영시스템문서 플랫폼 — Streamlit 앱. (4순위 최종단계 "문서관리" 반영, 2026-09-13)

3개 화면:
  1) 기준정보 조회 — standard / sector_main / iaf_group / sector_profile / doc_type /
     form_pattern / sample_original(Original 현황)
  2) 사용자 관리 — 사용자 등록(회사·샘플 통합) / 조직 책임과 권한
  3) 문서관리 — "문서관리"(신청건별 현황 + ⬆일괄 업로드/⬇일괄 다운로드/✂문서분리/
     🔗문서통합/개별 문서 처리(예외용)) / "분류문서 보기"(문서종류 하나를 기준으로
     전체 신청건 현황, 매뉴얼·양식대장 성격)
     (문서분리는 2026-09-13 한 번 제거했다가, 같은 날 6차에서 "분리기준표 자동
     생성" 방식으로 재도입 — 사용자가 xlsx를 직접 준비할 필요 없이, 이 신청건에
     이미 등록된 문서 목록에서 기준표를 자동으로 만들어 분리한다. hwp_split.py
     참고)

실행: (scripts 폴더에서 00~10을 먼저 실행해 DB가 준비된 상태에서)
    streamlit run app.py
"""
import io
import json
import os
import re
import sys
import tempfile
import zipfile
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine
from sqlalchemy.engine import URL

sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))
from db import get_conn  # noqa: E402
from storage_paths import (  # noqa: E402
    CATEGORY_LABELS,
    build_integrated_path,
    build_storage_path,
    category_for_doc_type,
)
import gcs_storage  # noqa: E402
import hwp_merge  # noqa: E402
import hwp_split  # noqa: E402

st.set_page_config(page_title="경영시스템문서 플랫폼", layout="wide")

# 규격 선택 (2026-09-18부터: 하드코딩된 7개 조합 대신 standard 테이블에서 동적으로
# 읽어와 다중선택하는 방식으로 전환 — 규격이 늘어나거나 개정판(예: ISO 9001/14001
# 2026년판)이 추가돼도 코드 수정 없이 데이터 추가만으로 대응 가능. _fetch_active_
# standards()/build_std_combo() 참고.

# 직원수 규모 6단계 (수정검토1.6, 기존 micro/small/medium/large 대체)
ORG_SCALE_OPTIONS = ["10인미만", "10~49인", "50~99인", "100~299인", "300~999인", "1000인 이상"]

# 조직 마스터 DB(dept_master) 대분류 13종 (수정검토2.5) — dept_code = {대분류: 한글 약칭}
# {중분류: 영문 소문자 1자}{세분류: 숫자 1자}. 예: 품질a1, 품질a2, 회계a1.
# 화면에서 새 부서명을 직접 등록하면 중분류를 'z'로 고정해 자동 채번(예: 품질z1)한다.
# dept_code 자체는 가나다순이 아니라서, 표준 표시순서는 dept_code가 아니라 dept_master의
# category_seq 컬럼(아래 순서대로 10,20,30...)을 기준으로 정렬한다 — 사용자 확정 순서:
# 인사/회계/총무 → 경영/기획/관리 → 영업/구매/생산 → 품질/환경/안전보건 → 연구개발.
DEPT_CATEGORY_LIST = [
    ("인사", "인사", 10), ("회계", "회계", 20), ("총무", "총무", 30),
    ("경영", "경영", 40), ("기획", "기획", 50), ("관리", "경영관리", 60),
    ("영업", "영업", 70), ("구매", "구매", 80), ("생산", "생산", 90),
    ("품질", "품질", 100), ("환경", "환경", 110), ("안전보건", "안전보건", 120),
    ("연구", "연구개발", 130),
]
DEPT_CATEGORY_NAME = {c: n for c, n, _ in DEPT_CATEGORY_LIST}
DEPT_CATEGORY_SEQ = {c: s for c, n, s in DEPT_CATEGORY_LIST}
NEW_DEPT_SENTINEL = "__NEW__"
NEW_ORIGINAL_SENTINEL = "__NEW_ORIGINAL__"


# ---------- 공용 헬퍼 ----------

@st.cache_resource
def _engine_conn():
    """페이지 전환 시마다 새로 연결하지 않도록 커넥션을 캐시.
    autocommit=True — SELECT 후 커밋을 안 하면 이 캐시된 커넥션이 앱이 켜져있는
    내내 idle in transaction 상태로 테이블 잠금을 쥐고 있어(예: ALTER TABLE이 무기한
    대기하게 됨) 반드시 켜야 한다. 마이그레이션 스크립트(scripts/*.py)는 이 함수를
    쓰지 않고 db.get_conn()을 직접 호출하므로 영향 없음(그쪽은 명시적 트랜잭션 유지)."""
    conn = get_conn()
    conn.autocommit = True
    return conn


@st.cache_resource
def _read_engine():
    """pd.read_sql 전용 SQLAlchemy 엔진.
    pd.read_sql에 psycopg2 raw connection을 바로 넘기면 pandas가
    'only supports SQLAlchemy connectable...' 경고를 낸다(동작은 하지만 비권장).
    조회는 이 엔진으로, 쓰기(run_write/run_insert_returning)는 기존
    _engine_conn()의 psycopg2 커넥션을 그대로 쓴다(구조 변경 없음)."""
    url = URL.create(
        "postgresql+psycopg2",
        username=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        host=os.environ["DB_HOST"],
        port=int(os.environ.get("DB_PORT", "5432")),
        database=os.environ["DB_NAME"],
    )
    return create_engine(url, pool_pre_ping=True)


def run_query(sql: str, params: tuple = ()) -> pd.DataFrame:
    engine = _read_engine()
    try:
        return pd.read_sql(sql, engine, params=params)
    except Exception:
        # 연결이 끊어졌으면 캐시를 지우고 한 번 더 시도
        _read_engine.clear()
        engine = _read_engine()
        return pd.read_sql(sql, engine, params=params)


def run_write(sql: str, params: tuple = ()):
    conn = _engine_conn()
    with conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)


def fetch_options(sql: str, params: tuple = ()):
    """(id, label) 튜플 리스트 — selectbox용."""
    df = run_query(sql, params)
    return list(df.itertuples(index=False, name=None))


def run_insert_returning(sql: str, params: tuple = ()):
    """INSERT ... RETURNING 실행 후 첫 컬럼 값 반환 (커밋까지 처리)."""
    conn = _engine_conn()
    with conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()[0]


def _as_list(v):
    """jsonb 컬럼 값을 파이썬 list로. 드라이버에 따라 이미 list거나 문자열일 수 있어 둘 다 처리."""
    if v is None:
        return []
    if isinstance(v, str):
        try:
            return json.loads(v)
        except Exception:
            return []
    return list(v)


def _std_families(v):
    """application.active_stds(2026-09-18부터 대소문자로 개정판을 구분 — 예: "Q"=2026년판,
    "q"=2015년판)를 doc_type.applicable_std/dept_master 관련규격 매칭용 '규격 가족'
    소문자 목록으로 변환한다. 예: ["Q","hs"] -> ["q","hs"] (어느 개정판을 쓰든 필요한
    문서종류는 같다는 전제 — 조항번호 차이는 doc_type.clause_ref_overrides로 별도 처리)."""
    return [str(c).lower() for c in _as_list(v)]


def _fetch_active_standards():
    """등록 화면에서 고를 수 있는 규격(개정판 포함) 목록 — is_active인 것만, sort_order 순.
    2026-09-18 규격 개정판(예: ISO 9001/14001 2026년판) 지원 도입."""
    return run_query(
        "SELECT std_code, iso_num, title, edition_label, valid_from, valid_until, sort_order "
        "FROM standard WHERE is_active ORDER BY sort_order, std_code"
    )


def _standard_label(row, today):
    edition = row.get("edition_label") or ""
    label = f"{row['std_code']} — {row['iso_num']} {edition}".strip()
    if pd.notna(row.get("valid_until")) and row["valid_until"] < today:
        label += " (만료됨)"
    return label


_CLASSIC_STD_SLOTS = ["q", "e", "hs"]


def build_std_combo(selected_codes, standard_df):
    """선택된 규격코드 목록(대소문자로 개정판 구분, 예 ["Q","hs"])으로 조합 코드
    (project_no 접두어 / GCS 폴더 세그먼트)를 만든다.
    규칙(2026-09-18 협의 확정): 기존 q/e/hs 3종은 항상 q→e→hs 슬롯 순서로 뒤쪽에 오고,
    그 외 새로 추가된 규격은 standard.sort_order 오름차순으로 앞쪽에 붙는다
    ("신규 규격 + 기존 q,e,hs" 순서). 예: 새 규격 "is"+q+hs 선택 시 "isqhs".
    대문자(2026년판 등 개정판)는 소문자와 길이가 같아 조합 코드 길이에 영향 없음."""
    order_map = dict(zip(standard_df["std_code"], standard_df["sort_order"]))
    classic_present = {}
    others = []
    for code in selected_codes:
        family = code.lower()
        if family in _CLASSIC_STD_SLOTS:
            classic_present[family] = code
        else:
            others.append(code)
    others.sort(key=lambda c: order_map.get(c, 999))
    ordered = others + [classic_present[f] for f in _CLASSIC_STD_SLOTS if f in classic_present]
    return "".join(ordered)


def _create_custom_dept(category_code: str, dept_name: str) -> str:
    """조직 마스터 DB(dept_master)에 없는 새 부서명을 'z'중분류 버킷에 자동 채번해서 등록하고
    새 dept_code를 반환한다(예: 품질z1, 품질z2 ...). 채번된 코드는 다른 신청건에서도 재사용 가능하다."""
    existing = run_query(
        "SELECT dept_code FROM dept_master WHERE dept_code LIKE %s ORDER BY dept_code DESC LIMIT 1",
        (f"{category_code}z%",),
    )
    next_seq = 1
    if len(existing):
        last_digit = existing.iloc[0]["dept_code"][-1]
        if last_digit.isdigit():
            next_seq = min(int(last_digit) + 1, 9)
    new_code = f"{category_code}z{next_seq}"
    run_write(
        "INSERT INTO dept_master (dept_code, dept_name, category_code, category_name, category_seq, is_custom) "
        "VALUES (%s, %s, %s, %s, %s, true) ON CONFLICT (dept_code) DO NOTHING",
        (new_code, dept_name, category_code, DEPT_CATEGORY_NAME.get(category_code, category_code),
         DEPT_CATEGORY_SEQ.get(category_code, 999)),
    )
    return new_code


def _resolve_or_create_dept(category_code: str, dept_name: str) -> str:
    """"새 부서명 직접 입력"으로 저장할 때, 조직 마스터에 이미 같은 부서명이 있으면(예:
    전에 한 번 '품질'을 직접 입력해 품질z1이 만들어졌는데, 그 사실을 모르고 '품질'을 또
    직접 입력하는 경우) 그 dept_code를 그대로 재사용한다. 그렇지 않고 매번 새로
    채번해버리면 같은 이름의 부서가 z1, z2, z3...으로 계속 늘어나 버린다."""
    dept_name = dept_name.strip()
    same_cat = run_query(
        "SELECT dept_code FROM dept_master WHERE dept_name = %s AND category_code = %s "
        "ORDER BY dept_code LIMIT 1",
        (dept_name, category_code),
    )
    if len(same_cat):
        return same_cat.iloc[0]["dept_code"], False
    any_cat = run_query(
        "SELECT dept_code FROM dept_master WHERE dept_name = %s ORDER BY dept_code LIMIT 1",
        (dept_name,),
    )
    if len(any_cat):
        return any_cat.iloc[0]["dept_code"], False
    return _create_custom_dept(category_code, dept_name), True


def _resolve_or_create_original(original_name: str) -> int:
    """"Original 새로 입력" 시, 이미 같은 이름이 sample_original에 있으면 그 번호를
    재사용하고, 없으면 새 번호로 등록한다(문서관리 시트3 "Original 현황" 마스터)."""
    original_name = original_name.strip()
    match = run_query(
        "SELECT original_no FROM sample_original WHERE original_name = %s", (original_name,)
    )
    if len(match):
        return int(match.iloc[0]["original_no"])
    return run_insert_returning(
        "INSERT INTO sample_original (original_name) VALUES (%s) RETURNING original_no",
        (original_name,),
    )


# ---------- 3-부속. 문서관리 공용 헬퍼 ----------

FORM_PATTERN_LETTER = {
    "register_log": "A", "single_report": "B", "checklist": "C", "nested_evaluation": "D",
}


def _application_header(application_id):
    row = run_query(
        """
        SELECT a.application_id, a.project_no, a.std_code_normalized, a.active_stds,
               a.sample_name, a.original_no, so.original_name,
               c.company_name, sp.sector_name, sp.profile_seq
        FROM application a
        LEFT JOIN company c ON c.company_id = a.company_id
        LEFT JOIN sample_original so ON so.original_no = a.original_no
        LEFT JOIN sector_profile sp ON sp.profile_id = a.profile_id
        WHERE a.application_id = %s
        """,
        (application_id,),
    )
    return row.iloc[0] if len(row) else None


def _doc_list_for_application(application_id, categories, active_stds):
    return run_query(
        """
        SELECT dt.doc_type_id, dt.doc_type_code, dt.doc_type_name, dt.category,
               dt.clause_ref, dt.applicable_label, dt.applicable_std, dt.form_pattern_code,
               dt.subcategory, dt.subcategory_group, dt.subcategory_letter,
               di.doc_id, di.revision_no, di.storage_path AS individual_storage_path,
               di.form_seq_no, dc.storage_path AS content_storage_path
        FROM doc_type dt
        LEFT JOIN document_individual di
               ON di.doc_type_id = dt.doc_type_id AND di.application_id = %s
        LEFT JOIN document_content dc ON dc.doc_id = di.doc_id
        WHERE dt.category = ANY(%s) AND dt.applicable_std ?| %s
        ORDER BY
            CASE dt.category WHEN 'manual' THEN 1 WHEN 'procedure' THEN 2
                             WHEN 'form' THEN 3 ELSE 4 END,
            (substring(dt.doc_type_code from '\\d+'))::int, dt.doc_type_code
        """,
        (application_id, categories, active_stds or ["q", "e", "hs"]),
    )


def _annotate_doc_list(df):
    df = df.copy()
    df["패턴"] = df["form_pattern_code"].map(FORM_PATTERN_LETTER).fillna("")
    df["applicable_std_표시"] = df["applicable_std"].apply(lambda v: ",".join(_as_list(v)))
    df["비고"] = df.apply(
        lambda r: ("완성본 O" if pd.notna(r["individual_storage_path"]) else "완성본 X")
        + " / " + ("내용본 O" if pd.notna(r["content_storage_path"]) else "내용본 X"),
        axis=1,
    )
    return df


def _next_individual_revision(application_id, doc_type_id):
    existing = run_query(
        "SELECT doc_id, revision_no FROM document_individual WHERE application_id=%s AND doc_type_id=%s",
        (application_id, doc_type_id),
    )
    if len(existing):
        return int(existing.iloc[0]["doc_id"]), int(existing.iloc[0]["revision_no"]) + 1
    return None, 1


def _upsert_document_individual(application_id, doc_type_id, revision_no, fmt, storage_path,
                                 form_seq_no, existing_doc_id):
    if existing_doc_id:
        run_write(
            "UPDATE document_individual SET revision_no=%s, format=%s, storage_path=%s, "
            "status='current', form_seq_no=COALESCE(%s, form_seq_no) WHERE doc_id=%s",
            (revision_no, fmt, storage_path, form_seq_no, existing_doc_id),
        )
        doc_id = existing_doc_id
        note = "업로드로 개정"
    else:
        doc_id = run_insert_returning(
            "INSERT INTO document_individual "
            "(application_id, doc_type_id, revision_no, format, storage_path, status, form_seq_no) "
            "VALUES (%s,%s,%s,%s,%s,'current',%s) RETURNING doc_id",
            (application_id, doc_type_id, revision_no, fmt, storage_path, form_seq_no),
        )
        note = "최초 등록"
    run_write(
        "INSERT INTO document_revision_log (doc_id, revision_no, change_note, changed_at) "
        "VALUES (%s,%s,%s, now())",
        (doc_id, revision_no, note),
    )
    return doc_id


def _upsert_document_content(doc_id, fmt, storage_path):
    run_write(
        "INSERT INTO document_content (doc_id, format, storage_path, extracted_at) "
        "VALUES (%s,%s,%s, now()) "
        "ON CONFLICT (doc_id) DO UPDATE SET format=EXCLUDED.format, "
        "storage_path=EXCLUDED.storage_path, extracted_at=now()",
        (doc_id, fmt, storage_path),
    )


def _ledger_for_doc_type(doc_type_id):
    return run_query(
        """
        SELECT di.doc_id, a.application_id, a.project_no, di.revision_no, di.form_seq_no,
               dt.doc_type_code, dt.doc_type_name, dt.clause_ref, dt.applicable_label, dt.applicable_std,
               sp.sector_name, sp.profile_seq,
               COALESCE(c.company_name, a.sample_name) AS name_display,
               so.original_no, so.original_name,
               di.storage_path AS individual_storage_path,
               dc.storage_path AS content_storage_path
        FROM document_individual di
        JOIN application a ON a.application_id = di.application_id
        JOIN doc_type dt ON dt.doc_type_id = di.doc_type_id
        LEFT JOIN company c ON c.company_id = a.company_id
        LEFT JOIN sample_original so ON so.original_no = a.original_no
        LEFT JOIN sector_profile sp ON sp.profile_id = a.profile_id
        LEFT JOIN document_content dc ON dc.doc_id = di.doc_id
        WHERE di.doc_type_id = %s
        ORDER BY a.application_id DESC
        """,
        (doc_type_id,),
    )


def _render_ledger(doc_type_id, is_form=False):
    df = _ledger_for_doc_type(doc_type_id)
    if len(df) == 0:
        st.info("이 문서를 생성한 신청건이 아직 없습니다.")
        return
    df = df.copy()
    df["비고"] = df.apply(
        lambda r: ("완성본 O" if pd.notna(r["individual_storage_path"]) else "완성본 X")
        + " / " + ("내용본 O" if pd.notna(r["content_storage_path"]) else "내용본 X"),
        axis=1,
    )
    df["Original"] = df["original_no"].apply(lambda v: str(int(v)) if pd.notna(v) else "—")
    df["프로필"] = df["profile_seq"].apply(lambda v: f"seq {int(v)}" if pd.notna(v) else "—")
    df["applicable_std_표시"] = df["applicable_std"].apply(lambda v: ",".join(_as_list(v)))

    show_cols = ["doc_type_code", "revision_no"]
    rename_map = {"doc_type_code": "doc_code", "revision_no": "Rev.No"}
    if is_form:
        show_cols.append("form_seq_no")
        rename_map["form_seq_no"] = "doc_code(양식번호)"
    show_cols += ["doc_type_name", "프로필", "name_display", "Original", "clause_ref",
                  "applicable_label", "applicable_std_표시", "비고"]
    rename_map.update({
        "doc_type_name": "문서명", "name_display": "Company/Sample name",
        "clause_ref": "관련 ISO 조항", "applicable_label": "적용구분",
        "applicable_std_표시": "applicable_std",
    })
    st.caption(f"{len(df)}건 — 이 문서종류를 생성한 신청건 목록입니다.")
    st.dataframe(df[show_cols].rename(columns=rename_map), width="stretch")

    dl_options = [(int(r.doc_id), f"{r.project_no} (Rev.{r.revision_no})") for r in df.itertuples()]
    dl_choice = st.selectbox(
        "다운로드할 신청건 선택", dl_options, format_func=lambda x: x[1],
        key=f"ledger_dl_{doc_type_id}",
    )
    dl_row = df[df["doc_id"] == dl_choice[0]].iloc[0]
    file_kind = st.radio(
        "파일 종류", ["완성본", "내용본"], horizontal=True, key=f"ledger_kind_{doc_type_id}"
    )
    target_path = (
        dl_row["individual_storage_path"] if file_kind == "완성본" else dl_row["content_storage_path"]
    )
    if pd.isna(target_path):
        st.info("선택한 종류의 파일이 저장되어 있지 않습니다.")
    else:
        dl_key = f"ledger_data_{doc_type_id}_{dl_choice[0]}_{file_kind}"
        if st.button("다운로드 준비", key=f"ledger_prep_{doc_type_id}"):
            try:
                st.session_state[dl_key] = gcs_storage.download_bytes(target_path)
            except Exception as e:
                st.error(f"다운로드 실패: {e}")
        if dl_key in st.session_state:
            st.download_button(
                "파일 저장", data=st.session_state[dl_key],
                file_name=target_path.split("/")[-1], key=f"ledger_save_{doc_type_id}",
            )




# ---------- 2-부속. 조직 책임과 권한 ([1]~[3]) ----------
# 06_migrate_org_rr.py / 08_migrate_dept_master.py 반영 필요: org_chart.application_id,
# org_chart_role.mission/dept_code, dept_master 테이블, dept_responsibility 테이블,
# application.org_rr_status, org_rr_approval_log 테이블.

def _guess_category_idx_for_name(role_name):
    """dept_code가 없는 구버전 부서명(예: '품질')에서 대분류를 추정해 DEPT_CATEGORY_LIST의
    인덱스를 돌려준다 — 못 찾으면 None(호출측에서 기본값 0을 씀)."""
    if not role_name:
        return None
    for idx, (code, _name, _seq) in enumerate(DEPT_CATEGORY_LIST):
        if code in role_name:
            return idx
    return None


def _render_dept_and_resp(org_chart_id, app_id):
    """[1] 부서 목록 — 부서(org_chart_role, 조직마스터 dept_code 연동)와 책임·권한
    (dept_responsibility)을 사용자 등록처럼 한 화면에서 다룬다. "새 항목 추가"와
    "기존 항목 수정·삭제"를 화면·상태를 완전히 분리해서, 수정하려고 불러온 항목이
    남아있는 채로 새 내용을 저장해 덮어써지는 사고를 원천적으로 막는다."""
    st.markdown("#### [1] 부서 목록")

    combined_df = run_query(
        """
        SELECT r.dept_code, r.role_name AS "부서명", r.mission AS "부서미션",
               d.category AS "구분", d.seq AS "순번", d.content AS "내용",
               d.authority_criteria AS "권한기준", d.basis_doc AS "근거문서",
               d.required_competency AS "필요역량"
        FROM org_chart_role r
        LEFT JOIN dept_responsibility d ON d.role_id = r.role_id
        LEFT JOIN dept_master m ON m.dept_code = r.dept_code
        WHERE r.org_chart_id = %s
        ORDER BY m.category_seq NULLS LAST, r.dept_code NULLS LAST, r.role_id, d.category, d.seq
        """,
        (org_chart_id,),
    )
    if len(combined_df):
        # 아래 "불러올 항목 선택" 목록의 번호(1,2,3...)와 여기 표의 번호가 같은 행을
        # 가리키도록 맞춘다(두 쿼리가 완전히 같은 JOIN/ORDER BY라 행 순서가 일치한다).
        combined_df = combined_df.copy()
        combined_df.index = range(1, len(combined_df) + 1)
    st.dataframe(combined_df, width="stretch")

    steps = fetch_options(
        "SELECT step_id, stage_seq || '. ' || step_name FROM process_step "
        "WHERE application_id = %s ORDER BY stage_seq",
        (app_id,),
    )
    master_df = run_query(
        "SELECT dept_code, dept_name FROM dept_master ORDER BY category_seq, dept_code"
    )
    dept_select_options = [(r.dept_code, r.dept_name) for r in master_df.itertuples()] + [
        (NEW_DEPT_SENTINEL, "— 조직 마스터에 없는 새 부서명 직접 입력 —")
    ]

    st.markdown("**새 부서 · 책임/권한 항목 추가**")
    st.caption("여기는 항상 빈 양식입니다 — 아래 '수정·삭제'에서 불러온 값과 무관하게 새 항목이 추가됩니다.")
    _render_add_resp_form(org_chart_id, dept_select_options, steps)

    st.divider()

    st.markdown("**기존 부서 · 항목 수정 / 삭제**")
    _render_edit_resp_form(org_chart_id, dept_select_options, steps)


def _render_add_resp_form(org_chart_id, dept_select_options, steps):
    """부서 목록 화면의 "새 부서 · 책임/권한 항목 추가" — 항상 빈 값에서 시작하고, 성공적으로
    추가한 뒤에는 폼이 자동으로 비워진다(clear_on_submit). '수정·삭제'에서 무엇을
    불러왔는지와는 완전히 무관하다."""
    ns = f"deptresp_add_{org_chart_id}"
    dept_choice = st.selectbox(
        "부서 선택 — dept_code 하나만 고르면 dept_name까지 함께 정해집니다",
        dept_select_options, index=0,
        format_func=lambda x: x[1] if x[0] == NEW_DEPT_SENTINEL else f"{x[0]} — {x[1]}",
        key=f"{ns}_dept",
    )
    new_dept_category = None
    new_dept_name = ""
    if dept_choice[0] == NEW_DEPT_SENTINEL:
        new_dept_category = st.selectbox(
            "대분류 선택 — 새 dept_code 자동 채번에 쓰입니다", DEPT_CATEGORY_LIST,
            format_func=lambda x: f"{x[0]} {x[1]}", key=f"{ns}_newcat",
        )
        new_dept_name = st.text_input("새 부서명 *", key=f"{ns}_newname")
        st.caption(f"저장 시 dept_code {new_dept_category[0]}z_ 로 조직 마스터 DB에 자동 등록됩니다.")
    else:
        # 고정된 key를 쓰는 입력 위젯(text_input)은 "부서 선택"을 바꿔도 Streamlit이
        # 예전 값을 그대로 들고 있어(위젯이 이미 생성된 뒤에는 value= 인자가 무시됨) 화면이
        # 안 바뀌는 문제가 있었다. 상태가 없는 markdown으로 표시해 매번 새로 그려지게 한다.
        col1, col2 = st.columns(2)
        col1.markdown(f"**dept_code**\n\n`{dept_choice[0]}`")
        col2.markdown(f"**dept_name**\n\n`{dept_choice[1]}`")

    with st.form(f"{ns}_form", clear_on_submit=True):
        mission = st.text_area("부서 미션 (선택 — 이미 있는 부서면 비워두면 기존 값이 유지됩니다)")
        category = st.radio("구분(책임/권한) *", ["책임", "권한"], horizontal=True)
        content = st.text_area("내용 *")
        authority_criteria = st.text_input("권한기준(금액, 범위 등) — 해당 시에만 입력")
        step_choice = st.selectbox(
            "관련 프로세스 (선택 — 프로세스맵 생성 후 목록에 표시/자동연동 예정)",
            [(None, "— 선택 안 함 —")] + steps, format_func=lambda x: x[1],
        )
        basis_doc = st.text_input("근거문서/조항 (선택 — 프로세스맵 확정 후 자동생성 예정)")
        competency = st.text_input("필요역량/자격 (선택)")

        submitted = st.form_submit_button("항목 추가")
        if submitted:
            if dept_choice[0] == NEW_DEPT_SENTINEL and not new_dept_name.strip():
                st.error("새 부서명을 입력해주세요.")
            elif not content.strip():
                st.error("내용은 필수입니다.")
            else:
                dept_reused = False
                if dept_choice[0] == NEW_DEPT_SENTINEL:
                    dept_code_final, dept_created = _resolve_or_create_dept(
                        new_dept_category[0], new_dept_name.strip()
                    )
                    dept_reused = not dept_created
                    dept_name_final = new_dept_name.strip()
                else:
                    dept_code_final, dept_name_final = dept_choice

                # 이 org_chart 안에 해당 dept_code 부서가 이미 있으면 재사용(항목만 추가),
                # 없으면 새로 만든다. 미션은 입력했을 때만 덮어쓴다(비워두면 기존 값 유지).
                same_dept_role = run_query(
                    "SELECT role_id FROM org_chart_role WHERE org_chart_id=%s AND dept_code=%s",
                    (org_chart_id, dept_code_final),
                )
                if len(same_dept_role):
                    role_id = int(same_dept_role.iloc[0]["role_id"])
                    if mission.strip():
                        run_write(
                            "UPDATE org_chart_role SET role_name=%s, mission=%s WHERE role_id=%s",
                            (dept_name_final, mission.strip(), role_id),
                        )
                    else:
                        run_write(
                            "UPDATE org_chart_role SET role_name=%s WHERE role_id=%s",
                            (dept_name_final, role_id),
                        )
                else:
                    role_id = run_insert_returning(
                        "INSERT INTO org_chart_role (org_chart_id, role_name, dept_code, mission, seq) "
                        "VALUES (%s, %s, %s, %s, 0) RETURNING role_id",
                        (org_chart_id, dept_name_final, dept_code_final, mission.strip() or None),
                    )

                next_seq = run_query(
                    "SELECT coalesce(max(seq), 0) + 1 AS n FROM dept_responsibility "
                    "WHERE role_id = %s AND category = %s",
                    (role_id, category),
                ).iloc[0]["n"]
                item_seq = int(next_seq)
                run_write(
                    "INSERT INTO dept_responsibility "
                    "(role_id, category, seq, content, authority_criteria, related_step_id, "
                    "basis_doc, required_competency) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                    (role_id, category, item_seq, content.strip(), authority_criteria.strip() or None,
                     step_choice[0], basis_doc.strip() or None, competency.strip() or None),
                )
                reuse_note = " · 이미 있는 동일한 이름의 부서를 재사용했습니다" if dept_reused else ""
                st.success(f"등록되었습니다({dept_code_final} — {category} 순번 {item_seq}{reuse_note}).")
                st.rerun()


def _render_edit_resp_form(org_chart_id, dept_select_options, steps):
    """부서 목록 화면의 "기존 부서·항목 수정/삭제" — 이미 있는 항목/부서만 다루며, 새
    항목 추가는 절대 여기서 일어나지 않는다(그건 위 '추가' 폼의 몫)."""
    role_item_rows = run_query(
        """
        SELECT r.role_id, r.dept_code, r.role_name,
               d.resp_id, d.category, d.content
        FROM org_chart_role r
        LEFT JOIN dept_responsibility d ON d.role_id = r.role_id
        LEFT JOIN dept_master m ON m.dept_code = r.dept_code
        WHERE r.org_chart_id = %s
        ORDER BY m.category_seq NULLS LAST, r.dept_code NULLS LAST, r.role_id, d.category, d.seq
        """,
        (org_chart_id,),
    )
    if not len(role_item_rows):
        st.caption("아직 등록된 부서가 없습니다. 위 '새 부서 · 책임/권한 항목 추가'에서 먼저 등록해주세요.")
        return

    load_options = []
    seen_bare_roles = set()
    item_no = 0
    for row in role_item_rows.itertuples():
        item_no += 1
        # pandas의 NaN은 파이썬에서 참(truthy)으로 취급되어 `or`로는 걸러지지 않으므로
        # pd.notna로 명시적으로 검사한다. dept_code가 비어 있으면(마스터 연동 이전의
        # 구버전 데이터) 그 사실을 라벨에 분명히 표시한다.
        dept_code_display = row.dept_code if pd.notna(row.dept_code) else "dept_code 없음·연결 필요"
        dept_label = f"{dept_code_display} {row.role_name}"
        if pd.notna(row.resp_id):
            load_options.append((
                ("item", int(row.resp_id)),
                f"{item_no}. {dept_label} - {row.category} - {(row.content or '')[:30]}",
            ))
        elif row.role_id not in seen_bare_roles:
            seen_bare_roles.add(row.role_id)
            load_options.append((
                ("dept", int(row.role_id)),
                f"{item_no}. {dept_label} — (등록된 항목 없음 · 부서만 있음)",
            ))

    # "수정할 항목 선택" 위젯의 key. 저장/삭제 직후에는 다음 실행에서 목록 맨 처음 항목으로
    # 되돌린다 — 위젯이 이미 생성된 이후(이번 실행 중)에는 session_state[load_key]를 직접
    # 바꿀 수 없으므로(Streamlit 제약) __reset 플래그를 세워두고 다음 실행 맨 처음,
    # 위젯을 만들기 전에 반영한다.
    load_key = f"deptresp_load_{org_chart_id}"
    if st.session_state.pop(f"{load_key}__reset", False):
        st.session_state.pop(load_key, None)

    load_value_map = {opt[0]: opt for opt in load_options}
    if load_key not in st.session_state or st.session_state[load_key] not in load_value_map:
        st.session_state[load_key] = load_options[0][0]
    load_choice_tag = st.selectbox(
        "수정 · 삭제할 항목 선택",
        [opt[0] for opt in load_options],
        format_func=lambda tag: load_value_map[tag][1],
        key=load_key,
    )
    kind, load_id = load_choice_tag
    editing_id = load_id if kind == "item" else None
    editing_role_id = load_id if kind == "dept" else None
    load_token = f"{kind}_{load_id}"

    existing = None
    existing_role = None
    if kind == "item":
        existing = run_query("SELECT * FROM dept_responsibility WHERE resp_id = %s", (editing_id,)).iloc[0]
        existing_role = run_query(
            "SELECT * FROM org_chart_role WHERE role_id = %s", (int(existing["role_id"]),)
        ).iloc[0]
    else:
        existing_role = run_query(
            "SELECT * FROM org_chart_role WHERE role_id = %s", (editing_role_id,)
        ).iloc[0]

    # dept_code가 있는 부서는 그대로 기본 선택한다. dept_code가 없는(마스터 연동 이전의)
    # 구버전 부서는 "새 부서명 직접 입력"을 기본값으로 띄우고, 부서명으로 대분류까지
    # 최대한 추정해 보여준다(예: '품질' → 품질 대분류) — 엉뚱한 첫 대분류(인사)가 아니라
    # 실제 부서명과 맞는 값이 나오도록.
    default_dept_idx = len(dept_select_options) - 1
    guessed_cat_idx = None
    if pd.notna(existing_role.get("dept_code")):
        codes = [x[0] for x in dept_select_options]
        if existing_role["dept_code"] in codes:
            default_dept_idx = codes.index(existing_role["dept_code"])
    else:
        guessed_cat_idx = _guess_category_idx_for_name(existing_role.get("role_name"))

    dept_choice = st.selectbox(
        "부서 선택 — dept_code 하나만 고르면 dept_name까지 함께 정해집니다",
        dept_select_options, index=default_dept_idx,
        format_func=lambda x: x[1] if x[0] == NEW_DEPT_SENTINEL else f"{x[0]} — {x[1]}",
        key=f"deptresp_edit_dept_{org_chart_id}_{load_token}",
    )

    new_dept_category = None
    new_dept_name = ""
    if dept_choice[0] == NEW_DEPT_SENTINEL:
        new_dept_category = st.selectbox(
            "대분류 선택 — 새 dept_code 자동 채번에 쓰입니다", DEPT_CATEGORY_LIST,
            index=guessed_cat_idx or 0,
            format_func=lambda x: f"{x[0]} {x[1]}", key=f"deptresp_edit_newcat_{org_chart_id}_{load_token}",
        )
        new_dept_name = st.text_input(
            "새 부서명 *", value=existing_role.get("role_name") or "",
            key=f"deptresp_edit_newname_{org_chart_id}_{load_token}",
        )
        st.caption(f"저장 시 dept_code {new_dept_category[0]}z_ 로 조직 마스터 DB에 자동 등록됩니다.")
    else:
        # 고정된 key를 쓰는 입력 위젯은 "부서 선택"을 바꿔도 예전 값을 그대로 들고 있어
        # 화면이 안 바뀌는 문제가 있었다. 상태가 없는 markdown으로 표시해 매번 새로
        # 그려지게 한다.
        col1, col2 = st.columns(2)
        col1.markdown(f"**dept_code**\n\n`{dept_choice[0]}`")
        col2.markdown(f"**dept_name**\n\n`{dept_choice[1]}`")

    with st.form(f"deptresp_edit_form_{org_chart_id}_{load_token}"):
        mission = st.text_area("부서 미션", value=existing_role.get("mission") or "")
        content_label = "내용 *" if kind == "item" else "내용 (선택 — 입력하면 이 부서의 첫 항목으로 등록됩니다)"
        category = st.radio(
            "구분(책임/권한) *", ["책임", "권한"], horizontal=True,
            index=0 if existing is None or existing["category"] == "책임" else 1,
        )
        content = st.text_area(content_label, value="" if existing is None else existing["content"])
        authority_criteria = st.text_input(
            "권한기준(금액, 범위 등) — 해당 시에만 입력",
            value="" if existing is None else (existing.get("authority_criteria") or ""),
        )
        default_step_idx = 0
        if existing is not None and pd.notna(existing.get("related_step_id")):
            step_ids = [None] + [x[0] for x in steps]
            if int(existing["related_step_id"]) in step_ids:
                default_step_idx = step_ids.index(int(existing["related_step_id"]))
        step_choice = st.selectbox(
            "관련 프로세스 (선택 — 프로세스맵 생성 후 목록에 표시/자동연동 예정)",
            [(None, "— 선택 안 함 —")] + steps,
            format_func=lambda x: x[1], index=default_step_idx,
        )
        basis_doc = st.text_input(
            "근거문서/조항 (선택 — 프로세스맵 확정 후 자동생성 예정)",
            value="" if existing is None else (existing.get("basis_doc") or ""),
        )
        competency = st.text_input(
            "필요역량/자격 (선택)", value="" if existing is None else (existing.get("required_competency") or "")
        )

        submitted = st.form_submit_button("수정 저장")
        if submitted:
            if dept_choice[0] == NEW_DEPT_SENTINEL and not new_dept_name.strip():
                st.error("새 부서명을 입력해주세요.")
            elif kind == "item" and not content.strip():
                st.error("내용은 필수입니다.")
            else:
                if dept_choice[0] == NEW_DEPT_SENTINEL:
                    dept_code_final, _ = _resolve_or_create_dept(new_dept_category[0], new_dept_name.strip())
                    dept_name_final = new_dept_name.strip()
                else:
                    dept_code_final, dept_name_final = dept_choice

                current_role_id = int(existing["role_id"]) if kind == "item" else int(editing_role_id)

                same_dept_role = run_query(
                    "SELECT role_id FROM org_chart_role WHERE org_chart_id=%s AND dept_code=%s",
                    (org_chart_id, dept_code_final),
                )
                other_role_id = int(same_dept_role.iloc[0]["role_id"]) if len(same_dept_role) else None

                if other_role_id is None or other_role_id == current_role_id:
                    # 지금 편집 중인 그 부서를 그대로 갱신한다(dept_code 없음 → 지정 포함).
                    # dept_code가 없던 구버전 행을 여기서 정상적으로 연결하는 경로도 이것이다.
                    role_id = current_role_id
                    run_write(
                        "UPDATE org_chart_role SET role_name=%s, dept_code=%s, mission=%s WHERE role_id=%s",
                        (dept_name_final, dept_code_final, mission.strip() or None, role_id),
                    )
                else:
                    # 같은 dept_code를 쓰는 다른 부서가 이미 있음 → 그쪽으로 합친다. 지금
                    # 편집 중이던 부서(주로 dept_code 없는 구버전 행)는 항목을 옮긴 뒤
                    # 정리해서, 부서명·dept_code 중 하나라도 비어 있는 행이 남지 않도록 한다.
                    role_id = other_role_id
                    run_write(
                        "UPDATE org_chart_role SET role_name=%s, mission=%s WHERE role_id=%s",
                        (dept_name_final, mission.strip() or None, role_id),
                    )
                    run_write(
                        "UPDATE dept_responsibility SET role_id=%s WHERE role_id=%s",
                        (role_id, current_role_id),
                    )
                    run_write(
                        "UPDATE responsibility_matrix SET role_id=%s WHERE role_id=%s",
                        (role_id, current_role_id),
                    )
                    run_write("DELETE FROM org_chart_role WHERE role_id=%s", (current_role_id,))

                if kind == "item":
                    run_write(
                        "UPDATE dept_responsibility SET role_id=%s, category=%s, content=%s, "
                        "authority_criteria=%s, related_step_id=%s, basis_doc=%s, required_competency=%s "
                        "WHERE resp_id=%s",
                        (role_id, category, content.strip(), authority_criteria.strip() or None,
                         step_choice[0], basis_doc.strip() or None, competency.strip() or None, editing_id),
                    )
                    st.success("수정되었습니다.")
                elif content.strip():
                    next_seq = run_query(
                        "SELECT coalesce(max(seq), 0) + 1 AS n FROM dept_responsibility "
                        "WHERE role_id = %s AND category = %s",
                        (role_id, category),
                    ).iloc[0]["n"]
                    run_write(
                        "INSERT INTO dept_responsibility "
                        "(role_id, category, seq, content, authority_criteria, related_step_id, "
                        "basis_doc, required_competency) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                        (role_id, category, int(next_seq), content.strip(), authority_criteria.strip() or None,
                         step_choice[0], basis_doc.strip() or None, competency.strip() or None),
                    )
                    st.success("부서 정보가 저장되고 첫 항목이 추가되었습니다.")
                else:
                    st.success("부서 정보가 저장되었습니다.")
                st.session_state[f"{load_key}__reset"] = True
                st.rerun()

    if kind == "item" and st.button("이 항목 삭제", key=f"deptresp_del_item_{editing_id}"):
        run_write("DELETE FROM dept_responsibility WHERE resp_id = %s", (editing_id,))
        st.success("삭제되었습니다.")
        st.session_state[f"{load_key}__reset"] = True
        st.rerun()

    if kind == "dept" and st.button(
        "이 부서 삭제(등록된 항목 없음)", key=f"deptresp_del_dept_{editing_role_id}"
    ):
        run_write("DELETE FROM responsibility_matrix WHERE role_id = %s", (editing_role_id,))
        run_write("DELETE FROM org_chart_role WHERE role_id = %s", (editing_role_id,))
        st.success("부서가 삭제되었습니다.")
        st.session_state[f"{load_key}__reset"] = True
        st.rerun()


def _render_raci(org_chart_id, app_id, org_scale):
    """[3] RACI 매트릭스 — responsibility_matrix(R/A/C/I) 편집."""
    st.markdown("#### [2] RACI 매트릭스")
    if org_scale == ORG_SCALE_OPTIONS[0]:
        st.caption("규모가 작은 조직(10인미만)은 생략해도 됩니다 — 필요하면 계속 진행하세요.")

    steps = run_query(
        "SELECT step_id, step_name FROM process_step WHERE application_id = %s ORDER BY stage_seq",
        (app_id,),
    )
    roles = run_query(
        "SELECT role_id, role_name FROM org_chart_role WHERE org_chart_id = %s ORDER BY seq, role_id",
        (org_chart_id,),
    )
    if len(steps) == 0:
        st.info("이 신청건의 프로세스맵이 아직 없습니다. 프로세스맵 생성 후 이용할 수 있습니다.")
        return
    if len(roles) == 0:
        st.info("먼저 [1] 부서 목록에서 부서를 등록해주세요.")
        return

    role_ids = [int(x) for x in roles["role_id"].tolist()]
    role_names = {int(r.role_id): r.role_name for r in roles.itertuples()}

    existing = run_query(
        "SELECT step_id, role_id, resp_type FROM responsibility_matrix WHERE role_id = ANY(%s)",
        (role_ids,),
    )

    st.caption("행(프로세스) 추가·삭제는 이 화면에서 할 수 없습니다 — 프로세스맵 화면에서 관리하세요.")

    if st.button("자동생성(초안) — 기존 값을 덮어씁니다", key=f"raci_auto_{org_chart_id}"):
        linked = run_query(
            "SELECT related_step_id, role_id FROM dept_responsibility "
            "WHERE role_id = ANY(%s) AND category = '책임' AND related_step_id IS NOT NULL",
            (role_ids,),
        )
        run_write("DELETE FROM responsibility_matrix WHERE role_id = ANY(%s)", (role_ids,))
        for step_id in steps["step_id"].tolist():
            resp_roles = linked[linked["related_step_id"] == step_id]["role_id"].unique().tolist()
            for rid in resp_roles:
                run_write(
                    "INSERT INTO responsibility_matrix (step_id, role_id, resp_type) VALUES (%s, %s, 'R')",
                    (int(step_id), int(rid)),
                )
            if len(resp_roles) == 1:
                run_write(
                    "UPDATE responsibility_matrix SET resp_type='A' WHERE step_id=%s AND role_id=%s",
                    (int(step_id), int(resp_roles[0])),
                )
        st.success("자동생성했습니다. 필요하면 아래에서 값을 고친 뒤 저장하세요.")
        st.rerun()

    step_ids = steps["step_id"].tolist()
    grid = pd.DataFrame({"process_step": steps["step_name"].values})
    for rid in role_ids:
        grid[role_names[rid]] = ""
    for r_ in existing.itertuples():
        if int(r_.role_id) in role_names and r_.step_id in step_ids:
            i = step_ids.index(r_.step_id)
            grid.loc[i, role_names[int(r_.role_id)]] = r_.resp_type

    col_config = {
        name: st.column_config.SelectboxColumn(options=["", "R", "A", "C", "I"])
        for name in role_names.values()
    }
    col_config["process_step"] = st.column_config.TextColumn(disabled=True)
    edited = st.data_editor(
        grid, column_config=col_config, width="stretch", key=f"raci_grid_{org_chart_id}"
    )

    if st.button("저장", key=f"raci_save_{org_chart_id}"):
        run_write("DELETE FROM responsibility_matrix WHERE role_id = ANY(%s)", (role_ids,))
        for i, row in edited.iterrows():
            step_id = int(step_ids[i])
            for rid in role_ids:
                val = row.get(role_names[rid], "")
                if val:
                    run_write(
                        "INSERT INTO responsibility_matrix (step_id, role_id, resp_type) VALUES (%s, %s, %s)",
                        (step_id, rid, val),
                    )
        st.success("저장되었습니다.")
        st.rerun()


def _has_cycle(roles_df):
    parent = {
        int(r.role_id): (int(r.parent_role_id) if pd.notna(r.parent_role_id) else None)
        for r in roles_df.itertuples()
    }
    for start in parent:
        seen = set()
        cur = start
        while cur is not None:
            if cur in seen:
                return True
            seen.add(cur)
            cur = parent.get(cur)
    return False


def _render_verify_confirm(org_chart_id, app_id):
    """[4] 검증 및 확정 — 오류(확정 불가)/경고(표시만) 2등급, 확정 시 스냅샷 이력 저장."""
    st.markdown("#### [3] 검증 및 확정")

    roles = run_query(
        "SELECT role_id, role_name, parent_role_id FROM org_chart_role WHERE org_chart_id = %s",
        (org_chart_id,),
    )
    role_ids = [int(x) for x in roles["role_id"].tolist()]
    steps = run_query("SELECT step_id, step_name FROM process_step WHERE application_id = %s", (app_id,))
    matrix = (
        run_query("SELECT step_id, role_id, resp_type FROM responsibility_matrix WHERE role_id = ANY(%s)", (role_ids,))
        if role_ids else pd.DataFrame(columns=["step_id", "role_id", "resp_type"])
    )
    resp = (
        run_query("SELECT role_id, category FROM dept_responsibility WHERE role_id = ANY(%s)", (role_ids,))
        if role_ids else pd.DataFrame(columns=["role_id", "category"])
    )

    errors, warnings = [], []

    assigned_steps = set(matrix["step_id"].unique().tolist())
    for s in steps.itertuples():
        if s.step_id not in assigned_steps:
            errors.append(f"담당 부서가 배정되지 않은 프로세스: {s.step_name}")

    a_counts = matrix[matrix["resp_type"] == "A"].groupby("step_id").size()
    for s in steps.itertuples():
        cnt = int(a_counts.get(s.step_id, 0))
        if cnt >= 2:
            errors.append(f"A(승인/최종책임)가 {cnt}개 지정됨: {s.step_name}")
        elif cnt == 0 and s.step_id in assigned_steps:
            errors.append(f"A(승인/최종책임)가 지정되지 않음: {s.step_name}")

    if len(roles) and _has_cycle(roles):
        errors.append("조직도의 상위부서 관계에 순환참조가 있습니다.")

    root_count = int(roles["parent_role_id"].isna().sum()) if len(roles) else 0
    if root_count == 0:
        errors.append("최상위 부서(상위부서 없음)가 없습니다.")
    elif root_count >= 2:
        errors.append(f"최상위 부서가 {root_count}개입니다(1개여야 합니다).")

    resp_roles_with_content = set(resp[resp["category"] == "책임"]["role_id"].unique().tolist())
    for r_ in roles.itertuples():
        if r_.role_id not in resp_roles_with_content:
            warnings.append(f"책임 항목이 하나도 없는 부서: {r_.role_name}")

    st.caption("절차서 문서와 부서명 교차검증은 절차서 생성 모듈 연동 후 추가될 예정입니다.")

    if not errors and not warnings:
        st.success("확인된 오류/경고가 없습니다.")
    else:
        for e in errors:
            st.error(e)
        for w in warnings:
            st.warning(w)

    app_status = run_query(
        "SELECT org_rr_status FROM application WHERE application_id = %s", (app_id,)
    ).iloc[0]["org_rr_status"]
    st.caption(f"현재 상태: {app_status}")

    if st.button("검증하기", key=f"verify_btn_{app_id}"):
        run_write(
            "UPDATE application SET org_rr_status = %s WHERE application_id = %s",
            ("검증완료" if not errors else "초안", app_id),
        )
        st.rerun()

    approver = st.text_input("승인자", key=f"approver_{app_id}")
    if st.button("확정", key=f"confirm_btn_{app_id}", disabled=bool(errors)):
        snapshot = {
            "org_chart_role": run_query(
                "SELECT * FROM org_chart_role WHERE org_chart_id=%s", (org_chart_id,)
            ).to_dict("records"),
            "dept_responsibility": (
                run_query("SELECT * FROM dept_responsibility WHERE role_id = ANY(%s)", (role_ids,)).to_dict("records")
                if role_ids else []
            ),
            "responsibility_matrix": matrix.to_dict("records"),
        }
        rev = run_query(
            "SELECT coalesce(max(rev_no), 0) + 1 AS next_rev FROM org_rr_approval_log WHERE application_id=%s",
            (app_id,),
        ).iloc[0]["next_rev"]
        run_write(
            "INSERT INTO org_rr_approval_log (application_id, rev_no, snapshot, approved_by) "
            "VALUES (%s, %s, %s, %s)",
            (app_id, int(rev), json.dumps(snapshot, ensure_ascii=False, default=str), approver.strip() or None),
        )
        run_write("UPDATE application SET org_rr_status = '확정' WHERE application_id = %s", (app_id,))
        st.success(f"확정되었습니다. (rev {int(rev)})")
        st.rerun()


# ---------- 사이드바 네비게이션 ----------

st.sidebar.title("경영시스템문서 플랫폼")
page = st.sidebar.radio(
    "화면 선택",
    ["1. 기준정보 조회", "2. 사용자 관리", "3. 문서관리"],
)

try:
    _engine_conn()
    st.sidebar.success("DB 연결됨")
except Exception as e:
    st.sidebar.error(f"DB 연결 실패: {e}")
    st.stop()


# ---------- 1. 기준정보 조회 ----------

if page.startswith("1"):
    st.header("기준정보 조회")

    tab = st.selectbox(
        "테이블 선택",
        ["standard (규격)", "sector_main (대분류)", "iaf_group (IAF그룹)",
         "sector_profile (업종 프로필)", "doc_type (문서종류 마스터)", "form_pattern (양식 패턴)",
         "sample_original (Original 현황)"],
    )

    if tab.startswith("standard"):
        st.dataframe(
            run_query("SELECT * FROM standard ORDER BY sort_order, std_code"),
            width="stretch",
        )
        st.caption(
            "std_code 대소문자로 개정판을 구분합니다(예: q=2015년판, Q=2026년판). "
            "삭제는 지원하지 않습니다 — 더 이상 신규 등록에 쓰지 않으려면 '사용 안 함(is_active=false)'으로 바꾸세요."
        )

        st.divider()
        st.subheader("규격/개정판 추가 · 수정")
        std_rows = run_query("SELECT * FROM standard ORDER BY sort_order, std_code")
        edit_targets = [(None, "— 새 규격/개정판 추가 —")] + [
            (r["std_code"], f"{r['std_code']} — {r['iso_num']} {r.get('edition_label') or ''}")
            for _, r in std_rows.iterrows()
        ]
        std_edit_choice = st.selectbox(
            "추가할지, 기존 항목을 고칠지 선택",
            edit_targets, format_func=lambda x: x[1], key="std_edit_choice",
        )
        std_existing = None
        if std_edit_choice[0]:
            std_existing = std_rows[std_rows["std_code"] == std_edit_choice[0]].iloc[0]

        with st.form("std_edit_form"):
            std_code_in = st.text_input(
                "std_code * (신규일 때만 입력 — 예: q, Q, e, E, hs, 새 규격이면 새 코드)",
                value="" if std_existing is None else std_existing["std_code"],
                disabled=std_existing is not None,
            )
            iso_num_in = st.text_input(
                "iso_num * (예: ISO 9001)",
                value="" if std_existing is None else (std_existing.get("iso_num") or ""),
            )
            title_in = st.text_input(
                "title * (예: 품질경영시스템)",
                value="" if std_existing is None else (std_existing.get("title") or ""),
            )
            prefix_in = st.text_input(
                "prefix * (필수)",
                value="" if std_existing is None else (std_existing.get("prefix") or ""),
            )
            edition_label_in = st.text_input(
                "edition_label (예: 2015년판 / 2026년판)",
                value="" if std_existing is None else (std_existing.get("edition_label") or ""),
            )
            col_a, col_b = st.columns(2)
            with col_a:
                valid_from_in = st.date_input(
                    "valid_from (선택)",
                    value=(std_existing.get("valid_from") if std_existing is not None
                           and pd.notna(std_existing.get("valid_from")) else None),
                )
            with col_b:
                valid_until_in = st.date_input(
                    "valid_until (선택 — 만료일, 지나면 신규 등록에서 선택 불가)",
                    value=(std_existing.get("valid_until") if std_existing is not None
                           and pd.notna(std_existing.get("valid_until")) else None),
                )
            sort_order_in = st.number_input(
                "sort_order (조합 코드 생성 순서 — 기존 q/e/hs는 10/20/30, 새 규격은 더 작은 값을 "
                "주면 조합 코드 앞쪽에 옵니다)",
                value=int(std_existing["sort_order"]) if std_existing is not None else 5,
                step=1,
            )
            is_current_default_in = st.checkbox(
                "신규 등록 폼에서 기본으로 추천(is_current_default)",
                value=bool(std_existing["is_current_default"]) if std_existing is not None else False,
            )
            is_active_in = st.checkbox(
                "사용함(is_active) — 끄면 신규 등록 목록에서 빠집니다",
                value=bool(std_existing["is_active"]) if std_existing is not None else True,
            )
            if st.form_submit_button("저장"):
                errs = []
                code_val = (std_existing["std_code"] if std_existing is not None else std_code_in.strip())
                if not code_val:
                    errs.append("std_code는 필수입니다.")
                if not iso_num_in.strip():
                    errs.append("iso_num은 필수입니다.")
                if not title_in.strip():
                    errs.append("title은 필수입니다.")
                if not prefix_in.strip():
                    errs.append("prefix는 필수입니다.")
                if errs:
                    for m in errs:
                        st.error(m)
                else:
                    if std_existing is not None:
                        run_write(
                            """
                            UPDATE standard SET
                                iso_num = %s, title = %s, prefix = %s, edition_label = %s,
                                valid_from = %s, valid_until = %s, sort_order = %s,
                                is_current_default = %s, is_active = %s
                            WHERE std_code = %s
                            """,
                            (iso_num_in.strip(), title_in.strip(), prefix_in.strip(),
                             edition_label_in.strip() or None, valid_from_in, valid_until_in,
                             int(sort_order_in), is_current_default_in, is_active_in, code_val),
                        )
                        st.success(f"'{code_val}' 수정되었습니다.")
                    else:
                        try:
                            run_write(
                                """
                                INSERT INTO standard
                                    (std_code, iso_num, title, prefix, edition_label,
                                     valid_from, valid_until, sort_order,
                                     is_current_default, is_active)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                                """,
                                (code_val, iso_num_in.strip(), title_in.strip(), prefix_in.strip(),
                                 edition_label_in.strip() or None, valid_from_in, valid_until_in,
                                 int(sort_order_in), is_current_default_in, is_active_in),
                            )
                            st.success(f"'{code_val}' 추가되었습니다.")
                        except Exception as e:
                            if "duplicate key" in str(e).lower():
                                st.error(f"std_code '{code_val}'는 이미 있습니다.")
                            else:
                                st.error(f"저장 중 오류: {e}")
                    st.rerun()

    elif tab.startswith("sector_main"):
        st.dataframe(run_query("SELECT * FROM sector_main ORDER BY code"), width="stretch")

    elif tab.startswith("iaf_group"):
        st.dataframe(run_query("SELECT * FROM iaf_group ORDER BY iaf_num"), width="stretch")

    elif tab.startswith("sector_profile"):
        col1, col2 = st.columns(2)
        with col1:
            code_filter = st.text_input("업종코드 검색 (예: M17f, 앞부분만 입력해도 됨)")
        with col2:
            name_filter = st.text_input("업종명 검색")

        sql = """
            SELECT profile_id, sector_code, profile_seq, sector_name, sector_main,
                   iaf_num, sector_detail, is_default, hazards, env_aspects,
                   quality_chars, key_laws_sh, key_laws_env, process_hints
            FROM sector_profile
            WHERE sector_code ILIKE %s AND sector_name ILIKE %s
            ORDER BY sector_code, profile_seq
            LIMIT 500
        """
        df = run_query(sql, (f"{code_filter}%", f"%{name_filter}%"))
        st.caption(f"{len(df)}건 표시 (최대 500건)")
        st.dataframe(df, width="stretch")

    elif tab.startswith("doc_type"):
        cat_filter = st.multiselect(
            "분류(category)", ["manual", "procedure", "guideline", "form"],
            default=["manual", "procedure", "guideline", "form"],
        )
        std_filter = st.multiselect("적용 규격", ["q", "e", "hs"], default=["q", "e", "hs"])
        if not cat_filter:
            cat_filter = ["manual", "procedure", "guideline", "form"]
        if not std_filter:
            std_filter = ["q", "e", "hs"]

        sql = """
            SELECT doc_type_code, doc_type_name, category, applicable_label,
                   clause_ref, subcategory, subcategory_group, display_code, remark
            FROM doc_type
            WHERE category = ANY(%s)
              AND applicable_std ?| %s
            ORDER BY
                CASE category
                    WHEN 'manual' THEN 1
                    WHEN 'procedure' THEN 2
                    WHEN 'guideline' THEN 3
                    WHEN 'form' THEN 4
                    ELSE 5
                END,
                (substring(doc_type_code from '\\d+'))::int,
                doc_type_code,
                display_code
        """
        df = run_query(sql, (cat_filter, std_filter))
        st.caption(f"{len(df)}건 표시")
        st.dataframe(df, width="stretch")

        st.divider()
        st.subheader("개정판별 조항번호 예외(clause_ref_overrides)")
        st.caption(
            "규격 개정판에서 조항번호가 달라지거나(예: ISO 9001:2026 신설 6.1.3) 조항 자체가 "
            "없어진 경우(예: ISO 14001:2026의 6.1.1 소멸)를 문서종류별로 등록합니다. "
            "등록하지 않으면 doc_type.clause_ref(기본 조항번호)를 그대로 씁니다."
        )
        override_targets = fetch_options(
            "SELECT doc_type_code, doc_type_code || ' - ' || doc_type_name || "
            "'  (기본 조항: ' || COALESCE(clause_ref, '없음') || ')' "
            "FROM doc_type ORDER BY doc_type_code"
        )
        override_std_rows = run_query(
            "SELECT std_code, iso_num, edition_label FROM standard "
            "WHERE is_active ORDER BY sort_order, std_code"
        )
        if not override_targets or not len(override_std_rows):
            st.info("문서종류 또는 규격 데이터가 없습니다.")
        else:
            ov_doc_choice = st.selectbox(
                "문서종류 선택", override_targets, format_func=lambda x: x[1], key="clause_ov_doc_choice",
            )
            ov_std_options = [
                (r["std_code"], f"{r['std_code']} — {r['iso_num']} {r.get('edition_label') or ''}")
                for _, r in override_std_rows.iterrows()
            ]
            ov_std_choice = st.selectbox(
                "적용할 규격/개정판 선택", ov_std_options, format_func=lambda x: x[1], key="clause_ov_std_choice",
            )

            cur_row = run_query(
                "SELECT clause_ref, clause_ref_overrides FROM doc_type WHERE doc_type_code = %s",
                (ov_doc_choice[0],),
            ).iloc[0]
            cur_overrides = cur_row.get("clause_ref_overrides") or {}
            if isinstance(cur_overrides, str):
                cur_overrides = json.loads(cur_overrides)
            existing_ov = cur_overrides.get(ov_std_choice[0], "__unset__")

            st.caption(
                f"기본 조항번호: {cur_row.get('clause_ref') or '(없음)'} · "
                f"현재 '{ov_std_choice[0]}'에 등록된 예외: "
                + ("없음(기본값 사용)" if existing_ov == "__unset__"
                   else ("해당 조항 없음" if existing_ov is None else existing_ov))
            )

            no_clause = st.checkbox(
                "이 개정판에는 해당 조항이 없음(조항 자체가 없어짐)",
                value=(existing_ov is None and existing_ov != "__unset__"),
                key="clause_ov_no_clause",
            )
            new_clause_val = st.text_input(
                "이 개정판에서의 조항번호(다르면 입력 — 예: 6.1.3). 비워두면 예외를 지웁니다.",
                value="" if (existing_ov in ("__unset__", None)) else str(existing_ov),
                disabled=no_clause,
                key="clause_ov_new_value",
            )
            col_save, col_clear = st.columns(2)
            with col_save:
                if st.button("이 예외 저장", key="clause_ov_save_btn"):
                    if no_clause:
                        cur_overrides[ov_std_choice[0]] = None
                    elif new_clause_val.strip():
                        cur_overrides[ov_std_choice[0]] = new_clause_val.strip()
                    else:
                        cur_overrides.pop(ov_std_choice[0], None)
                    run_write(
                        "UPDATE doc_type SET clause_ref_overrides = %s WHERE doc_type_code = %s",
                        (json.dumps(cur_overrides, ensure_ascii=False), ov_doc_choice[0]),
                    )
                    st.success("저장되었습니다.")
                    st.rerun()
            with col_clear:
                if existing_ov != "__unset__" and st.button("이 예외 삭제(기본값으로 되돌림)", key="clause_ov_clear_btn"):
                    cur_overrides.pop(ov_std_choice[0], None)
                    run_write(
                        "UPDATE doc_type SET clause_ref_overrides = %s WHERE doc_type_code = %s",
                        (json.dumps(cur_overrides, ensure_ascii=False), ov_doc_choice[0]),
                    )
                    st.success("삭제되었습니다.")
                    st.rerun()

    elif tab.startswith("form_pattern"):
        st.dataframe(run_query("SELECT * FROM form_pattern ORDER BY pattern_code"), width="stretch")

    elif tab.startswith("sample_original"):
        st.caption(
            "Original(샘플 입수 소스)의 전체 원본명 마스터입니다. "
            "다른 화면에서는 이름이 길어 번호로만 표시됩니다 — 번호가 가리키는 실제 이름은 여기서 확인하세요."
        )
        st.dataframe(
            run_query("SELECT original_no, original_name FROM sample_original ORDER BY original_no"),
            width="stretch",
        )


# ---------- 2. 사용자 관리 ----------

elif page.startswith("2"):
    st.header("사용자 관리")
    st.caption(
        "회사·신청건을 '사용자 등록' 하나로 통합(실제 회사/샘플 양자택일 지원). "
        "조직도는 신청건별 전용으로 관리하며 '조직 책임과 권한' 화면에서 부서 목록/책임과 권한/"
        "RACI/검증·확정까지 진행합니다."
    )

    sub = st.radio("항목", ["사용자 등록", "조직 책임과 권한"], horizontal=True)

    if sub.startswith("사용자"):
        st.subheader("사용자 목록")
        st.dataframe(
            run_query("""
                SELECT a.application_id AS "No", a.std_code_normalized AS std_code,
                       substring(a.sector_code from 1 for 1) AS "산업",
                       CASE WHEN length(a.sector_code) >= 4
                            THEN a.sector_code END AS "업종",
                       CASE WHEN a.profile_id IS NOT NULL
                            THEN a.sector_code || lpad(sp.profile_seq::text, 2, '0') END AS "프로필",
                       c.company_name AS "Company_name", a.sample_name AS "Sample_name",
                       c.biz_reg_no AS "Biz_reg_No", a.original_no AS "Original",
                       a.org_scale AS "Org.scale", a.status AS "Status", a.created_at,
                       a.superseded_application_id AS "대체한 원본(No)",
                       succ.application_id AS "이 건을 대체한 신청건(No)"
                FROM application a
                LEFT JOIN company c ON c.company_id = a.company_id
                LEFT JOIN sector_profile sp ON sp.profile_id = a.profile_id
                LEFT JOIN application succ ON succ.superseded_application_id = a.application_id
                ORDER BY a.application_id DESC
            """),
            width="stretch",
        )
        st.caption(
            "Original은 번호로 표시됩니다 — 전체 원본명은 [1. 기준정보 조회 → sample_original(Original 현황)]에서 확인하세요. "
            "'대체한 원본(No)'은 이 신청건이 규격 개정 등으로 대체한 이전 신청건, "
            "'이 건을 대체한 신청건(No)'은 반대로 이 신청건을 대체하며 새로 만들어진 신청건입니다."
        )

        expiring = run_query("""
            WITH std_expiry AS (
                SELECT std_code, valid_until FROM standard WHERE valid_until IS NOT NULL
            )
            SELECT a.application_id AS "No", a.project_no, se.std_code AS "만료 예정 규격",
                   se.valid_until AS "유효기한"
            FROM application a
            CROSS JOIN LATERAL jsonb_array_elements_text(a.active_stds) AS std(code)
            JOIN std_expiry se ON se.std_code = std.code
            WHERE se.valid_until >= CURRENT_DATE
              AND se.valid_until <= CURRENT_DATE + INTERVAL '180 days'
              AND NOT EXISTS (
                  SELECT 1 FROM application succ
                  WHERE succ.superseded_application_id = a.application_id
              )
            ORDER BY se.valid_until, a.application_id
        """)
        if len(expiring):
            st.warning(
                f"⚠ 유효기한이 180일 이내로 다가오는데 아직 후속(대체) 신청건이 없는 항목 {len(expiring)}건"
            )
            st.dataframe(expiring, width="stretch")

        with st.expander("🗑 잘못 등록한 신청건 삭제"):
            del_apps = fetch_options(
                "SELECT application_id, application_id || ' - ' || project_no "
                "FROM application ORDER BY application_id DESC"
            )
            if not del_apps:
                st.caption("삭제할 신청건이 없습니다.")
            else:
                del_choice = st.selectbox(
                    "삭제할 신청건 선택", del_apps, format_func=lambda x: x[1], key="del_app_choice"
                )
                confirm_del = st.checkbox("정말 삭제하시겠습니까? (되돌릴 수 없습니다)", key="del_app_confirm")
                if st.button("삭제", key="del_app_btn", disabled=not confirm_del):
                    try:
                        run_write("DELETE FROM application WHERE application_id = %s", (del_choice[0],))
                        st.success(f"{del_choice[1]} 삭제되었습니다.")
                        st.rerun()
                    except Exception as e:
                        if "foreign key" in str(e).lower():
                            st.error(
                                "이미 이 신청건과 연결된 조직도·문서 데이터가 있어 삭제할 수 없습니다. "
                                "먼저 연결된 데이터를 정리한 뒤 다시 시도해주세요."
                            )
                        else:
                            st.error(f"삭제 중 오류: {e}")

        st.divider()
        st.subheader("사용자 등록 / 수정 / 복사")

        load_targets = fetch_options(
            "SELECT application_id, application_id || ' - ' || project_no "
            "FROM application ORDER BY application_id DESC"
        )
        source_choice = st.selectbox(
            "불러올 신청건 선택 — 고르면 아래 양식에 그 내용이 채워집니다",
            [(None, "— 새로 등록(빈 양식) —")] + load_targets,
            format_func=lambda x: x[1],
            key="load_app_choice",
        )

        action_mode = "new"
        if source_choice and source_choice[0]:
            mode_label = st.radio(
                "이 신청건을",
                ["수정(덮어쓰기)", "복사해서 새로 등록"],
                horizontal=True,
                key="load_app_mode",
            )
            action_mode = "edit" if mode_label.startswith("수정") else "copy"

        source_id = source_choice[0] if (source_choice and source_choice[0]) else None
        editing_id = source_id if action_mode == "edit" else None
        key_tag = f"{source_id}_{action_mode}" if source_id else "new"

        existing = None
        if source_id:
            existing = run_query(
                """
                SELECT a.*, c.company_name, c.biz_reg_no
                FROM application a LEFT JOIN company c ON c.company_id = a.company_id
                WHERE a.application_id = %s
                """,
                (source_id,),
            ).iloc[0]
            if action_mode == "edit":
                st.info(f"'{existing['project_no']}' 신청건을 불러왔습니다. 내용을 고친 뒤 저장하세요.")
            else:
                st.info(
                    f"'{existing['project_no']}' 신청건 내용을 복사했습니다. "
                    "필요한 부분만 고쳐서 '신규 등록'하면 새 신청건이 만들어집니다(원본은 그대로 남습니다)."
                )

        default_kind = "실제 회사"
        if existing is not None and pd.notna(existing.get("sample_name")):
            default_kind = "샘플"
        source_kind = st.radio(
            "등록 종류 *", ["실제 회사", "샘플"], horizontal=True,
            index=["실제 회사", "샘플"].index(default_kind),
            key=f"user_reg_kind_{key_tag}",
        )

        original_choice = None
        new_original_name = ""
        if source_kind == "샘플":
            original_options = fetch_options(
                "SELECT original_no, original_no || ' - ' || original_name FROM sample_original "
                "ORDER BY original_no"
            )
            default_original_idx = 0
            if existing is not None and pd.notna(existing.get("original_no")):
                original_ids = [x[0] for x in original_options]
                if int(existing["original_no"]) in original_ids:
                    default_original_idx = original_ids.index(int(existing["original_no"]))
            original_choice = st.selectbox(
                "Original * (샘플 입수 소스 — 목록에서 선택, 없으면 아래에서 새로 등록)",
                original_options + [(NEW_ORIGINAL_SENTINEL, "— 목록에 없음 · 새로 등록 —")],
                index=default_original_idx,
                format_func=lambda x: x[1],
                key=f"user_reg_original_{key_tag}",
            )
            if original_choice[0] == NEW_ORIGINAL_SENTINEL:
                new_original_name = st.text_input(
                    "새 Original 이름 *", key=f"user_reg_new_original_{key_tag}"
                )

        st.markdown(
            "**산업 / 업종 / 프로필** — 산업(대분류)은 필수이고, 정확히 아실수록 업종·프로필까지 "
            "추가로 좁혀서 선택할 수 있습니다(둘 다 선택)."
        )
        sector_mains = fetch_options("SELECT code, code || ' - ' || name FROM sector_main ORDER BY code")
        default_main_idx = 0
        if existing is not None and sector_mains:
            existing_main = str(existing["sector_code"])[:1]
            main_ids = [x[0] for x in sector_mains]
            if existing_main in main_ids:
                default_main_idx = main_ids.index(existing_main)
        if not sector_mains:
            st.warning("등록된 산업(대분류)이 없습니다.")
            sector_main_choice = None
        else:
            sector_main_choice = st.selectbox(
                "산업(대분류) *", sector_mains, format_func=lambda x: x[1],
                index=default_main_idx, key=f"user_reg_main_{key_tag}",
            )

        iaf_options = []
        if sector_main_choice:
            iaf_options = fetch_options(
                "SELECT DISTINCT sector_code, sector_code || ' - ' || sector_name "
                "FROM sector_profile WHERE sector_main = %s ORDER BY sector_code",
                (sector_main_choice[0],),
            )
        default_iaf_idx = 0
        if existing is not None and len(str(existing["sector_code"])) >= 4:
            iaf_ids = [None] + [x[0] for x in iaf_options]
            if existing["sector_code"] in iaf_ids:
                default_iaf_idx = iaf_ids.index(existing["sector_code"])
        iaf_choice = st.selectbox(
            "업종(업종코드) — 선택",
            [(None, "— 선택 안 함 —")] + iaf_options,
            format_func=lambda x: x[1],
            index=default_iaf_idx,
            key=f"user_reg_iaf_{key_tag}",
            disabled=not sector_main_choice,
        )

        profile_options = []
        if iaf_choice and iaf_choice[0]:
            profile_options = fetch_options(
                "SELECT profile_id, 'seq ' || profile_seq || CASE WHEN is_default THEN ' (기본)' ELSE '' END "
                "FROM sector_profile WHERE sector_code = %s ORDER BY profile_seq",
                (iaf_choice[0],),
            )
        default_profile_idx = 0
        if existing is not None and pd.notna(existing.get("profile_id")):
            profile_ids = [None] + [x[0] for x in profile_options]
            if int(existing["profile_id"]) in profile_ids:
                default_profile_idx = profile_ids.index(int(existing["profile_id"]))
        profile_choice = st.selectbox(
            "프로필(세부) — 선택",
            [(None, "— 선택 안 함 —")] + profile_options,
            format_func=lambda x: x[1],
            index=default_profile_idx,
            key=f"user_reg_profile_{key_tag}",
            disabled=not (iaf_choice and iaf_choice[0]),
        )

        with st.form(f"add_user_{key_tag}"):
            if source_kind == "실제 회사":
                company_name_in = st.text_input(
                    "회사명 *", value="" if existing is None else (existing.get("company_name") or "")
                )
                biz_reg_no_in = st.text_input(
                    "사업자등록번호 * (예: 111-11-11111, 이미 등록된 번호면 그 회사에 신청건만 추가됩니다)",
                    value="" if existing is None else (existing.get("biz_reg_no") or ""),
                )
                sample_name_in = ""
            else:
                sample_name_in = st.text_input(
                    "샘플명 *", value="" if existing is None else (existing.get("sample_name") or "")
                )
                if original_choice and original_choice[0] != NEW_ORIGINAL_SENTINEL:
                    st.markdown(f"**Original**\n\n`{original_choice[1]}`")
                elif new_original_name.strip():
                    st.markdown(f"**Original(신규 등록 예정)**\n\n`{new_original_name.strip()}`")
                company_name_in, biz_reg_no_in = "", ""

            # 규격 선택 — 2026-09-18: 하드코딩 7종 콤보 대신 standard 테이블 기반 다중선택.
            # "수정" 모드에서는 규격/개정판 변경을 막는다 — 규격 개정(예: 2026년판 전환)은
            # 기존 프로젝트를 고치는 게 아니라 "복사해서 새로 등록"으로 새 프로젝트를
            # 만드는 일이기 때문(사용자 확정 워크플로우).
            standards_df = _fetch_active_standards()
            today = date.today()
            existing_active_stds = (
                _as_list(existing.get("active_stds")) if existing is not None else []
            )
            supersede_source_id = None

            if action_mode == "edit":
                st.multiselect(
                    "규격 선택 * (수정 화면에서는 변경할 수 없습니다 — 규격/개정판을 바꾸려면 "
                    "위에서 '복사해서 새로 등록'을 선택하세요. 규격 개정은 기존 프로젝트 수정이 "
                    "아니라 새 프로젝트 등록으로 처리합니다.)",
                    options=existing_active_stds,
                    default=existing_active_stds,
                    disabled=True,
                    key=f"user_reg_std_locked_{key_tag}",
                )
                selected_std_codes = existing_active_stds
            else:
                selectable_codes = []
                std_labels = {}
                for _, srow in standards_df.iterrows():
                    code = srow["std_code"]
                    expired = pd.notna(srow.get("valid_until")) and srow["valid_until"] < today
                    if expired:
                        continue
                    selectable_codes.append(code)
                    std_labels[code] = _standard_label(srow, today)
                default_codes = [c for c in existing_active_stds if c in selectable_codes]
                dropped_codes = [c for c in existing_active_stds if c not in selectable_codes]
                selected_std_codes = st.multiselect(
                    "규격 선택 * (하나 이상 — 통합경영시스템은 여러 개 선택)",
                    options=selectable_codes,
                    default=default_codes,
                    format_func=lambda c: std_labels.get(c, c),
                    key=f"user_reg_std_pick_{key_tag}",
                )
                if dropped_codes:
                    st.caption(
                        f"원본에 있던 {', '.join(dropped_codes)}은(는) 유효기간이 지나 "
                        "선택 목록에서 빠졌습니다."
                    )
                if action_mode == "copy" and existing is not None:
                    if st.checkbox(
                        f"이 신청건이 '{existing['project_no']}'(원본)을 대체합니다 "
                        "(규격 개정 등으로 새로 만드는 경우 — 체크하면 원본과 연결되어 "
                        "이력 추적에 표시됩니다)",
                        value=True,
                        key=f"user_reg_supersede_{key_tag}",
                    ):
                        supersede_source_id = source_id

            default_scale_idx = (
                ORG_SCALE_OPTIONS.index(existing["org_scale"])
                if existing is not None and existing.get("org_scale") in ORG_SCALE_OPTIONS
                else 0
            )
            org_scale_choice = st.selectbox(
                "직원수 규모(Org.scale) *", ORG_SCALE_OPTIONS, index=default_scale_idx
            )
            st.caption(
                "조직도(부서 목록·책임과 권한)는 등록 후 [조직 책임과 권한] 화면에서 "
                "이 신청건 전용으로 만들거나 비슷한 신청건에서 복사해올 수 있습니다."
            )

            submit_label = "수정 저장" if action_mode == "edit" else "신규 등록"
            if st.form_submit_button(submit_label):
                errors = []
                if source_kind == "실제 회사":
                    if not company_name_in.strip():
                        errors.append("회사명은 필수입니다.")
                    if not biz_reg_no_in.strip():
                        errors.append("사업자등록번호는 필수입니다.")
                    elif not re.match(r"^\d{3}-\d{2}-\d{5}$", biz_reg_no_in.strip()):
                        errors.append("사업자등록번호는 111-11-11111 형식으로 입력해주세요.")
                else:
                    if not sample_name_in.strip():
                        errors.append("샘플명은 필수입니다.")
                    has_existing_original = bool(
                        original_choice and original_choice[0] != NEW_ORIGINAL_SENTINEL
                    )
                    has_new_original = bool(new_original_name.strip())
                    if not (has_existing_original or has_new_original):
                        errors.append("Original(샘플 소스명)을 선택하거나 새로 입력해주세요.")

                if not sector_main_choice:
                    errors.append("산업(대분류)을 선택해주세요.")

                if not selected_std_codes:
                    errors.append("규격을 최소 1개 선택해주세요.")

                if errors:
                    for msg in errors:
                        st.error(msg)
                else:
                    std_norm = build_std_combo(selected_std_codes, standards_df)
                    active_stds = selected_std_codes
                    profile_id = None

                    if profile_choice and profile_choice[0]:
                        profile_id = profile_choice[0]
                        row = run_query(
                            "SELECT sector_code, profile_seq FROM sector_profile WHERE profile_id = %s",
                            (profile_id,),
                        )
                        sector_code = row.iloc[0]["sector_code"]
                        profile_seq = int(row.iloc[0]["profile_seq"])
                        sector_suffix = f"{sector_code}{profile_seq:02d}"
                    elif iaf_choice and iaf_choice[0]:
                        sector_code = iaf_choice[0]
                        sector_suffix = sector_code
                    else:
                        # 대분류만 확정되고 업종/프로필이 미정인 경우 — placeholder 코드를
                        # "{대분류}00z{seq:02d}" 형태로 부여한다(예: M00z01, C00z02).
                        # "00"은 미정 IAF번호, "z"는 미정 세분류를 뜻하며, 실제 IAF 코드
                        # 체계에서는 쓰이지 않는 조합이라 충돌 위험이 없다(2026-09-17,
                        # IAF_sector_profile.csv 117건 전수 분석으로 확인 — IAF번호는
                        # 01~39만 사용, 세분류는 각 대분류별 a~o 범위 내에서만 쓰이고
                        # z는 어떤 대분류에도 쓰이지 않음). application.sector_code는
                        # FK 없는 varchar(10)이라 스키마 변경도 필요 없다.
                        placeholder_prefix = f"{sector_main_choice[0]}00z"
                        existing_is_same_placeholder = (
                            editing_id is not None
                            and existing is not None
                            and str(existing.get("sector_code", "")).startswith(placeholder_prefix)
                            and pd.isna(existing.get("profile_id"))
                        )
                        if existing_is_same_placeholder:
                            # 수정 모드에서 기존에도 같은 대분류의 "미정" 상태였다면
                            # 번호를 새로 매기지 않고 기존 값을 그대로 유지한다.
                            sector_code = existing["sector_code"]
                        else:
                            # 신규 등록이거나, 다른 분류에서 "미정"으로 재분류된 경우
                            # 새 번호를 매긴다(해당 대분류의 미정 코드 개수 + 1).
                            cnt_query = (
                                "SELECT COUNT(*) AS n FROM application WHERE sector_code LIKE %s"
                            )
                            cnt_params = [f"{placeholder_prefix}%"]
                            if editing_id:
                                cnt_query += " AND application_id != %s"
                                cnt_params.append(editing_id)
                            cnt_row = run_query(cnt_query, tuple(cnt_params))
                            next_seq = int(cnt_row.iloc[0]["n"]) + 1
                            sector_code = f"{placeholder_prefix}{next_seq:02d}"
                        sector_suffix = sector_code

                    if source_kind == "실제 회사":
                        match = run_query(
                            "SELECT company_id FROM company WHERE biz_reg_no = %s", (biz_reg_no_in.strip(),)
                        )
                        if len(match):
                            company_id = int(match.iloc[0]["company_id"])
                            if editing_id and pd.notna(existing.get("company_id")) \
                                    and int(existing["company_id"]) == company_id:
                                run_write(
                                    "UPDATE company SET company_name = %s WHERE company_id = %s",
                                    (company_name_in.strip(), company_id),
                                )
                        elif editing_id and pd.notna(existing.get("company_id")):
                            # 수정 모드이고 사업자등록번호를 새 값으로 바꾼 경우: 기존에 연결된
                            # 회사 레코드 자체를 갱신(같은 회사의 다른 신청건들도 함께 갱신됨).
                            company_id = int(existing["company_id"])
                            run_write(
                                "UPDATE company SET company_name = %s, biz_reg_no = %s WHERE company_id = %s",
                                (company_name_in.strip(), biz_reg_no_in.strip(), company_id),
                            )
                        else:
                            conn = _engine_conn()
                            with conn:
                                with conn.cursor() as cur:
                                    cur.execute(
                                        "INSERT INTO company (company_name, biz_reg_no) VALUES (%s, %s) "
                                        "RETURNING company_id",
                                        (company_name_in.strip(), biz_reg_no_in.strip()),
                                    )
                                    company_id = cur.fetchone()[0]
                        sample_name_val = None
                        original_no_val = None
                        name_for_project_no = company_name_in.strip()
                    else:
                        company_id = None
                        sample_name_val = sample_name_in.strip()
                        if original_choice and original_choice[0] != NEW_ORIGINAL_SENTINEL:
                            original_no_val = original_choice[0]
                            original_name_for_display = original_choice[1].split(" - ", 1)[-1]
                        else:
                            original_no_val = _resolve_or_create_original(new_original_name)
                            original_name_for_display = new_original_name.strip()
                        name_for_project_no = f"{sample_name_val}({original_name_for_display})"

                    project_no = f"{std_norm}{sector_suffix}_{name_for_project_no}"

                    try:
                        if editing_id:
                            # 수정 모드는 규격/개정판을 바꿀 수 없으므로(위 multiselect가
                            # disabled) superseded_application_id는 건드리지 않는다.
                            run_write(
                                """
                                UPDATE application SET
                                    company_id = %s, sample_name = %s, original_no = %s,
                                    project_no = %s, std_code_normalized = %s, active_stds = %s,
                                    sector_code = %s, profile_id = %s, org_scale = %s
                                WHERE application_id = %s
                                """,
                                (company_id, sample_name_val, original_no_val, project_no,
                                 std_norm, json.dumps(active_stds, ensure_ascii=False), sector_code, profile_id,
                                 org_scale_choice, editing_id),
                            )
                            st.success(f"수정되었습니다. (project_no: {project_no})")
                        else:
                            run_write(
                                """
                                INSERT INTO application
                                    (company_id, sample_name, original_no, project_no,
                                     std_code_normalized, active_stds, sector_code, profile_id,
                                     org_scale, superseded_application_id)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                                """,
                                (company_id, sample_name_val, original_no_val, project_no,
                                 std_norm, json.dumps(active_stds, ensure_ascii=False), sector_code, profile_id,
                                 org_scale_choice, supersede_source_id),
                            )
                            if supersede_source_id:
                                st.success(
                                    f"등록되었습니다. (project_no: {project_no}) — "
                                    f"기존 신청건 #{supersede_source_id}을(를) 대체하는 것으로 기록했습니다."
                                )
                            else:
                                st.success(f"등록되었습니다. (project_no: {project_no})")
                        st.session_state.pop("load_app_choice", None)
                        st.session_state.pop("load_app_mode", None)
                        st.rerun()
                    except Exception as e:
                        if "duplicate key" in str(e).lower():
                            st.error(
                                "이미 같은 project_no(규격+업종+이름 조합)를 가진 신청건이 있습니다. "
                                "복사한 경우라면 규격·업종·이름 중 하나를 바꿔서 다시 시도해주세요."
                            )
                        else:
                            st.error(f"저장 중 오류: {e}")

    elif sub.startswith("조직 책임과 권한"):
        st.subheader("신청건 선택")
        app_targets = fetch_options(
            "SELECT application_id, application_id || ' - ' || project_no "
            "FROM application ORDER BY application_id DESC"
        )
        if not app_targets:
            st.info("먼저 '사용자 등록'에서 신청건을 등록해주세요.")
        else:
            app_choice = st.selectbox(
                "신청건 선택 — 이 신청건의 부서 목록/책임과 권한을 관리합니다",
                app_targets, format_func=lambda x: x[1], key="orgrr_app_choice",
            )
            app_id = app_choice[0]
            app_row = run_query("SELECT * FROM application WHERE application_id = %s", (app_id,)).iloc[0]
            org_scale = app_row.get("org_scale")
            org_rr_status = app_row.get("org_rr_status") or "미시작"

            org_chart_row = run_query(
                "SELECT org_chart_id FROM org_chart WHERE application_id = %s", (app_id,)
            )

            if len(org_chart_row) == 0:
                st.info(
                    f"'{app_row['project_no']}' 신청건에는 아직 부서 목록이 없습니다. "
                    "아래에서 자동생성하거나, 비슷한 신청건에서 복사해서 시작하세요."
                )
                start_mode = st.radio(
                    "시작 방법", ["자동생성(빈 조직도)", "복사(유사 신청건에서 가져오기)"],
                    horizontal=True, key=f"orgrr_start_mode_{app_id}",
                )
                if start_mode.startswith("자동생성"):
                    master_df = run_query(
                        "SELECT dept_code, dept_name, category_name, relevant_std FROM dept_master "
                        "ORDER BY category_seq, dept_code"
                    )
                    active_stds = set(_std_families(app_row.get("active_stds")))

                    def _is_recommended(rel_std):
                        rel = _as_list(rel_std)
                        return (not rel) or bool(set(rel) & active_stds)

                    master_df["추천"] = master_df["relevant_std"].apply(_is_recommended)
                    option_codes = master_df["dept_code"].tolist()
                    default_codes = master_df.loc[master_df["추천"], "dept_code"].tolist()
                    labels = {
                        r.dept_code: f"{r.dept_code} — {r.dept_name} ({r.category_name})"
                        for r in master_df.itertuples()
                    }
                    st.caption(
                        "std_code·업종·규모에 맞는 부서가 기본 선택되어 있습니다. 자유롭게 추가/해제한 뒤 생성하세요."
                    )
                    selected_codes = st.multiselect(
                        "포함할 부서 선택 (조직 마스터 DB 기준)",
                        option_codes, default=default_codes,
                        format_func=lambda c: labels[c], key=f"orgrr_auto_sel_{app_id}",
                    )
                    if st.button("선택한 부서로 초안 생성", key=f"orgrr_create_{app_id}"):
                        new_org_chart_id = run_insert_returning(
                            "INSERT INTO org_chart (org_chart_name, application_id, industry_tag, company_size_tag) "
                            "VALUES (%s, %s, %s, %s) RETURNING org_chart_id",
                            (f"{app_row['project_no']} 조직도", int(app_id),
                             str(app_row.get("sector_code")) if pd.notna(app_row.get("sector_code")) else None,
                             org_scale),
                        )
                        for code in selected_codes:
                            dept_name = master_df.loc[master_df["dept_code"] == code, "dept_name"].iloc[0]
                            run_write(
                                "INSERT INTO org_chart_role (org_chart_id, role_name, dept_code, seq) "
                                "VALUES (%s, %s, %s, 0)",
                                (new_org_chart_id, dept_name, code),
                            )
                        run_write(
                            "UPDATE application SET org_rr_status = '초안' WHERE application_id = %s", (app_id,)
                        )
                        st.success(f"부서 {len(selected_codes)}건으로 조직도 초안이 생성되었습니다. 이제 [1] 부서 목록에서 이어서 작성하세요.")
                        st.rerun()
                else:
                    candidates = run_query(
                        """
                        SELECT a.application_id, a.project_no, a.std_code_normalized, a.sector_code,
                               a.org_scale, oc.org_chart_id,
                               (CASE WHEN a.std_code_normalized = %s THEN 1 ELSE 0 END
                                + CASE WHEN a.sector_code = %s THEN 1 ELSE 0 END
                                + CASE WHEN substring(a.sector_code from 1 for 1) = substring(%s from 1 for 1) THEN 1 ELSE 0 END
                                + CASE WHEN a.org_scale = %s THEN 1 ELSE 0 END) AS similarity
                        FROM application a
                        JOIN org_chart oc ON oc.application_id = a.application_id
                        WHERE a.application_id != %s
                        ORDER BY similarity DESC, a.application_id DESC
                        """,
                        (app_row.get("std_code_normalized"), app_row.get("sector_code"),
                         app_row.get("sector_code") or "", org_scale, app_id),
                    )
                    if len(candidates) == 0:
                        st.caption("복사할 수 있는(부서 목록이 이미 있는) 신청건이 없습니다. 자동생성을 이용해주세요.")
                    else:
                        copy_options = [
                            (int(r.org_chart_id), int(r.application_id),
                             f"{r.project_no} (std={r.std_code_normalized}, 업종={r.sector_code}, 규모={r.org_scale}) "
                             f"— 유사도 {int(r.similarity)}/4")
                            for r in candidates.itertuples()
                        ]
                        copy_choice = st.selectbox(
                            "복사할 신청건 선택 — 유사한 조건 순으로 정렬됩니다",
                            copy_options, format_func=lambda x: x[2], key=f"orgrr_copy_choice_{app_id}",
                        )
                        if st.button("이 신청건의 부서 목록/책임과 권한 복사", key=f"orgrr_copy_btn_{app_id}"):
                            src_org_chart_id = copy_choice[0]
                            new_org_chart_id = run_insert_returning(
                                "INSERT INTO org_chart (org_chart_name, application_id, industry_tag, company_size_tag) "
                                "VALUES (%s, %s, %s, %s) RETURNING org_chart_id",
                                (f"{app_row['project_no']} 조직도", int(app_id),
                                 str(app_row.get("sector_code")) if pd.notna(app_row.get("sector_code")) else None,
                                 org_scale),
                            )
                            src_roles = run_query(
                                "SELECT * FROM org_chart_role WHERE org_chart_id = %s ORDER BY seq, role_id",
                                (src_org_chart_id,),
                            )
                            role_id_map = {}
                            for r_ in src_roles.itertuples():
                                new_role_id = run_insert_returning(
                                    "INSERT INTO org_chart_role "
                                    "(org_chart_id, role_name, department, dept_code, mission, seq) "
                                    "VALUES (%s, %s, %s, %s, %s, %s) RETURNING role_id",
                                    (new_org_chart_id, r_.role_name, r_.department,
                                     getattr(r_, "dept_code", None), r_.mission, int(r_.seq)),
                                )
                                role_id_map[int(r_.role_id)] = new_role_id
                            for r_ in src_roles.itertuples():
                                if pd.notna(r_.parent_role_id):
                                    run_write(
                                        "UPDATE org_chart_role SET parent_role_id = %s WHERE role_id = %s",
                                        (role_id_map.get(int(r_.parent_role_id)), role_id_map[int(r_.role_id)]),
                                    )
                            src_resp = (
                                run_query(
                                    "SELECT * FROM dept_responsibility WHERE role_id = ANY(%s)",
                                    (list(role_id_map.keys()),),
                                )
                                if role_id_map else pd.DataFrame()
                            )
                            for r_ in src_resp.itertuples():
                                run_write(
                                    "INSERT INTO dept_responsibility "
                                    "(role_id, category, seq, content, authority_criteria, basis_doc, required_competency) "
                                    "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                                    (role_id_map[int(r_.role_id)], r_.category, int(r_.seq), r_.content,
                                     r_.authority_criteria, r_.basis_doc, r_.required_competency),
                                )
                            run_write(
                                "UPDATE application SET org_rr_status = '초안' WHERE application_id = %s", (app_id,)
                            )
                            st.success(
                                f"{len(src_roles)}개 부서, {len(src_resp)}개 책임/권한 항목을 복사했습니다. "
                                "related_step_id(관련 프로세스)와 RACI는 이 신청건의 프로세스맵에 맞춰 다시 지정해주세요."
                            )
                            st.rerun()
            else:
                org_chart_id = int(org_chart_row.iloc[0]["org_chart_id"])
                st.caption(f"현재 상태(org_rr_status): {org_rr_status}")
                step = st.radio(
                    "단계", ["1.부서목록", "2.RACI매트릭스", "3.검증 및 확정"],
                    horizontal=True, key=f"orgrr_step_{app_id}",
                )
                st.divider()
                if step.startswith("1."):
                    _render_dept_and_resp(org_chart_id, app_id)
                elif step.startswith("2."):
                    _render_raci(org_chart_id, app_id, org_scale)
                else:
                    _render_verify_confirm(org_chart_id, app_id)


# ---------- 3. 문서관리 ----------

elif page.startswith("3"):
    st.header("문서관리")
    tab1, tab2 = st.tabs(["문서관리", "분류문서 보기"])

    # ===== 탭1: 신청건별 문서관리 =====
    with tab1:
        app_targets = fetch_options(
            "SELECT application_id, application_id || ' - ' || project_no "
            "FROM application ORDER BY application_id DESC"
        )
        if not app_targets:
            st.info("먼저 [사용자 관리 → 사용자 등록]에서 신청건을 등록해주세요.")
        else:
            app_choice = st.selectbox(
                "신청건 선택", app_targets, format_func=lambda x: x[1], key="doc_mgmt_app_choice"
            )
            app_id = app_choice[0]
            info = _application_header(app_id)
            # 2026-09-18: active_stds가 대소문자로 개정판을 구분(예: "Q"=2026년판)하므로
            # doc_type.applicable_std(소문자만) 매칭용으로는 _std_families()로 소문자화한다.
            active_stds = _std_families(info["active_stds"])
            app_std = info["std_code_normalized"]
            project_no = info["project_no"]
            is_company = pd.notna(info.get("company_name"))
            name_display = info["company_name"] if is_company else info["sample_name"]
            name_label = "Company name" if is_company else "Sample name"
            original_display = (
                f'{int(info["original_no"])} - {info["original_name"]}'
                if pd.notna(info.get("original_no")) else "—"
            )
            # 정식 프로젝트명 = "신청건 번호-프로필코드"(예: "1-qM18c04"). project_no는
            # 내부적으로 "{프로필코드}_{회사명/샘플명}" 형태로 저장돼 있으므로(예:
            # "qM18c04_ABC comapny"), 첫 "_" 앞부분만 잘라내면 프로필코드가 그대로
            # 나온다(2026-09-13, "프로필"→"프로젝트명" 표시 변경 — GCS 저장에 쓰이는
            # project_no 실제 값 자체는 바꾸지 않음, 순수 표시 로직만 변경).
            profile_code = str(project_no).split("_", 1)[0]
            project_name_display = f"{app_id}-{profile_code}"
            st.markdown(
                f"**프로젝트명**: {project_name_display}  \n"
                f"**{name_label}**: {name_display}  \n"
                f"**Original**: {original_display}"
            )
            # 업로드 시 다른 신청건과 혼동하는 사고를 막기 위해, 아래 업로드
            # 위젯들 옆에 반복해서 표시할 배지(2026-09-13, "신청건 선택 안전장치"
            # 논의 결과 — 풀세트 폴더 자동생성 대신 채택한 경량 대안).
            project_badge = f"📁 현재 신청건: **{project_no} — {name_display}**"

            st.divider()
            st.subheader("매뉴얼/절차서/양식")
            list_toggle = st.radio(
                "구분", ["매뉴얼/절차서", "양식"], horizontal=True, key="doc_mgmt_list_toggle"
            )
            list_cats = ["manual", "procedure"] if list_toggle == "매뉴얼/절차서" else ["form"]
            list_df = _annotate_doc_list(_doc_list_for_application(app_id, list_cats, active_stds))
            display_cols = ["doc_type_code", "revision_no", "패턴", "doc_type_name",
                             "clause_ref", "applicable_label", "applicable_std_표시", "비고"]
            if list_toggle == "양식":
                display_cols.insert(2, "form_seq_no")
            st.dataframe(
                list_df[display_cols].rename(columns={
                    "doc_type_code": "doc_code/Form No", "revision_no": "Rev.No",
                    "doc_type_name": "절차서(매뉴얼)명/양식명", "clause_ref": "관련 ISO 조항",
                    "applicable_label": "적용구분", "applicable_std_표시": "applicable_std",
                    "form_seq_no": "양식번호",
                }),
                width="stretch",
            )

            st.subheader("지침서")
            guide_df = _annotate_doc_list(_doc_list_for_application(app_id, ["guideline"], active_stds))
            if len(guide_df) == 0:
                st.caption("적용 규격에 해당하는 지침서가 없습니다.")
            else:
                st.dataframe(
                    guide_df[["doc_type_code", "revision_no", "subcategory", "subcategory_group",
                              "subcategory_letter", "doc_type_name", "clause_ref", "applicable_label",
                              "applicable_std_표시", "비고"]].rename(columns={
                        "doc_type_code": "doc_code", "revision_no": "Rev.No", "subcategory": "중분류",
                        "subcategory_group": "세분류", "subcategory_letter": "세분류문자",
                        "doc_type_name": "지침서명", "clause_ref": "관련 ISO 조항",
                        "applicable_label": "적용구분", "applicable_std_표시": "applicable_std",
                    }),
                    width="stretch",
                )

            st.divider()
            st.subheader("⬆ 일괄 업로드 (여러 파일 한번에)")
            st.caption(
                "여러 곳에 흩어져 있는 문서 파일들을 한 번에 선택해서 올리면, 파일명에서 "
                "표시기호(doc_type_code)를 자동 인식해 각각 등록합니다 — 매뉴얼/절차서/양식/"
                "지침서 완성본은 물론 내용본까지 전부 이 한 곳에서 처리합니다. 통합본을 한글에서 "
                "수작업으로 나눈 결과물이든, 아래 [✂ 문서분리]로 만들어진 개별 파일이든, 원래부터 "
                "개별 파일이었든 그대로 올리면 됩니다. 자동 인식이 안 되면 아래에서 직접 문서종류를 "
                "지정할 수 있습니다."
            )
            st.caption(project_badge)
            batch_is_content = st.checkbox(
                "이 파일들은 완성본이 아니라 내용본입니다 (완성본이 이미 등록된 문서만 처리됨)",
                key="doc_batch_is_content",
            )
            batch_files = st.file_uploader(
                "파일 여러 개 선택 (.hwp/.hwpx)", type=["hwp", "hwpx"],
                accept_multiple_files=True, key="doc_integrate_batch_uploader",
            )
            if batch_files:
                auto_codes = {
                    f.name: hwp_split.extract_doc_type_code_from_filename(f.name) for f in batch_files
                }
                preview_df = pd.DataFrame(
                    [{"파일명": n, "인식된 doc_type_code": c or "(자동인식 실패)"}
                     for n, c in auto_codes.items()]
                )
                st.dataframe(preview_df, width="stretch")

                unresolved = [f for f in batch_files if not auto_codes[f.name]]
                manual_map = {}
                if unresolved:
                    st.warning(
                        f"{len(unresolved)}건은 파일명에서 문서종류를 자동 인식하지 못했습니다. "
                        "아래에서 직접 지정하거나, 건너뛸 수 있습니다."
                    )
                    dt_all = run_query(
                        "SELECT doc_type_id, doc_type_code, doc_type_name FROM doc_type "
                        "WHERE category IN ('manual','procedure','form','guideline') "
                        "AND applicable_std ?| %s "
                        "ORDER BY (substring(doc_type_code from '\\d+'))::int, doc_type_code",
                        (active_stds or ["q", "e", "hs"],),
                    )
                    dt_options = [
                        (int(r.doc_type_id), f"{r.doc_type_code} — {r.doc_type_name}")
                        for r in dt_all.itertuples()
                    ]
                    for f in unresolved:
                        choice = st.selectbox(
                            f"'{f.name}' → 문서종류 지정", options=[None] + dt_options,
                            format_func=lambda x: "(건너뛰기)" if x is None else x[1],
                            key=f"doc_integrate_batch_map_{f.name}",
                        )
                        if choice:
                            manual_map[f.name] = choice[0]

                if st.button("일괄 등록", key="doc_integrate_batch_register"):
                    registered, skipped, registered_paths = 0, [], []
                    for f in batch_files:
                        code = auto_codes[f.name]
                        doc_type_id, category, dt_code = None, None, code
                        if code:
                            dt_row = run_query(
                                "SELECT doc_type_id, category FROM doc_type WHERE doc_type_code = %s",
                                (code,),
                            )
                            if len(dt_row):
                                doc_type_id = int(dt_row.iloc[0]["doc_type_id"])
                                category = dt_row.iloc[0]["category"]
                        elif f.name in manual_map:
                            doc_type_id = manual_map[f.name]
                            dt_row = run_query(
                                "SELECT category, doc_type_code FROM doc_type WHERE doc_type_id = %s",
                                (doc_type_id,),
                            )
                            category = dt_row.iloc[0]["category"]
                            dt_code = dt_row.iloc[0]["doc_type_code"]

                        if doc_type_id is None:
                            skipped.append(f"{f.name}(문서종류 미지정)")
                            continue

                        fmt = f.name.rsplit(".", 1)[-1].lower()
                        storage_category = category_for_doc_type(category, batch_is_content)

                        if batch_is_content:
                            existing = run_query(
                                "SELECT doc_id FROM document_individual "
                                "WHERE application_id=%s AND doc_type_id=%s",
                                (app_id, doc_type_id),
                            )
                            if len(existing) == 0:
                                skipped.append(f"{f.name}(완성본 미등록이라 내용본 불가)")
                                continue
                            storage_path = build_storage_path(
                                app_std, project_no, storage_category, dt_code, 1, fmt
                            )
                            gcs_storage.upload_bytes(storage_path, f.getvalue())
                            _upsert_document_content(int(existing.iloc[0]["doc_id"]), fmt, storage_path)
                        else:
                            existing_doc_id, next_rev = _next_individual_revision(app_id, doc_type_id)
                            storage_path = build_storage_path(
                                app_std, project_no, storage_category, dt_code, next_rev, fmt,
                            )
                            gcs_storage.upload_bytes(storage_path, f.getvalue())
                            _upsert_document_individual(
                                app_id, doc_type_id, next_rev, fmt, storage_path, None, existing_doc_id
                            )
                        registered += 1
                        registered_paths.append({"파일명": f.name, "저장 위치": storage_path})
                    msg = f"{registered}건 등록 완료 → {project_no} ({name_display})"
                    if skipped:
                        msg += f", {len(skipped)}건 건너뜀({', '.join(skipped)})"
                    st.success(msg)
                    if registered_paths:
                        st.dataframe(pd.DataFrame(registered_paths), width="stretch")
                    st.rerun()

            st.divider()
            st.subheader("⬇ 일괄 다운로드 (zip)")
            st.caption("이 신청건에 저장된 문서 파일 전체(또는 선택한 구분만)를 zip 하나로 받습니다.")
            dl_cat_labels = {"manual": "매뉴얼", "procedure": "절차서", "form": "양식", "guideline": "지침서"}
            dl_categories = st.multiselect(
                "포함할 구분", list(dl_cat_labels), default=list(dl_cat_labels),
                format_func=lambda c: dl_cat_labels[c], key="doc_bulk_dl_categories",
            )
            dl_include_content = st.checkbox("내용본도 포함", value=True, key="doc_bulk_dl_include_content")
            bulk_dl_key = f"doc_bulk_dl_zip_{app_id}"
            if st.button("일괄 다운로드 준비", key="doc_bulk_dl_prep", disabled=not dl_categories):
                zip_docs_df = _doc_list_for_application(app_id, dl_categories, active_stds)
                buf = io.BytesIO()
                file_count = 0
                with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                    for row in zip_docs_df.itertuples():
                        if pd.notna(row.individual_storage_path):
                            data = gcs_storage.download_bytes(row.individual_storage_path)
                            zf.writestr("/".join(row.individual_storage_path.split("/")[2:]), data)
                            file_count += 1
                        if dl_include_content and pd.notna(row.content_storage_path):
                            data = gcs_storage.download_bytes(row.content_storage_path)
                            zf.writestr("/".join(row.content_storage_path.split("/")[2:]), data)
                            file_count += 1
                if file_count == 0:
                    st.warning("선택한 조건에 해당하는 저장된 파일이 없습니다.")
                else:
                    st.session_state[bulk_dl_key] = buf.getvalue()
                    st.success(f"{file_count}개 파일을 zip으로 묶었습니다. 아래에서 저장하세요.")
            if bulk_dl_key in st.session_state:
                st.download_button(
                    "zip 파일 저장", data=st.session_state[bulk_dl_key],
                    file_name=f"{project_no}_documents.zip", key="doc_bulk_dl_save",
                )

            st.divider()
            st.subheader("✂ 문서분리 (통합본 → 개별, 기준표 불필요)")
            st.caption(
                "통합 HWP 파일 하나를 업로드하면, 이 신청건에 이미 등록된 문서 목록(코드+명칭) "
                "순서를 기준으로 '가상 분리기준표'를 자동 생성해 문서별로 잘라냅니다 — 분리기준표 "
                "xlsx를 따로 준비할 필요가 없습니다. 다만 통합본 안의 실제 순서가 아래 목록 순서와 "
                "다르면 잘못 잘릴 수 있으니, 필요하면 순서를 고치거나 이번엔 뺄 문서를 체크 "
                "해제하세요. 분리 결과는 성공한 항목만 자동으로 [일괄 업로드]와 같은 방식으로 "
                "바로 등록됩니다. ★ 한글(한컴오피스)이 설치·로그인된 Windows PC에서만 실제 "
                "분리가 동작합니다."
            )
            split_candidates_df = _doc_list_for_application(
                app_id, ["manual", "procedure", "form"], active_stds
            )
            split_candidates_df = split_candidates_df[split_candidates_df["doc_type_code"].notna()]
            if len(split_candidates_df) == 0:
                st.info("적용 규격에 해당하는 매뉴얼/절차서/양식이 없습니다.")
            else:
                split_order_df = pd.DataFrame({
                    "순서": range(1, len(split_candidates_df) + 1),
                    "포함": True,
                    "구분": split_candidates_df["category"].map(
                        lambda c: "양식" if c == "form" else "절차서"
                    ).values,
                    "코드": split_candidates_df["doc_type_code"].values,
                    "문서명": split_candidates_df["doc_type_name"].values,
                })
                edited_order_df = st.data_editor(
                    split_order_df, key="doc_split_order_editor", width="stretch",
                    disabled=["구분", "코드", "문서명"], hide_index=True,
                )
                st.caption(project_badge)
                split_master_upload = st.file_uploader(
                    "통합 HWP 파일", type=["hwp", "hwpx"], key="doc_split_master_uploader",
                )
                anchor_mode = st.radio(
                    "찾기 기준 텍스트", ["both", "title", "code"], horizontal=True,
                    format_func=lambda m: {
                        "both": "문서명 우선 + 실패시 코드(권장)",
                        "title": "문서명/양식명 텍스트만",
                        "code": "표시기호 코드 텍스트만",
                    }[m],
                    key="doc_split_anchor_mode",
                )
                split_visible = st.checkbox(
                    "한글 창을 화면에 표시하며 실행 (디버깅용, 느림)", value=True,
                    key="doc_split_visible",
                )
                split_ready = split_master_upload is not None
                split_clicked = st.button(
                    "문서분리 실행", key="doc_split_btn", disabled=not split_ready,
                )
                if not split_ready:
                    st.caption("통합 HWP 파일을 먼저 올려주세요.")
                if split_clicked:
                    included = edited_order_df[edited_order_df["포함"]].sort_values("순서")
                    if len(included) == 0:
                        st.warning("포함된 문서가 없습니다. 위 표에서 최소 1건은 체크하세요.")
                    else:
                        doc_rows = [
                            {"category": "form" if r["구분"] == "양식" else "procedure",
                             "doc_type_code": r["코드"], "doc_type_name": r["문서명"]}
                            for _, r in included.iterrows()
                        ]
                        try:
                            with tempfile.TemporaryDirectory() as tmpdir:
                                master_local = os.path.join(tmpdir, split_master_upload.name)
                                with open(master_local, "wb") as f:
                                    f.write(split_master_upload.getvalue())
                                out_dir = os.path.join(tmpdir, "split_out")
                                results = hwp_split.split_hwp_file_auto(
                                    master_local, doc_rows, out_dir,
                                    anchor_mode=anchor_mode, visible=split_visible,
                                )
                                registered, failed = 0, []
                                for r in results:
                                    dt_row = pd.DataFrame()
                                    if r["status"] == "성공" and r["doc_type_code"]:
                                        dt_row = run_query(
                                            "SELECT doc_type_id, category FROM doc_type "
                                            "WHERE doc_type_code = %s", (r["doc_type_code"],),
                                        )
                                    if len(dt_row):
                                        doc_type_id = int(dt_row.iloc[0]["doc_type_id"])
                                        category = dt_row.iloc[0]["category"]
                                        with open(r["file_path"], "rb") as ff:
                                            data = ff.read()
                                        existing_doc_id, next_rev = _next_individual_revision(
                                            app_id, doc_type_id
                                        )
                                        storage_path = build_storage_path(
                                            app_std, project_no,
                                            category_for_doc_type(category),
                                            r["doc_type_code"], next_rev, "hwp",
                                        )
                                        gcs_storage.upload_bytes(storage_path, data)
                                        _upsert_document_individual(
                                            app_id, doc_type_id, next_rev, "hwp",
                                            storage_path, None, existing_doc_id,
                                        )
                                        registered += 1
                                    else:
                                        failed.append(r)
                            st.success(f"{registered}건 분리·등록 완료 → {project_no} ({name_display})")
                            if failed:
                                st.warning(f"{len(failed)}건은 실패/수동확인필요 — 아래에서 확인하세요.")
                                st.dataframe(
                                    pd.DataFrame([
                                        {"코드": r["raw_code"], "구분": r["구분"],
                                         "상태": r["status"], "메시지": r["message"]}
                                        for r in failed
                                    ]),
                                    width="stretch",
                                )
                            st.rerun()
                        except RuntimeError as e:
                            st.info(str(e))
                        except Exception as e:
                            st.error(f"문서분리 중 오류: {e}")

            st.divider()
            st.subheader("🔗 문서통합 (개별 → 통합본)")
            st.caption(
                "현재 신청건에 등록된 매뉴얼/절차서 완성본을 하나의 통합 HWP로 병합합니다. "
                "완성본이 아직 없다면 위 [⬆ 일괄 업로드]나 [✂ 문서분리]로 먼저 채워주세요. "
                "실제 파일 병합(scripts/hwp_merge.py)은 미검증 초안입니다 — 실패하면 자동으로 "
                "'병합 대기(pending_merge)' 상태로 남고, 구성 문서 목록만 DB에 기록됩니다. "
                "★ 한글(한컴오피스)이 설치·로그인된 Windows PC에서만 실제 병합이 동작합니다."
            )
            st.caption(project_badge)
            merge_visible = st.checkbox(
                "한글 창을 화면에 표시하며 실행 (디버깅용, 느림)", value=True, key="doc_integrate_visible"
            )
            if st.button("문서통합 실행", key="doc_integrate_btn"):
                core_docs = _doc_list_for_application(app_id, ["manual", "procedure"], active_stds)
                ready = core_docs[core_docs["individual_storage_path"].notna()]
                if len(ready) == 0:
                    st.warning("완성본이 업로드된 매뉴얼/절차서가 없습니다. 먼저 업로드해주세요.")
                else:
                    doc_ids = [int(x) for x in ready["doc_id"].dropna().tolist()]
                    bundle_scope = "core"  # document_integrated.bundle_scope CHECK: 'core'|'guideline'
                    existing_bundle = run_query(
                        "SELECT integrated_id, revision_no FROM document_integrated "
                        "WHERE application_id=%s AND bundle_scope=%s",
                        (app_id, bundle_scope),
                    )
                    next_rev = (
                        int(existing_bundle.iloc[0]["revision_no"]) + 1 if len(existing_bundle) else 1
                    )
                    integrated_storage_path = None
                    integrated_status = "pending_merge"
                    try:
                        with tempfile.TemporaryDirectory() as tmpdir:
                            local_paths = []
                            for i, row in enumerate(ready.itertuples()):
                                local_path = os.path.join(tmpdir, f"{i}_{row.doc_type_code}.hwp")
                                with open(local_path, "wb") as f:
                                    f.write(gcs_storage.download_bytes(row.individual_storage_path))
                                local_paths.append(local_path)
                            output_path = os.path.join(tmpdir, "merged.hwp")
                            hwp_merge.merge_hwp_files(local_paths, output_path, visible=merge_visible)
                            with open(output_path, "rb") as f:
                                merged_bytes = f.read()
                        integrated_storage_path = build_integrated_path(
                            app_std, project_no, bundle_scope, next_rev, "hwp"
                        )
                        gcs_storage.upload_bytes(integrated_storage_path, merged_bytes)
                        integrated_status = "completed"
                    except NotImplementedError as e:
                        st.info(str(e))
                    except Exception as e:
                        st.warning(
                            f"실제 파일 병합 중 오류가 발생해 병합 대기 상태로 남겨둡니다: {e}"
                        )
                    if len(existing_bundle):
                        run_write(
                            "UPDATE document_integrated SET revision_no=%s, composed_doc_ids=%s, "
                            "storage_path=%s, status=%s WHERE integrated_id=%s",
                            (next_rev, json.dumps(doc_ids), integrated_storage_path, integrated_status,
                             int(existing_bundle.iloc[0]["integrated_id"])),
                        )
                    else:
                        run_write(
                            "INSERT INTO document_integrated "
                            "(application_id, bundle_scope, revision_no, composed_doc_ids, storage_path, status) "
                            "VALUES (%s,%s,%s,%s,%s,%s)",
                            (app_id, bundle_scope, next_rev, json.dumps(doc_ids),
                             integrated_storage_path, integrated_status),
                        )
                    if integrated_status == "completed":
                        st.success(
                            f"통합본 병합이 완료되었습니다 (Rev.{next_rev}, 구성문서 {len(doc_ids)}건) "
                            f"→ `{integrated_storage_path}`"
                        )
                    else:
                        st.success(
                            f"통합본 레코드가 생성/갱신되었습니다 (Rev.{next_rev}, 구성문서 {len(doc_ids)}건, "
                            "상태: 병합 대기). 실제 파일 병합 기능이 연결되면 이어서 완성본이 채워집니다."
                        )
                    st.rerun()

            st.divider()
            st.subheader("개별 문서 처리 (예외용 — 문서 1건만 급히 올리거나 받기)")
            st.caption(
                "전체 문서 현황은 위쪽 표를 참고하세요. 여기서는 문서 1건만 골라 업로드하거나 "
                "다운로드합니다 — 여러 건을 한 번에 처리할 때는 위 [⬆ 일괄 업로드]/[⬇ 일괄 "
                "다운로드]를 사용하세요."
            )
            all_docs_df = _doc_list_for_application(
                app_id, ["manual", "procedure", "form", "guideline"], active_stds
            )
            if len(all_docs_df) == 0:
                st.info("적용 규격에 해당하는 문서종류가 없습니다.")
            else:
                doc_options = [
                    (int(r.doc_type_id), f"{r.doc_type_code} — {r.doc_type_name}")
                    for r in all_docs_df.itertuples()
                ]
                doc_choice = st.selectbox(
                    "대상 문서 선택", doc_options, format_func=lambda x: x[1], key="doc_mgmt_target_doc"
                )
                sel = all_docs_df[all_docs_df["doc_type_id"] == doc_choice[0]].iloc[0]
                is_content = st.checkbox("내용본으로 저장/조회", key="doc_mgmt_is_content")
                storage_category = category_for_doc_type(sel["category"], is_content)
                st.caption(f"저장 폴더: {CATEGORY_LABELS[storage_category]}")

                form_seq_no_in = None
                if sel["category"] == "form" and not is_content:
                    form_seq_no_in = st.text_input(
                        "양식번호(이 신청건 전용 일련번호, 중복 가능) — 선택 입력",
                        value="" if pd.isna(sel.get("form_seq_no")) else str(sel["form_seq_no"]),
                        key="doc_mgmt_form_seq_no",
                    ) or None

                col_up, col_down = st.columns(2)
                with col_up:
                    st.markdown("**⬆ 업로드**")
                    st.caption(project_badge)
                    uploaded = st.file_uploader("업로드할 파일", key="doc_mgmt_uploader")
                    if uploaded is not None and st.button("업로드", key="doc_mgmt_upload_btn"):
                        fmt = uploaded.name.rsplit(".", 1)[-1].lower() if "." in uploaded.name else "hwp"
                        if is_content:
                            if pd.isna(sel["doc_id"]):
                                st.error("먼저 완성본을 업로드해 문서를 생성한 뒤 내용본을 올려주세요.")
                            else:
                                storage_path = build_storage_path(
                                    app_std, project_no, storage_category, sel["doc_type_code"], 1, fmt
                                )
                                gcs_storage.upload_bytes(storage_path, uploaded.getvalue())
                                _upsert_document_content(int(sel["doc_id"]), fmt, storage_path)
                                st.success(f"내용본 업로드 완료 → `{storage_path}`")
                                st.rerun()
                        else:
                            existing_doc_id, next_rev = _next_individual_revision(app_id, doc_choice[0])
                            storage_path = build_storage_path(
                                app_std, project_no, storage_category, sel["doc_type_code"], next_rev, fmt
                            )
                            gcs_storage.upload_bytes(storage_path, uploaded.getvalue())
                            _upsert_document_individual(
                                app_id, doc_choice[0], next_rev, fmt, storage_path,
                                form_seq_no_in, existing_doc_id,
                            )
                            st.success(f"완성본 업로드 완료 (Rev.{next_rev}) → `{storage_path}`")
                            st.rerun()

                with col_down:
                    st.markdown("**⬇ 다운로드**")
                    target_path = sel["content_storage_path"] if is_content else sel["individual_storage_path"]
                    if pd.isna(target_path):
                        st.info("저장된 파일이 없습니다.")
                    else:
                        dl_key = f"doc_mgmt_dl_{doc_choice[0]}_{is_content}"
                        if st.button("다운로드 준비", key="doc_mgmt_dl_prep"):
                            try:
                                st.session_state[dl_key] = gcs_storage.download_bytes(target_path)
                            except Exception as e:
                                st.error(f"다운로드 실패: {e}")
                        if dl_key in st.session_state:
                            st.download_button(
                                "파일 저장", data=st.session_state[dl_key],
                                file_name=target_path.split("/")[-1], key="doc_mgmt_dl_save",
                            )

    # ===== 탭2: 분류문서 보기 =====
    with tab2:
        cat_choice = st.radio(
            "구분", ["매뉴얼", "절차서", "양식", "지침서"], horizontal=True, key="classify_cat"
        )

        if cat_choice in ("매뉴얼", "절차서"):
            cat_key = "manual" if cat_choice == "매뉴얼" else "procedure"
            std_filter = st.multiselect(
                "규격 필터", ["q", "e", "hs"], default=["q", "e", "hs"], key=f"classify_std_{cat_key}"
            )
            opts_df = run_query(
                "SELECT doc_type_id, doc_type_code, doc_type_name FROM doc_type "
                "WHERE category=%s AND applicable_std ?| %s "
                "ORDER BY (substring(doc_type_code from '\\d+'))::int, doc_type_code",
                (cat_key, std_filter or ["q", "e", "hs"]),
            )
            if len(opts_df) == 0:
                st.info("조건에 맞는 문서가 없습니다.")
            else:
                options = [
                    (int(r.doc_type_id), f"{r.doc_type_code} — {r.doc_type_name}")
                    for r in opts_df.itertuples()
                ]
                choice = st.selectbox(
                    "문서 선택", options, format_func=lambda x: x[1], key=f"classify_pick_{cat_key}"
                )
                _render_ledger(choice[0])

        elif cat_choice == "지침서":
            mid_df = run_query(
                "SELECT DISTINCT subcategory FROM doc_type "
                "WHERE category='guideline' AND subcategory IS NOT NULL ORDER BY subcategory"
            )
            mid_options = mid_df["subcategory"].tolist()
            if not mid_options:
                st.info("등록된 지침서가 없습니다.")
            else:
                mid_choice = st.selectbox("중분류", mid_options, key="classify_guide_mid")
                sub_df = run_query(
                    "SELECT DISTINCT subcategory_group FROM doc_type "
                    "WHERE category='guideline' AND subcategory=%s AND subcategory_group IS NOT NULL "
                    "ORDER BY subcategory_group",
                    (mid_choice,),
                )
                sub_options = sub_df["subcategory_group"].tolist()
                if not sub_options:
                    st.info("세분류가 없습니다.")
                else:
                    sub_choice = st.selectbox("세분류", sub_options, key="classify_guide_sub")
                    item_df = run_query(
                        "SELECT doc_type_id, doc_type_code, subcategory_letter, doc_type_name FROM doc_type "
                        "WHERE category='guideline' AND subcategory=%s AND subcategory_group=%s "
                        "ORDER BY subcategory_letter, doc_type_code",
                        (mid_choice, sub_choice),
                    )
                    item_options = [
                        (int(r.doc_type_id), f"{r.subcategory_letter} · {r.doc_type_code} — {r.doc_type_name}")
                        for r in item_df.itertuples()
                    ]
                    item_choice = st.selectbox(
                        "지침서 선택", item_options, format_func=lambda x: x[1], key="classify_guide_item"
                    )
                    _render_ledger(item_choice[0])

        else:  # 양식
            std_filter = st.multiselect(
                "규격 필터 (관련 절차서 검색용)", ["q", "e", "hs"], default=["q", "e", "hs"],
                key="classify_form_std",
            )
            proc_df = run_query(
                "SELECT doc_type_id, doc_type_code, doc_type_name, clause_ref FROM doc_type "
                "WHERE category='procedure' AND applicable_std ?| %s "
                "ORDER BY (substring(doc_type_code from '\\d+'))::int, doc_type_code",
                (std_filter or ["q", "e", "hs"],),
            )
            if len(proc_df) == 0:
                st.info("조건에 맞는 절차서가 없습니다.")
            else:
                proc_options = [
                    (r.clause_ref, f"{r.doc_type_code} — {r.doc_type_name}") for r in proc_df.itertuples()
                ]
                proc_choice = st.selectbox(
                    "관련 절차서 선택", proc_options, format_func=lambda x: x[1], key="classify_form_proc"
                )
                form_df = run_query(
                    "SELECT doc_type_id, doc_type_code, doc_type_name, form_pattern_code FROM doc_type "
                    "WHERE category='form' AND clause_ref=%s ORDER BY doc_type_code",
                    (proc_choice[0],),
                )
                if len(form_df) == 0:
                    st.info("이 절차서에 연결된 양식이 없습니다.")
                else:
                    form_options = [
                        (int(r.doc_type_id), f"{r.doc_type_code} — {r.doc_type_name}")
                        for r in form_df.itertuples()
                    ]
                    form_choice = st.selectbox(
                        "양식 선택 (중복 없음)", form_options, format_func=lambda x: x[1],
                        key="classify_form_pick",
                    )
                    _render_ledger(form_choice[0], is_form=True)
