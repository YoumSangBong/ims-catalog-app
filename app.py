"""
경영시스템문서 플랫폼 — Streamlit 앱 1차(B단계): 화면 골격. (수정검토1.6 반영)

4개 화면:
  1) 기준정보 조회 — standard / sector_main / iaf_group / sector_profile / doc_type / form_pattern
  2) 사용자 관리 — 사용자 등록(회사·샘플 통합) / 조직도
  3) 샘플 문서 관리 — legacy_source_document 조회 (실제 데이터는 다음 전달분 C단계 스크립트로 적재)
  4) 문서 보관 조회 — document_individual / document_content / document_integrated

실행: (scripts/00~05 를 먼저 실행해 DB가 준비된 상태에서)
    streamlit run app.py
"""
import json
import re
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))
from db import get_conn  # noqa: E402

st.set_page_config(page_title="경영시스템문서 플랫폼", layout="wide")

# 규격 조합 7종 (수정검토1.6) — 신청건 등록 시 단일 선택
STD_COMBOS = [
    ("q", "품질경영시스템 (ISO 9001)"),
    ("e", "환경경영시스템 (ISO 14001)"),
    ("hs", "안전보건경영시스템 (ISO 45001)"),
    ("qe", "품질+환경 통합 (ISO 9001+14001)"),
    ("qhs", "품질+안전보건 통합 (ISO 9001+45001)"),
    ("ehs", "환경+안전보건 통합 (ISO 14001+45001)"),
    ("qehs", "품질+환경+안전보건 통합 (ISO 9001+14001+45001)"),
]
STD_TOKENS = {
    "q": ["q"], "e": ["e"], "hs": ["hs"],
    "qe": ["q", "e"], "qhs": ["q", "hs"], "ehs": ["e", "hs"], "qehs": ["q", "e", "hs"],
}

# 직원수 규모 6단계 (수정검토1.6, 기존 micro/small/medium/large 대체)
ORG_SCALE_OPTIONS = ["10인미만", "10~49인", "50~99인", "100~299인", "300~999인", "1000인 이상"]


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
    ["1. 기준정보 조회", "2. 사용자 관리", "3. 샘플 문서 관리", "4. 문서 보관 조회"],
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
        st.dataframe(
            run_query(
                "SELECT * FROM standard "
                "ORDER BY CASE std_code WHEN 'q' THEN 1 WHEN 'e' THEN 2 WHEN 'hs' THEN 3 ELSE 4 END"
            ),
            use_container_width=True,
        )

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
        st.dataframe(df, use_container_width=True)

    elif tab.startswith("form_pattern"):
        st.dataframe(run_query("SELECT * FROM form_pattern ORDER BY pattern_code"), use_container_width=True)


# ---------- 2. 사용자 관리 ----------

