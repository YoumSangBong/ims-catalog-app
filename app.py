"""
경영시스템문서 플랫폼 — Streamlit 앱 1차(B단계): 화면 골격.

4개 화면:
  1) 기준정보 조회 — standard / sector_main / iaf_group / sector_profile / doc_type / form_pattern
  2) 신청건·조직도 관리 — company / application / org_chart / org_chart_role 조회+등록
  3) 샘플 문서 관리 — legacy_source_document 조회 (실제 데이터는 다음 전달분 C단계 스크립트로 적재)
  4) 문서 보관 조회 — document_individual / document_content / document_integrated

실행: (scripts/00~04 를 먼저 실행해 DB가 준비된 상태에서)
    streamlit run app.py
"""
import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))
from db import get_conn  # noqa: E402

st.set_page_config(page_title="경영시스템문서 플랫폼", layout="wide")


# ---------- 공용 헬퍼 ----------

@st.cache_resource
def _engine_conn():
    """페이지 전환 시마다 새로 연결하지 않도록 커넥션을 캐시."""
    return get_conn()


def run_query(sql: str, params: tuple = ()) -> pd.DataFrame:
    conn = _engine_conn()
    try:
        return pd.read_sql(sql, conn, params=params)
    except Exception:
        # 커넥션이 끊어졌으면 캐시를 지우고 한 번 더 시도
        _engine_conn.clear()
        conn = _engine_conn()
        return pd.read_sql(sql, conn, params=params)


def run_write(sql: str, params: tuple = ()):
    conn = _engine_conn()
    with conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)


def fetch_options(sql: str, params: tuple = ()):
    """(id, label) 튜플 리스트 — selectbox용."""
    df = run_query(sql, params)
    return list(df.itertuples(index=False, name=None))


# ---------- 사이드바 네비게이션 ----------

st.sidebar.title("경영시스템문서 플랫폼")
page = st.sidebar.radio(
    "화면 선택",
    ["1. 기준정보 조회", "2. 신청건·조직도 관리", "3. 샘플 문서 관리", "4. 문서 보관 조회"],
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
         "sector_profile (업종 프로필)", "doc_type (문서종류 마스터)", "form_pattern (양식 패턴)"],
    )

    if tab.startswith("standard"):
        st.dataframe(run_query("SELECT * FROM standard ORDER BY std_code"), use_container_width=True)

    elif tab.startswith("sector_main"):
        st.dataframe(run_query("SELECT * FROM sector_main ORDER BY code"), use_container_width=True)

    elif tab.startswith("iaf_group"):
        st.dataframe(run_query("SELECT * FROM iaf_group ORDER BY iaf_num"), use_container_width=True)

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
        st.dataframe(df, use_container_width=True)

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
            ORDER BY category, doc_type_code
        """
        df = run_query(sql, (cat_filter, std_filter))
        st.caption(f"{len(df)}건 표시")
        st.dataframe(df, use_container_width=True)

    elif tab.startswith("form_pattern"):
        st.dataframe(run_query("SELECT * FROM form_pattern ORDER BY pattern_code"), use_container_width=True)


# ---------- 2. 신청건·조직도 관리 ----------

elif page.startswith("2"):
    st.header("신청건·조직도 관리")

    sub = st.radio("항목", ["회사(company)", "신청건(application)", "조직도(org_chart)"], horizontal=True)

    if sub.startswith("회사"):
        st.subheader("회사 목록")
        st.dataframe(run_query("SELECT * FROM company ORDER BY company_id DESC"), use_container_width=True)

        with st.form("add_company"):
            st.subheader("새 회사 등록")
            company_name = st.text_input("회사명 *")
            biz_reg_no = st.text_input("사업자등록번호")
            if st.form_submit_button("등록"):
                if not company_name.strip():
                    st.error("회사명은 필수입니다.")
                else:
                    run_write(
                        "INSERT INTO company (company_name, biz_reg_no) VALUES (%s, %s)",
                        (company_name.strip(), biz_reg_no.strip() or None),
                    )
                    st.success("등록되었습니다.")
                    st.rerun()

    elif sub.startswith("신청건"):
        st.subheader("신청건 목록")
        st.dataframe(
            run_query("""
                SELECT a.application_id, a.project_no, c.company_name, a.std_code_normalized,
                       a.sector_code, a.status, a.created_at
                FROM application a JOIN company c ON c.company_id = a.company_id
                ORDER BY a.application_id DESC
            """),
            use_container_width=True,
        )

        st.subheader("새 신청건 등록")
        companies = fetch_options("SELECT company_id, company_name FROM company ORDER BY company_name")
        profiles = fetch_options(
            "SELECT profile_id, sector_code || ' - ' || sector_name || ' (seq ' || profile_seq || ')' "
            "FROM sector_profile ORDER BY sector_code, profile_seq"
        )
        orgs = fetch_options("SELECT org_chart_id, org_chart_name FROM org_chart ORDER BY org_chart_name")

        if not companies:
            st.info("먼저 회사를 등록해주세요.")
        else:
            with st.form("add_application"):
                company_choice = st.selectbox("회사 *", companies, format_func=lambda x: x[1])
                stds = st.multiselect("규격 선택 * (복수 가능: q/e/hs)", ["q", "e", "hs"])
                profile_choice = st.selectbox(
                    "업종 프로필 (선택)", [(None, "— 선택 안 함 —")] + profiles, format_func=lambda x: x[1]
                )
                org_choice = st.selectbox(
                    "조직도 (선택)", [(None, "— 선택 안 함 —")] + orgs, format_func=lambda x: x[1]
                )
                if st.form_submit_button("등록"):
                    if not stds:
                        st.error("규격을 최소 1개 선택해주세요.")
                    else:
                        std_norm = "".join(sorted(stds, key=["q", "e", "hs"].index))
                        company_id, company_name = company_choice
                        profile_id = profile_choice[0]
                        sector_code = ""
                        if profile_id:
                            row = run_query(
                                "SELECT sector_code, profile_seq FROM sector_profile WHERE profile_id = %s",
                                (profile_id,),
                            )
                            sector_code = row.iloc[0]["sector_code"]
                            profile_seq = int(row.iloc[0]["profile_seq"])
                            project_no = f"{std_norm}{sector_code}{profile_seq:02d}_{company_name}"
                        else:
                            project_no = f"{std_norm}_{company_name}"

                        run_write(
                            """
                            INSERT INTO application
                                (company_id, project_no, std_code_normalized, active_stds,
                                 sector_code, profile_id, org_chart_id)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                            """,
                            (company_id, project_no, std_norm, json.dumps(list(stds), ensure_ascii=False),
                             sector_code or "", profile_id, org_choice[0]),
                        )
                        st.success(f"등록되었습니다. (project_no: {project_no})")
                        st.rerun()

    elif sub.startswith("조직도"):
        st.subheader("조직도 목록")
        st.dataframe(run_query("SELECT * FROM org_chart ORDER BY org_chart_id DESC"), use_container_width=True)

        with st.form("add_org_chart"):
            st.subheader("새 조직도 등록")
            name = st.text_input("조직도 이름 *")
            industry_tag = st.text_input("업종 태그 (선택)")
            size_tag = st.selectbox("규모", ["micro", "small", "medium", "large"])
            if st.form_submit_button("등록"):
                if not name.strip():
                    st.error("조직도 이름은 필수입니다.")
                else:
                    run_write(
                        "INSERT INTO org_chart (org_chart_name, industry_tag, company_size_tag) "
                        "VALUES (%s, %s, %s)",
                        (name.strip(), industry_tag.strip() or None, size_tag),
                    )
                    st.success("등록되었습니다.")
                    st.rerun()

        st.divider()
        st.subheader("조직도 직책 관리")
        orgs = fetch_options("SELECT org_chart_id, org_chart_name FROM org_chart ORDER BY org_chart_name")
        if orgs:
            org_choice = st.selectbox("조직도 선택", orgs, format_func=lambda x: x[1])
            st.dataframe(
                run_query(
                    "SELECT role_id, role_name, department, parent_role_id, seq "
                    "FROM org_chart_role WHERE org_chart_id = %s ORDER BY seq",
                    (org_choice[0],),
                ),
                use_container_width=True,
            )
            with st.form("add_role"):
                role_name = st.text_input("직책명 *")
                department = st.text_input("부서 (선택)")
                seq = st.number_input("순서", min_value=0, value=0, step=1)
                if st.form_submit_button("직책 추가"):
                    if not role_name.strip():
                        st.error("직책명은 필수입니다.")
                    else:
                        run_write(
                            "INSERT INTO org_chart_role (org_chart_id, role_name, department, seq) "
                            "VALUES (%s, %s, %s, %s)",
                            (org_choice[0], role_name.strip(), department.strip() or None, int(seq)),
                        )
                        st.success("추가되었습니다.")
                        st.rerun()
        else:
            st.info("먼저 조직도를 등록해주세요.")


# ---------- 3. 샘플 문서 관리 ----------

elif page.startswith("3"):
    st.header("샘플 문서 관리")
    st.caption(
        "보유 중인 기존 경영시스템문서 샘플(통합본→개별본 분리) 관리 화면입니다. "
        "실제 9개 패키지 데이터 적재는 다음 전달분(C단계) 스크립트로 진행합니다."
    )

    df = run_query("SELECT * FROM legacy_source_document ORDER BY legacy_id DESC")
    st.subheader(f"등록된 원본 소스 파일 ({len(df)}건)")
    st.dataframe(df, use_container_width=True)

    if len(df) == 0:
        st.info("아직 적재된 샘플이 없습니다. C단계 스크립트 실행 후 이 화면에서 확인할 수 있습니다.")
    else:
        st.subheader("소스별 분리 매핑 현황")
        mapping_df = run_query("""
            SELECT ls.file_name, count(*) AS 분리된_문서수
            FROM legacy_split_mapping m
            JOIN legacy_source_document ls ON ls.legacy_id = m.legacy_id
            GROUP BY ls.file_name
            ORDER BY ls.file_name
        """)
        st.dataframe(mapping_df, use_container_width=True)


# ---------- 4. 문서 보관 조회 ----------

elif page.startswith("4"):
    st.header("문서 보관 조회")

    sub = st.radio("항목", ["개별본(document_individual)", "내용본(document_content)", "통합본(document_integrated)"], horizontal=True)

    if sub.startswith("개별본"):
        df = run_query("""
            SELECT di.doc_id, a.project_no, dt.doc_type_code, dt.doc_type_name,
                   di.revision_no, di.format, di.status, di.storage_path, di.created_at
            FROM document_individual di
            JOIN application a ON a.application_id = di.application_id
            JOIN doc_type dt ON dt.doc_type_id = di.doc_type_id
            ORDER BY di.doc_id DESC
            LIMIT 1000
        """)
        st.caption(f"{len(df)}건 표시 (최대 1000건)")
        st.dataframe(df, use_container_width=True)

    elif sub.startswith("내용본"):
        doc_id_filter = st.number_input("doc_id로 검색 (0이면 전체 목록)", min_value=0, value=0, step=1)
        if doc_id_filter:
            df = run_query(
                "SELECT content_id, doc_id, extracted_at, "
                "left(content_text, 2000) AS content_preview, length(content_text) AS 전체글자수 "
                "FROM document_content WHERE doc_id = %s",
                (doc_id_filter,),
            )
            st.dataframe(df, use_container_width=True)
            for _, row in df.iterrows():
                with st.expander(f"content_id {row['content_id']} 전체 내용 보기"):
                    full = run_query(
                        "SELECT content_text FROM document_content WHERE content_id = %s",
                        (row["content_id"],),
                    )
                    st.text(full.iloc[0]["content_text"])
        else:
            df = run_query(
                "SELECT content_id, doc_id, extracted_at, length(content_text) AS 글자수 "
                "FROM document_content ORDER BY content_id DESC LIMIT 500"
            )
            st.caption(f"{len(df)}건 표시 (최대 500건)")
            st.dataframe(df, use_container_width=True)

    elif sub.startswith("통합본"):
        df = run_query("""
            SELECT di.integrated_id, a.project_no, di.bundle_scope, di.format,
                   di.revision_no, jsonb_array_length(di.composed_doc_ids) AS 구성문서수, di.storage_path
            FROM document_integrated di
            JOIN application a ON a.application_id = di.application_id
            ORDER BY di.integrated_id DESC
        """)
        st.dataframe(df, use_container_width=True)