elif page.startswith("2"):
    st.header("사용자 관리")
    st.caption(
        "수정검토1.6: 회사·신청건을 '사용자 등록' 하나로 통합(실제 회사/샘플 양자택일 지원). "
        "'조직 책임과 권한' 화면으로의 개편은 별도 세션에서 설계 후 반영 예정이라, 이번엔 "
        "기존 '조직도' 기능을 그대로 둡니다."
    )

    sub = st.radio("항목", ["사용자 등록", "조직도"], horizontal=True)

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
                       c.biz_reg_no AS "Biz_reg_No", a.sample_original AS "Original",
                       a.org_scale AS "Org.scale", a.status AS "Status", a.created_at
                FROM application a
                LEFT JOIN company c ON c.company_id = a.company_id
                LEFT JOIN sector_profile sp ON sp.profile_id = a.profile_id
                ORDER BY a.application_id DESC
            """),
            use_container_width=True,
        )

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

        orgs = fetch_options("SELECT org_chart_id, org_chart_name FROM org_chart ORDER BY org_chart_name")

        with st.form(f"add_user_{key_tag}"):
            if source_kind == "실제 회사":
                company_name_in = st.text_input(
                    "회사명 *", value="" if existing is None else (existing.get("company_name") or "")
                )
                biz_reg_no_in = st.text_input(
                    "사업자등록번호 * (예: 111-11-11111, 이미 등록된 번호면 그 회사에 신청건만 추가됩니다)",
                    value="" if existing is None else (existing.get("biz_reg_no") or ""),
                )
                sample_name_in, sample_original_in = "", ""
            else:
                sample_name_in = st.text_input(
                    "샘플명 *", value="" if existing is None else (existing.get("sample_name") or "")
                )
                sample_original_in = st.text_input(
                    "Original * (샘플 입수 소스명, 예: itcpass)",
                    value="" if existing is None else (existing.get("sample_original") or ""),
                )
                company_name_in, biz_reg_no_in = "", ""

            std_ids = [x[0] for x in STD_COMBOS]
            default_std_idx = (
                std_ids.index(existing["std_code_normalized"])
                if existing is not None and existing["std_code_normalized"] in std_ids
                else 0
            )
            std_choice = st.selectbox(
                "규격 선택 *", STD_COMBOS, format_func=lambda x: f"{x[0]} — {x[1]}", index=default_std_idx
            )

            default_scale_idx = (
                ORG_SCALE_OPTIONS.index(existing["org_scale"])
                if existing is not None and existing.get("org_scale") in ORG_SCALE_OPTIONS
                else 0
            )
            org_scale_choice = st.selectbox(
                "직원수 규모(Org.scale) *", ORG_SCALE_OPTIONS, index=default_scale_idx
            )

            org_ids = [None] + [x[0] for x in orgs]
            default_org_idx = (
                org_ids.index(int(existing["org_chart_id"]))
                if existing is not None and pd.notna(existing.get("org_chart_id"))
                   and int(existing["org_chart_id"]) in org_ids
                else 0
            )
            org_choice = st.selectbox(
                "조직도 (선택)", [(None, "— 선택 안 함 —")] + orgs, format_func=lambda x: x[1],
                index=default_org_idx,
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
                    if not sample_original_in.strip():
                        errors.append("Original(샘플 소스명)은 필수입니다.")

                if not sector_main_choice:
                    errors.append("산업(대분류)을 선택해주세요.")

                if errors:
                    for msg in errors:
                        st.error(msg)
                else:
                    std_norm = std_choice[0]
                    active_stds = STD_TOKENS[std_norm]
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
                        sector_code = sector_main_choice[0]
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
                        sample_name_val = sample_original_val = None
                        name_for_project_no = company_name_in.strip()
                    else:
                        company_id = None
                        sample_name_val = sample_name_in.strip()
                        sample_original_val = sample_original_in.strip()
                        name_for_project_no = f"{sample_name_val}({sample_original_val})"

                    project_no = f"{std_norm}{sector_suffix}_{name_for_project_no}"

                    try:
                        if editing_id:
                            run_write(
                                """
                                UPDATE application SET
                                    company_id = %s, sample_name = %s, sample_original = %s,
                                    project_no = %s, std_code_normalized = %s, active_stds = %s,
                                    sector_code = %s, profile_id = %s, org_chart_id = %s, org_scale = %s
                                WHERE application_id = %s
                                """,
                                (company_id, sample_name_val, sample_original_val, project_no,
                                 std_norm, json.dumps(active_stds, ensure_ascii=False), sector_code, profile_id,
                                 org_choice[0], org_scale_choice, editing_id),
                            )
                            st.success(f"수정되었습니다. (project_no: {project_no})")
                        else:
                            run_write(
                                """
                                INSERT INTO application
                                    (company_id, sample_name, sample_original, project_no,
                                     std_code_normalized, active_stds, sector_code, profile_id,
                                     org_chart_id, org_scale)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                                """,
                                (company_id, sample_name_val, sample_original_val, project_no,
                                 std_norm, json.dumps(active_stds, ensure_ascii=False), sector_code, profile_id,
                                 org_choice[0], org_scale_choice),
                            )
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

    elif sub.startswith("조직도"):
        st.subheader("조직도 목록")
        st.dataframe(run_query("SELECT * FROM org_chart ORDER BY org_chart_id DESC"), use_container_width=True)

        with st.form("add_org_chart"):
            st.subheader("새 조직도 등록")
            name = st.text_input("조직도 이름 *")
            industry_tag = st.text_input("업종 태그 (선택)")
            size_tag = st.selectbox("규모", ORG_SCALE_OPTIONS)
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
