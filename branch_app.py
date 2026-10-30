"""
경영시스템문서 플랫폼 — 브랜치 앱(고객용 Streamlit 앱, 2026-10-29)

허브 앱(app.py, 운영자용)과 같은 DB·GCS를 쓴다. 설계: claude/hub_branch_design.md

로그인 전:  🔐 로그인 / 🔑 다운로드 키로 문서 받기(단순 사용자·로컬 브랜치용, 로그인 불필요)
로그인 대상(2026-10-30, 15번): 브랜치·로컬 브랜치·단순 사용자 회사 계정 + 무료 개인 회원(role=member).
  단순·무료 회원 메뉴: 👤 내 정보(이메일) / 📥 다운로드 키로 문서 받기 / 🔑 비밀번호 변경
  (커뮤니티 SSO는 v_member_sso 뷰를 읽어 연동 예정)
로그인 후(고객 유형별):
  공통           — 📝 신청 정보(신청 시 일괄 입력·제출, 확인 요청 응답, 만들어진 문서 확인) — 신청건이 없어도 사용
  ② 브랜치       — 📘 내 문서함(공유·개정, 충돌 방지) / 📁 파일 보관함 / ✍ 기록 입력(서버 저장) /
                   📊 기록 대장 / 📋 기록 작성 예시 / 🔒 공개 설정 / 🕵 운영자 접근 / 👥 사용자 관리 /
                   🔑 비밀번호 변경
  ③ 로컬 브랜치  — ✍ 기록 입력(로컬 저장: 파일로만 저장·복구) / 📋 기록 작성 예시 / 🔒 공개 설정 /
                   👥 사용자 관리 / 🔑 비밀번호 변경
  (허브 앱은 운영자 PC 전용이므로, 로컬 브랜치 고객의 양식 작성 화면도 여기서 '로컬 저장 모드'로 제공.
   서버에는 기록 값이 남지 않고 길이 메타데이터만 남는다.)
  ① 단순 사용자  — 로그인 대상 아님(다운로드 키 사용)

권한: 고객 관리자(customer_admin)만 공개 설정 저장·운영자 접근 승인·사용자 관리 가능.
접근 범위: 로그인한 사용자의 회사(company_id) 신청건으로만 모든 조회·저장을 제한.

실행: (scripts 12, 13 마이그레이션 실행 후)
    streamlit run branch_app.py --server.port 8502
계정: 허브 앱 [4. 고객·발행 관리 → 브랜치 계정]에서 고객 관리자 계정을 발급.
"""
import io
import json
import sys
import uuid
import zipfile
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))
from db import get_conn  # noqa: E402
from storage_paths import build_storage_path, category_for_doc_type  # noqa: E402
import auth_utils  # noqa: E402
import gcs_storage  # noqa: E402
import intake_core as ic  # noqa: E402
import record_utils  # noqa: E402

st.set_page_config(page_title="경영시스템문서 — 고객 포털", layout="wide")

CATEGORY_KO = {"manual": "매뉴얼", "procedure": "절차서", "form": "양식", "guideline": "지침서"}
AUTHOR_KO = {"operator": "운영사", "customer": "고객"}
EVIDENCE_TYPE_LABEL = {"erp": "ERP/정보시스템", "paper": "종이 보관", "file": "파일/공유폴더", "external": "외부기관"}
ROLE_KO = {"customer_admin": "고객 관리자", "customer_user": "고객 사용자", "member": "개인 회원"}
TIER_KO = {"branch": "② 브랜치 서비스", "local_branch": "③ 로컬 브랜치 서비스(기록은 내 PC에 저장)",
           "simple": "① 단순 사용자(문서는 다운로드 키로 받음)", "free": "무료 일반 회원"}
BASIC_MENU = ["👤 내 정보", "📥 다운로드 키로 문서 받기", "🔑 비밀번호 변경"]   # 단순·무료 회원


# ---------------------------------------------------------------------------
# DB 헬퍼
# ---------------------------------------------------------------------------
@st.cache_resource
def _conn():
    c = get_conn()
    c.autocommit = True
    return c


def _cursor():
    c = _conn()
    if c.closed:
        _conn.clear()
        c = _conn()
    return c.cursor()


def q(sql, params=()):
    """SELECT → DataFrame."""
    try:
        cur = _cursor()
        cur.execute(sql, params)
    except Exception:
        _conn.clear()
        cur = _cursor()
        cur.execute(sql, params)
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    cur.close()
    return pd.DataFrame(rows, columns=cols)


def x(sql, params=()):
    """쓰기. RETURNING이 있으면 첫 값 반환, 아니면 영향받은 행 수."""
    cur = _cursor()
    cur.execute(sql, params)
    if cur.description:
        row = cur.fetchone()
        out = row[0] if row else None
    else:
        out = cur.rowcount
    cur.close()
    return out


def _pick(label, labels: dict, key, **kw):
    ids = list(labels)
    return st.selectbox(label, ids, format_func=lambda v: labels.get(v, str(v)), key=key, **kw)


def _as_dict(v):
    if isinstance(v, dict):
        return v
    if isinstance(v, str) and v:
        return json.loads(v)
    return None


# ---------------------------------------------------------------------------
# 세션
# ---------------------------------------------------------------------------
def _user():
    return st.session_state.get("user")


def _require_admin():
    if _user()["role"] != "customer_admin":
        st.info("고객 관리자만 사용할 수 있는 기능입니다.")
        return False
    return True


def _login(login_id, password):
    df = q(
        """
        SELECT u.user_id, u.company_id, u.role, u.login_id, u.display_name, u.password_hash,
               u.is_active, u.must_change_password, c.company_name,
               COALESCE(ca.customer_type, u.member_tier) AS customer_type, ca.is_active AS acct_active
        FROM app_user u
        LEFT JOIN company c ON c.company_id = u.company_id
        LEFT JOIN customer_account ca ON ca.company_id = u.company_id
        WHERE u.login_id = %s AND u.role IN ('customer_admin','customer_user','member')
        """,
        (login_id.strip(),),
    )
    if df.empty or not auth_utils.verify_password(password, df.iloc[0]["password_hash"]):
        if not df.empty:
            x("UPDATE app_user SET failed_login_count = failed_login_count + 1 WHERE user_id=%s",
              (int(df.iloc[0]["user_id"]),))
        return None, "아이디 또는 비밀번호가 맞지 않습니다."
    r = df.iloc[0]
    if not r["is_active"] or (pd.notna(r["acct_active"]) and not r["acct_active"]):
        return None, "사용이 중지된 계정입니다. 관리자에게 문의하세요."
    if r["customer_type"] not in TIER_KO:
        return None, "회원 등급이 지정되지 않은 계정입니다. 운영사에 문의하세요."
    x("UPDATE app_user SET last_login_at=now(), failed_login_count=0 WHERE user_id=%s", (int(r["user_id"]),))
    return {
        "user_id": int(r["user_id"]), "company_id": int(r["company_id"]) if pd.notna(r["company_id"]) else None,
        "role": r["role"], "login_id": r["login_id"], "name": r["display_name"] or r["login_id"],
        "company_name": r["company_name"] if pd.notna(r["company_name"]) else "개인 회원",
        "customer_type": r["customer_type"],
        "must_change_password": bool(r["must_change_password"]),
    }, None


def _my_apps():
    u = _user()
    df = q("SELECT application_id, project_no, std_code_normalized FROM application "
           "WHERE company_id=%s ORDER BY application_id DESC", (u["company_id"],))
    return df


def _app_ctx(app_id):
    """현재 신청건(반드시 내 회사 소속인지 확인)."""
    df = q(
        """
        SELECT a.application_id, a.project_no, a.std_code_normalized, ca.customer_type,
               p.max_private_ratio, p.template_access_rule
        FROM application a
        JOIN customer_account ca ON ca.company_id = a.company_id
        JOIN customer_type_policy p ON p.customer_type = ca.customer_type
        WHERE a.application_id=%s AND a.company_id=%s
        """,
        (app_id, _user()["company_id"]),
    )
    if df.empty:
        st.error("접근할 수 없는 신청건입니다.")
        st.stop()
    return df.iloc[0]


# ---------------------------------------------------------------------------
# 로그인 전 화면
# ---------------------------------------------------------------------------
def page_login():
    st.title("경영시스템문서 고객 포털")
    t1, t2 = st.tabs(["🔐 로그인", "🔑 다운로드 키로 문서 받기"])
    with t1:
        lid = st.text_input("아이디", key="login_id")
        pw = st.text_input("비밀번호", type="password", key="login_pw")
        if st.button("로그인", type="primary", key="login_btn"):
            user, err = _login(lid, pw)
            if err:
                st.error(err)
            else:
                st.session_state["user"] = user
                st.rerun()
        st.caption("계정은 운영사가 발급합니다. 비밀번호를 잊으셨으면 회사 관리자 또는 운영사에 초기화를 요청하세요.")
    with t2:
        page_download_key()


def page_download_key():
    st.caption("운영사에게 받은 다운로드 키를 입력하면 발행된 문서 세트를 zip으로 받을 수 있습니다.")
    key_text = st.text_input("다운로드 키", key="dlkey_text", placeholder="xxxx-xxxx-xxxx-xxxx")
    if st.button("확인 후 받기", key="dlkey_btn", disabled=not key_text.strip()):
        rel = x(
            """
            UPDATE download_key SET used_count = used_count + 1
            WHERE key_hash = %s AND revoked_at IS NULL
              AND (expires_at IS NULL OR expires_at > now())
              AND (max_downloads IS NULL OR used_count < max_downloads)
            RETURNING key_id
            """,
            (auth_utils.key_hash(key_text),),
        )
        if not rel:
            st.error("유효하지 않은 키입니다(오타, 만료, 횟수 소진 또는 폐기).")
            return
        x("INSERT INTO download_log (key_id) VALUES (%s)", (rel,))
        info = q(
            "SELECT r.release_id, r.released_at, a.project_no, k.used_count, k.max_downloads, k.expires_at "
            "FROM download_key k JOIN doc_release r ON r.release_id = k.release_id "
            "JOIN application a ON a.application_id = r.application_id WHERE k.key_id=%s",
            (rel,),
        ).iloc[0]
        items = q("SELECT storage_path FROM doc_release_item WHERE release_id=%s AND storage_path IS NOT NULL",
                  (int(info["release_id"]),))
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in items["storage_path"]:
                zf.writestr("/".join(p.split("/")[2:]) or p, gcs_storage.download_bytes(p))
        st.session_state["dlkey_zip"] = (buf.getvalue(), f"{info['project_no']}_release{info['release_id']}.zip")
        st.success(f"발행일 {str(info['released_at'])[:10]} · 문서 {len(items)}건 · "
                   f"남은 횟수 {int(info['max_downloads']) - int(info['used_count'])}")
    if "dlkey_zip" in st.session_state:
        data, name = st.session_state["dlkey_zip"]
        st.download_button("zip 저장", data, file_name=name, key="dlkey_save")


# ---------------------------------------------------------------------------
# 📘 내 문서함 (브랜치: 허브와 같은 행 공유, 양쪽 개정 가능)
# ---------------------------------------------------------------------------
def page_documents(ctx):
    st.header("📘 내 문서함")
    app_id = int(ctx["application_id"])
    docs = q(
        """
        SELECT di.doc_id, dt.doc_type_code, dt.doc_type_name, dt.category, di.revision_no,
               di.last_author_role, di.storage_path, di.format,
               (SELECT max(changed_at) FROM document_revision_log l WHERE l.doc_id = di.doc_id) AS last_changed
        FROM document_individual di JOIN doc_type dt ON dt.doc_type_id = di.doc_type_id
        WHERE di.application_id = %s
        ORDER BY CASE dt.category WHEN 'manual' THEN 1 WHEN 'procedure' THEN 2 WHEN 'form' THEN 3 ELSE 4 END,
                 dt.doc_type_code
        """,
        (app_id,),
    )
    if docs.empty:
        st.info("아직 등록된 문서가 없습니다.")
        return
    cats = st.multiselect("구분", list(CATEGORY_KO), default=list(CATEGORY_KO),
                          format_func=lambda c: CATEGORY_KO[c], key="docs_cats")
    view = docs[docs["category"].isin(cats)].copy()
    view["구분"] = view["category"].map(CATEGORY_KO)
    view["최근 개정"] = view["last_author_role"].map(AUTHOR_KO)
    view["파일"] = view["storage_path"].notna().map({True: "O", False: "-"})
    st.dataframe(view[["doc_type_code", "doc_type_name", "구분", "revision_no", "최근 개정", "last_changed", "파일"]]
                 .rename(columns={"doc_type_code": "코드", "doc_type_name": "문서명", "revision_no": "Rev",
                                  "last_changed": "최근 변경일"}),
                 use_container_width=True, hide_index=True)
    if view.empty:
        return

    labels = {int(r.doc_id): f"{r.doc_type_code} {r.doc_type_name} (Rev.{r.revision_no})" for r in view.itertuples()}
    doc_id = _pick("문서 선택", labels, "docs_pick")
    d = docs[docs["doc_id"] == doc_id].iloc[0]

    # 편집 시작 시점의 개정번호를 기억 → 저장 시 그 사이 다른 쪽이 개정했는지 확인(낙관적 잠금)
    base_key = f"docs_base_rev_{doc_id}"
    st.session_state.setdefault(base_key, int(d["revision_no"]))
    base_rev = st.session_state[base_key]
    if base_rev != int(d["revision_no"]):
        st.warning(f"이 문서는 열어둔 뒤 다른 쪽에서 개정되었습니다(Rev.{base_rev} → Rev.{int(d['revision_no'])}).")
        if st.button("최신본 기준으로 다시 열기", key=f"docs_reload_{doc_id}"):
            st.session_state[base_key] = int(d["revision_no"])
            st.rerun()

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**⬇ 현재 파일 받기**")
        if pd.isna(d["storage_path"]):
            st.caption("저장된 파일이 없습니다.")
        else:
            dk = f"docs_dl_{doc_id}_{int(d['revision_no'])}"
            if st.button("파일 준비", key=f"docs_prep_{doc_id}"):
                st.session_state[dk] = gcs_storage.download_bytes(d["storage_path"])
            if dk in st.session_state:
                st.download_button("저장", st.session_state[dk], file_name=d["storage_path"].split("/")[-1],
                                   key=f"docs_save_{doc_id}")
    with c2:
        st.markdown("**⬆ 개정본 올리기**")
        up = st.file_uploader("개정한 파일", key=f"docs_up_{doc_id}")
        note = st.text_input("개정 내용(필수)", key=f"docs_note_{doc_id}")
        if st.button("개정 저장", type="primary", key=f"docs_rev_{doc_id}",
                     disabled=up is None or not note.strip() or base_rev != int(d["revision_no"])):
            ok, msg = _save_revision(ctx, d, base_rev, up, note.strip())
            (st.success if ok else st.error)(msg)
            if ok:
                st.session_state[base_key] = base_rev + 1

    with st.expander("개정 이력"):
        st.dataframe(q("SELECT revision_no AS rev, author_role AS 작성, change_note AS 내용, changed_at AS 일시 "
                       "FROM document_revision_log WHERE doc_id=%s ORDER BY log_id DESC", (doc_id,))
                     .replace({"작성": AUTHOR_KO}), use_container_width=True, hide_index=True)


def _save_revision(ctx, d, base_rev, uploaded, note):
    new_rev = base_rev + 1
    fmt = uploaded.name.rsplit(".", 1)[-1].lower() if "." in uploaded.name else (d["format"] or "hwp")
    path = build_storage_path(ctx["std_code_normalized"], ctx["project_no"],
                              category_for_doc_type(d["category"]), d["doc_type_code"], new_rev, fmt)
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE document_individual SET revision_no=%s, storage_path=%s, format=%s, status='current', "
                "last_author_role='customer' WHERE doc_id=%s AND application_id=%s AND revision_no=%s",
                (new_rev, path, fmt, int(d["doc_id"]), int(ctx["application_id"]), base_rev),
            )
            if cur.rowcount == 0:
                conn.rollback()
                return False, "저장하지 못했습니다 — 그 사이 다른 쪽에서 먼저 개정했습니다. 최신본을 받아 다시 작업하세요."
            cur.execute(
                "INSERT INTO document_revision_log (doc_id, revision_no, change_note, author_role, author_user_id) "
                "VALUES (%s,%s,%s,'customer',%s)",
                (int(d["doc_id"]), new_rev, note, _user()["user_id"]),
            )
            gcs_storage.upload_bytes(path, uploaded.getvalue())   # 실패하면 DB도 롤백
        conn.commit()
        return True, f"Rev.{new_rev}로 개정했습니다. 운영사 허브에도 바로 반영됩니다."
    except Exception as e:  # noqa: BLE001
        conn.rollback()
        return False, f"저장 중 오류: {e}"
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 📁 파일 보관함
# ---------------------------------------------------------------------------
def page_files(ctx):
    st.header("📁 파일 보관함")
    st.caption("경영시스템 운영에 필요한 자체 파일(증빙, 사진, 외부 문서 등)을 보관합니다.")
    app_id = int(ctx["application_id"])
    ups = st.file_uploader("파일 올리기(여러 개 가능)", accept_multiple_files=True, key="files_up")
    note = st.text_input("메모(선택)", key="files_note")
    if st.button("업로드", key="files_go", disabled=not ups):
        for f in ups:
            safe = f.name.replace("/", "_").replace("\\", "_")
            path = f"branch/{app_id}/files/{uuid.uuid4().hex[:12]}_{safe}"
            gcs_storage.upload_bytes(path, f.getvalue())
            x("INSERT INTO customer_file (application_id, file_name, storage_path, size_bytes, note, uploaded_by_user_id) "
              "VALUES (%s,%s,%s,%s,NULLIF(%s,''),%s)", (app_id, f.name, path, f.size, note.strip(), _user()["user_id"]))
        st.success(f"{len(ups)}개 업로드")
    files = q(
        "SELECT f.file_id, f.file_name, f.size_bytes, f.note, f.uploaded_at, u.display_name AS 올린사람, f.storage_path "
        "FROM customer_file f LEFT JOIN app_user u ON u.user_id = f.uploaded_by_user_id "
        "WHERE f.application_id=%s AND NOT f.is_deleted ORDER BY f.file_id DESC",
        (app_id,),
    )
    if files.empty:
        st.caption("보관 중인 파일이 없습니다.")
        return
    st.dataframe(files.drop(columns=["storage_path"]), use_container_width=True, hide_index=True)
    fid = _pick("파일", {int(r.file_id): r.file_name for r in files.itertuples()}, "files_pick")
    f = files[files["file_id"] == fid].iloc[0]
    c1, c2 = st.columns(2)
    dk = f"files_dl_{fid}"
    if c1.button("받기 준비", key="files_prep"):
        st.session_state[dk] = gcs_storage.download_bytes(f["storage_path"])
    if dk in st.session_state:
        c1.download_button("저장", st.session_state[dk], file_name=f["file_name"], key="files_save")
    if c2.button("삭제", key="files_del"):
        x("UPDATE customer_file SET is_deleted=true WHERE file_id=%s AND application_id=%s", (fid, app_id))
        st.rerun()


# ---------------------------------------------------------------------------
# ✍ 기록 입력 (브랜치: 서버 저장 / 로컬 브랜치: 파일로만)
# ---------------------------------------------------------------------------
def _forms(app_id):
    return q(
        "SELECT di.doc_id, di.doc_type_id, di.revision_no, dt.doc_type_code, dt.doc_type_name, dt.clause_ref, "
        "dt.is_personal_data, dt.default_evidence FROM document_individual di "
        "JOIN doc_type dt ON dt.doc_type_id = di.doc_type_id "
        "WHERE di.application_id=%s AND dt.category='form' ORDER BY dt.doc_type_code",
        (app_id,),
    )


def _editor_df(payload):
    rows = [{"항목": k, "값": v} for k, v in (payload or {}).items()]
    return pd.DataFrame(rows or [{"항목": "", "값": ""}], columns=["항목", "값"])


def _payload_from(df):
    out = {}
    for r in df.itertuples(index=False):
        k = "" if pd.isna(r[0]) else str(r[0]).strip()
        if k:
            out[k] = "" if pd.isna(r[1]) else str(r[1])
    return out


def _evidence_inputs(prefix, default):
    default = default or {}
    types = list(EVIDENCE_TYPE_LABEL)
    t = st.selectbox("증빙 구분", types, format_func=lambda v: EVIDENCE_TYPE_LABEL[v],
                     index=types.index(default["type"]) if default.get("type") in types else 0, key=f"{prefix}_t")
    c1, c2 = st.columns(2)
    sysname = c1.text_input("시스템/기관명", value=default.get("system", ""), key=f"{prefix}_s")
    loc = c2.text_input("메뉴 경로/보관 위치", value=default.get("menu", default.get("location", "")), key=f"{prefix}_m")
    note = st.text_input("비고", value=default.get("note", ""), key=f"{prefix}_n")
    ev = {"type": t}
    if sysname.strip():
        ev["system"] = sysname.strip()
    if loc.strip():
        ev["menu" if t == "erp" else "location"] = loc.strip()
    if note.strip():
        ev["note"] = note.strip()
    return ev


def _insert_usage(app_id, doc_type_id, rev, rec_date, source, payload):
    for r in record_utils.field_usage_rows(payload):
        x("INSERT INTO form_field_usage (application_id, doc_type_id, form_revision_no, field_name, record_date, "
          "source, is_filled, char_count, display_width, line_count, overflow, numeric_bucket) "
          "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
          (app_id, doc_type_id, rev, r["field_name"], rec_date, source, r["is_filled"], r["char_count"],
           r["display_width"], r["line_count"], r["overflow"], r["numeric_bucket"]))


def page_record_entry(ctx):
    is_local = ctx["customer_type"] == "local_branch"
    st.header("✍ 기록 입력" + (" (로컬 저장)" if is_local else ""))
    if is_local:
        st.info("로컬 저장 방식입니다 — 입력한 값은 서버에 저장되지 않고, 내려받는 파일로만 보관됩니다. "
                "다음에 같은 양식을 작성할 때 그 파일을 올리면 값이 채워진 상태로 시작합니다.")
    app_id = int(ctx["application_id"])
    forms = _forms(app_id)
    if forms.empty:
        st.info("등록된 양식이 없습니다.")
        return
    labels = {int(r.doc_id): f"{r.doc_type_code} {r.doc_type_name} (Rev.{r.revision_no})"
              + (" 🔒개인정보" if r.is_personal_data else "") for r in forms.itertuples()}
    if st.session_state.get("rec_goto_doc") in labels:   # 기록 작성 예시에서 넘어온 경우
        st.session_state["rec_form"] = st.session_state.pop("rec_goto_doc")
    doc_id = _pick("양식", labels, "rec_form")
    f = next(r for r in forms.itertuples(index=False) if int(r.doc_id) == doc_id)
    sk, vk = f"rec_prefill_{doc_id}", f"rec_prefill_{doc_id}_ver"
    st.session_state.setdefault(sk, {})
    st.session_state.setdefault(vk, 0)

    if is_local:
        up = st.file_uploader("지난 기록 파일로 시작(zip 또는 json)", type=["zip", "json"], key=f"rec_restore_{doc_id}")
        if up is not None and st.button("이 파일 값으로 채우기", key=f"rec_restore_go_{doc_id}"):
            try:
                doc = record_utils.read_local_package(up.getvalue())
                if doc.get("doc_type_code") != f.doc_type_code:
                    st.warning(f"다른 양식({doc.get('doc_type_code')})의 기록입니다. 값만 채웁니다.")
                if not doc["hash_ok"]:
                    st.warning("내려받은 뒤 파일 내용이 수정되었습니다(해시 불일치).")
                st.session_state[sk] = doc["payload"]
                st.session_state[vk] += 1
                st.success("채웠습니다. 바뀐 부분만 고치세요.")
            except ValueError as e:
                st.error(str(e))

    rec_date = st.date_input("기록일", value=date.today(), key=f"rec_date_{doc_id}")
    st.caption("양식별 입력 칸이 확정되기 전까지는 '항목/값'으로 입력합니다. 행 추가는 표 아래 '+'.")
    edited = st.data_editor(_editor_df(st.session_state[sk]), num_rows="dynamic", use_container_width=True,
                            key=f"rec_editor_{doc_id}_{st.session_state[vk]}")
    payload = _payload_from(edited)
    dev = _as_dict(f.default_evidence)
    use_ev = st.checkbox("ERP 등 외부 증빙으로 대체(증빙 위치 기록)", value=bool(dev), key=f"rec_use_ev_{doc_id}")
    evidence = _evidence_inputs(f"rec_ev_{doc_id}", dev) if use_ev else None
    if not payload and not evidence:
        st.caption("값이나 증빙 중 하나 이상을 입력하세요.")
        return

    if not is_local:
        if st.button("기록 저장", type="primary", key=f"rec_save_{doc_id}"):
            rid = x("INSERT INTO form_record (application_id, doc_id, form_revision_no, record_date, entry_app, "
                    "author_role, entered_by_user_id, evidence_ref) VALUES (%s,%s,%s,%s,'branch','customer',%s,%s::jsonb) "
                    "RETURNING record_id",
                    (app_id, doc_id, int(f.revision_no), rec_date, _user()["user_id"],
                     json.dumps(evidence, ensure_ascii=False) if evidence else None))
            x("INSERT INTO form_record_payload (record_id, payload, payload_hash) VALUES (%s,%s::jsonb,%s)",
              (rid, json.dumps(payload, ensure_ascii=False), record_utils.payload_hash(payload)))
            _insert_usage(app_id, int(f.doc_type_id), int(f.revision_no), rec_date, "branch", payload)
            st.session_state[sk] = {}
            st.session_state[vk] += 1
            st.success(f"기록 #{rid}를 저장했습니다.")
        return

    pk = f"rec_pkg_{doc_id}"
    if st.button("기록 파일 만들기", type="primary", key=f"rec_pkg_go_{doc_id}"):
        meta = {"project_no": ctx["project_no"], "doc_type_code": f.doc_type_code, "doc_type_name": f.doc_type_name,
                "form_revision_no": int(f.revision_no), "record_date": rec_date.isoformat(), "evidence_ref": evidence}
        st.session_state[pk] = record_utils.build_local_package(meta, payload)
        _insert_usage(app_id, int(f.doc_type_id), int(f.revision_no), rec_date, "local_upload", payload)
    if pk in st.session_state:
        st.download_button("기록 파일 저장(zip) — 내 PC에 보관", st.session_state[pk],
                           file_name=f"{f.doc_type_code}_{rec_date.isoformat()}.zip", key=f"rec_pkg_save_{doc_id}")
    if f.is_personal_data or not payload:
        return
    with st.expander("이 건을 공용 템플릿으로 제공(선택)"):
        st.caption("익명화된 결과만 전송되며 운영사 검수 후 게시됩니다. 공개로 설정한 양식은 최근 12개월 내 "
                   "승인된 제공이 있어야 템플릿 활용 자격이 유지됩니다.")
        extra = st.text_input("추가로 가릴 단어(담당자명·거래처명 등, 쉼표 구분)", key=f"rec_terms_{doc_id}")
        anon = record_utils.anonymize_payload(payload, [_user()["company_name"]] + extra.split(","))
        st.json(anon)
        if st.button("이 내용으로 제공", key=f"rec_contrib_{doc_id}"):
            x("INSERT INTO record_template (doc_type_id, source, contributor_application_id, form_revision_no, "
              "anonymized_payload) VALUES (%s,'customer',%s,%s,%s::jsonb)",
              (int(f.doc_type_id), app_id, int(f.revision_no), json.dumps(anon, ensure_ascii=False)))
            st.success("제공했습니다(운영사 검수 대기).")


# ---------------------------------------------------------------------------
# 📊 기록 대장 (브랜치)
# ---------------------------------------------------------------------------
def page_ledger(ctx):
    st.header("📊 기록 대장")
    app_id = int(ctx["application_id"])
    recs = q(
        """
        SELECT r.record_id, dt.doc_type_code, dt.doc_type_name, r.form_revision_no, r.record_date,
               r.entry_app, r.author_role, u.display_name AS 입력자, r.evidence_ref, p.payload
        FROM form_record r
        JOIN document_individual di ON di.doc_id = r.doc_id
        JOIN doc_type dt ON dt.doc_type_id = di.doc_type_id
        LEFT JOIN form_record_payload p ON p.record_id = r.record_id
        LEFT JOIN app_user u ON u.user_id = r.entered_by_user_id
        WHERE r.application_id=%s AND NOT r.is_deleted
        ORDER BY r.record_date DESC, r.record_id DESC
        """,
        (app_id,),
    )
    if recs.empty:
        st.caption("저장된 기록이 없습니다.")
        return
    codes = ["(전체)"] + sorted(recs["doc_type_code"].unique().tolist())
    code = st.selectbox("양식", codes, key="ledger_code")
    view = recs if code == "(전체)" else recs[recs["doc_type_code"] == code]
    show = view.drop(columns=["payload", "evidence_ref"]).copy()
    show["작성"] = show["author_role"].map(AUTHOR_KO)
    show["증빙"] = view["evidence_ref"].apply(lambda v: EVIDENCE_TYPE_LABEL.get((_as_dict(v) or {}).get("type"), ""))
    st.dataframe(show.drop(columns=["author_role"]), use_container_width=True, hide_index=True)

    rid = _pick("기록 보기", {int(r.record_id): f"#{r.record_id} {r.doc_type_code} {r.record_date}"
                              for r in view.itertuples()}, "ledger_pick")
    r = view[view["record_id"] == rid].iloc[0]
    st.json(_as_dict(r["payload"]) or {})
    if _as_dict(r["evidence_ref"]):
        st.caption("증빙: " + json.dumps(_as_dict(r["evidence_ref"]), ensure_ascii=False))
    if st.button("이 기록 삭제", key="ledger_del"):
        x("UPDATE form_record SET is_deleted=true WHERE record_id=%s AND application_id=%s", (rid, app_id))
        st.rerun()

    # 내 데이터 내보내기(구독 해지 시에도 데이터가 갇히지 않도록)
    rows = [{"record_id": int(v.record_id), "양식": v.doc_type_code, "기록일": str(v.record_date),
             "양식개정": int(v.form_revision_no), **(_as_dict(v.payload) or {})} for v in view.itertuples()]
    st.download_button("⬇ 이 목록 내보내기(CSV)", "﻿" + pd.DataFrame(rows).to_csv(index=False),
                       file_name=f"{ctx['project_no']}_records.csv", key="ledger_export")


# ---------------------------------------------------------------------------
# 📋 기록 작성 예시
# ---------------------------------------------------------------------------
def page_templates(ctx):
    st.header("📋 기록 작성 예시")
    app_id = int(ctx["application_id"])
    vis = q(
        """
        SELECT v.doc_type_id, v.access_basis, dt.doc_type_code, dt.doc_type_name, di.doc_id,
               (SELECT COUNT(*) FROM record_template t WHERE t.doc_type_id = v.doc_type_id AND t.is_published) AS 예시수
        FROM v_template_visible_form v
        JOIN doc_type dt ON dt.doc_type_id = v.doc_type_id
        JOIN document_individual di ON di.application_id = v.application_id AND di.doc_type_id = v.doc_type_id
        WHERE v.application_id = %s ORDER BY dt.doc_type_code
        """,
        (app_id,),
    )
    acc = q("SELECT * FROM v_template_access WHERE application_id=%s", (app_id,))
    if vis.empty:
        st.info("아직 기록 작성 예시를 볼 수 있는 자격이 없습니다. [🔒 공개 설정]에서 조건을 확인하세요.")
        if not acc.empty:
            a = acc.iloc[0]
            st.caption(f"현재 비공개 {int(a['private_forms'])}/{int(a['eligible_forms'])} (한도 "
                       f"{float(a['max_private_ratio']):.0%})")
        return
    vis = vis[vis["예시수"] > 0]
    if vis.empty:
        st.caption("자격은 있지만 아직 게시된 예시가 없습니다.")
        return
    did = _pick("양식", {int(r.doc_type_id): f"{r.doc_type_code} {r.doc_type_name} · 예시 {r.예시수}건"
                         + (" (절차서 단위 자격)" if r.access_basis == "procedure" else "") for r in vis.itertuples()},
                "tmpl_form")
    row = vis[vis["doc_type_id"] == did].iloc[0]
    tmpl = q("SELECT template_id, source, anonymized_payload FROM record_template "
             "WHERE doc_type_id=%s AND is_published ORDER BY source DESC, template_id DESC", (did,))
    for t in tmpl.itertuples():
        with st.expander(f"예시 #{t.template_id} ({'운영사 작성' if t.source == 'operator' else '고객 제공'})"):
            st.json(_as_dict(t.anonymized_payload))
            if st.button("이 예시로 기록 시작", key=f"tmpl_use_{t.template_id}"):
                doc_id = int(row["doc_id"])
                st.session_state[f"rec_prefill_{doc_id}"] = _as_dict(t.anonymized_payload)
                st.session_state[f"rec_prefill_{doc_id}_ver"] = st.session_state.get(f"rec_prefill_{doc_id}_ver", 0) + 1
                st.session_state["rec_goto_doc"] = doc_id
                st.session_state["nav_goto"] = "✍ 기록 입력"
                st.rerun()


# ---------------------------------------------------------------------------
# 🔒 공개 설정
# ---------------------------------------------------------------------------
def page_disclosure(ctx):
    st.header("🔒 공개 설정")
    app_id = int(ctx["application_id"])
    limit = float(ctx["max_private_ratio"])
    st.markdown(
        f"양식 종류 기준 **최대 {limit:.0%}까지 비공개**로 둘 수 있습니다. 개인정보 양식은 항상 비공개이며 "
        "비율 계산에서 빠집니다. 공개 양식의 기록은 **익명화 → 운영사 검수 → 일부 게시**되며 원본이 그대로 "
        "공개되지 않습니다."
        + (" 로컬 요금제는 비공개 가능 범위가 더 넓습니다." if ctx["customer_type"] == "local_branch" else "")
    )
    status = q("SELECT doc_type_id, doc_type_code, clause_ref, is_personal_data, is_private, recent_contributions "
               "FROM v_form_disclosure_status WHERE application_id=%s ORDER BY doc_type_code", (app_id,))
    if status.empty:
        st.info("등록된 양식이 없습니다.")
        return
    is_admin = _user()["role"] == "customer_admin"
    edited = st.data_editor(
        status,
        disabled=["doc_type_id", "doc_type_code", "clause_ref", "is_personal_data", "recent_contributions"]
        + ([] if is_admin else ["is_private"]),
        column_config={"doc_type_id": None, "doc_type_code": "양식", "clause_ref": "관련 조항",
                       "is_private": st.column_config.CheckboxColumn("비공개"),
                       "is_personal_data": st.column_config.CheckboxColumn("개인정보(항상 비공개)"),
                       "recent_contributions": "최근 12개월 승인 제공"},
        use_container_width=True, hide_index=True, key="disc_editor",
    )
    elig = edited[~edited["is_personal_data"]]
    n_priv = int(elig["is_private"].sum())
    ratio = n_priv / len(elig) if len(elig) else 0
    st.markdown(f"비공개 {n_priv}/{len(elig)} = **{ratio:.0%}** (한도 {limit:.0%})")
    if is_admin:
        if st.button("저장", type="primary", key="disc_save", disabled=ratio > limit):
            for r in elig.itertuples():
                x("INSERT INTO form_disclosure_setting (application_id, doc_type_id, is_private) VALUES (%s,%s,%s) "
                  "ON CONFLICT (application_id, doc_type_id) DO UPDATE SET is_private=EXCLUDED.is_private, updated_at=now()",
                  (app_id, int(r.doc_type_id), bool(r.is_private)))
            st.success("저장했습니다.")
            st.rerun()
        if ratio > limit:
            st.error("비공개 비율이 한도를 넘었습니다.")
    else:
        st.caption("공개 설정 변경은 고객 관리자만 할 수 있습니다.")

    acc = q("SELECT * FROM v_template_access WHERE application_id=%s", (app_id,))
    if not acc.empty:
        a = acc.iloc[0]
        st.markdown("**템플릿 활용 자격**: " + ("✅ 전체 양식" if a["full_template_access"] else "❌ 전체 양식 미충족"))
        if ctx["customer_type"] == "local_branch":
            st.caption(f"공개 양식 {int(a['public_forms'])}종 중 최근 12개월 승인 제공이 있는 양식 "
                       f"{int(a['public_forms_contributed'])}종 — 모두 채우면 전체 활용(A안). 또는 절차서 단위(B안):")
            pa = q("SELECT procedure_code AS 절차서, clause_ref AS 조항, eligible_forms AS 대상양식, "
                   "ready_forms AS 충족양식, procedure_access AS 활용가능 FROM v_procedure_template_access "
                   "WHERE application_id=%s AND eligible_forms > 0 ORDER BY procedure_code", (app_id,))
            st.dataframe(pa, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# 🕵 운영자 접근
# ---------------------------------------------------------------------------
def page_operator_access(ctx):
    st.header("🕵 운영자 접근")
    st.caption("운영사는 고객이 승인한 기간에만 기록 원본을 볼 수 있으며, 모든 열람이 아래에 기록됩니다.")
    app_id = int(ctx["application_id"])
    grants = q("SELECT grant_id, reason AS 사유, granted_at AS 승인일, expires_at AS 만료일, revoked_at AS 철회일, "
               "CASE WHEN revoked_at IS NOT NULL THEN '철회' WHEN expires_at < now() THEN '만료' ELSE '유효' END AS 상태 "
               "FROM operator_access_grant WHERE application_id=%s ORDER BY grant_id DESC", (app_id,))
    st.subheader("접근 승인")
    st.dataframe(grants, use_container_width=True, hide_index=True)
    if _user()["role"] == "customer_admin":
        c1, c2 = st.columns([3, 1])
        reason = c1.text_input("사유(예: 데이터 오류 지원 요청)", key="grant_reason")
        days = c2.number_input("기간(일)", 1, 30, 3, key="grant_days")
        if st.button("승인", key="grant_go", disabled=not reason.strip()):
            x("INSERT INTO operator_access_grant (application_id, granted_by_user_id, reason, expires_at) "
              "VALUES (%s,%s,%s, now() + make_interval(days => %s))", (app_id, _user()["user_id"], reason.strip(), int(days)))
            st.rerun()
        live = grants[grants["상태"] == "유효"]
        if not live.empty:
            gid = _pick("철회할 승인", {int(g): f"#{g}" for g in live["grant_id"]}, "grant_revoke_pick")
            if st.button("즉시 철회", key="grant_revoke"):
                x("UPDATE operator_access_grant SET revoked_at=now() WHERE grant_id=%s AND application_id=%s", (gid, app_id))
                st.rerun()
    st.subheader("열람 기록")
    st.dataframe(q("SELECT accessed_at AS 일시, action AS 동작, target_table AS 대상, target_id AS 대상번호, "
                   "grant_id AS 승인번호 FROM operator_access_log WHERE application_id=%s ORDER BY log_id DESC",
                   (app_id,)), use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# 👥 사용자 관리 / 🔑 비밀번호
# ---------------------------------------------------------------------------
def page_users(ctx):
    st.header("👥 사용자 관리")
    if not _require_admin():
        return
    cid = _user()["company_id"]
    users = q("SELECT user_id, login_id AS 아이디, display_name AS 이름, email AS 이메일, role, is_active AS 사용, "
              "last_login_at AS 최근로그인 "
              "FROM app_user WHERE company_id=%s ORDER BY user_id", (cid,))
    show = users.copy()
    show["권한"] = show["role"].map(ROLE_KO)
    st.dataframe(show.drop(columns=["role"]), use_container_width=True, hide_index=True)

    st.subheader("사용자 추가")
    c1, c2, c3, c4 = st.columns(4)
    lid = c1.text_input("아이디", key="usr_new_id")
    name = c2.text_input("이름", key="usr_new_name")
    email = c3.text_input("이메일", key="usr_new_email")
    roles = ["customer_admin", "customer_user"]
    role = c4.selectbox("권한", roles, index=1, format_func=lambda r: ROLE_KO[r], key="usr_new_role")
    if st.button("추가", key="usr_add", disabled=not lid.strip()):
        e = email.strip()
        if not q("SELECT 1 FROM app_user WHERE login_id=%s", (lid.strip(),)).empty:
            st.error("이미 사용 중인 아이디입니다.")
        elif auth_utils.email_problem(e):
            st.error(auth_utils.email_problem(e))
        elif e and not q("SELECT 1 FROM app_user WHERE lower(email)=lower(%s)", (e,)).empty:
            st.error("이미 다른 계정에서 쓰는 이메일입니다.")
        else:
            pw = auth_utils.temp_password()
            x("INSERT INTO app_user (company_id, role, login_id, display_name, email, password_hash, must_change_password) "
              "VALUES (%s,%s,%s,NULLIF(%s,''),NULLIF(%s,''),%s,true)",
              (cid, role, lid.strip(), name.strip(), e, auth_utils.hash_password(pw)))
            st.session_state["usr_temp_pw"] = (lid.strip(), pw)
    if "usr_temp_pw" in st.session_state:
        who, pw = st.session_state["usr_temp_pw"]
        st.success(f"{who} 임시 비밀번호(첫 로그인 시 변경):")
        st.code(pw)

    others = users[users["user_id"] != _user()["user_id"]]
    if others.empty:
        return
    st.subheader("사용 중지 / 비밀번호 초기화")
    uid = _pick("사용자", {int(r.user_id): f"{r.아이디} ({r.이름 or ''})" for r in others.itertuples()}, "usr_pick")
    c1, c2 = st.columns(2)
    active = bool(others[others["user_id"] == uid].iloc[0]["사용"])
    if c1.button("사용 중지" if active else "다시 사용", key="usr_toggle"):
        x("UPDATE app_user SET is_active = NOT is_active WHERE user_id=%s AND company_id=%s", (uid, cid))
        st.rerun()
    if c2.button("비밀번호 초기화", key="usr_reset"):
        pw = auth_utils.temp_password()
        x("UPDATE app_user SET password_hash=%s, must_change_password=true WHERE user_id=%s AND company_id=%s",
          (auth_utils.hash_password(pw), uid, cid))
        st.session_state["usr_temp_pw"] = (str(others[others["user_id"] == uid].iloc[0]["아이디"]), pw)
        st.rerun()


def page_profile(ctx=None):
    st.header("👤 내 정보")
    u = _user()
    me = q("SELECT login_id, display_name, email, email_verified FROM app_user WHERE user_id=%s", (u["user_id"],)).iloc[0]
    st.markdown(f"아이디: **{me['login_id']}** · 등급: **{TIER_KO[u['customer_type']]}** · 권한: {ROLE_KO[u['role']]}")
    name = st.text_input("이름", value=me["display_name"] if pd.notna(me["display_name"]) else "", key="prof_name")
    email = st.text_input("이메일(알림·커뮤니티 로그인에 사용)", value=me["email"] if pd.notna(me["email"]) else "",
                          key="prof_email")
    if pd.notna(me["email"]):
        st.caption("✅ 확인된 이메일" if me["email_verified"] else "⏳ 아직 확인되지 않은 이메일(운영사 확인 후 커뮤니티 사용 가능)")
    if st.button("저장", type="primary", key="prof_save"):
        e = email.strip()
        problem = auth_utils.email_problem(e)
        if problem:
            st.error(problem)
        elif e and not q("SELECT 1 FROM app_user WHERE lower(email)=lower(%s) AND user_id<>%s", (e, u["user_id"])).empty:
            st.error("이미 다른 계정에서 쓰는 이메일입니다.")
        else:
            changed = (e or None) != (me["email"] if pd.notna(me["email"]) else None)
            x("UPDATE app_user SET display_name=NULLIF(%s,''), email=NULLIF(%s,''), "
              "email_verified = CASE WHEN %s THEN false ELSE email_verified END WHERE user_id=%s",
              (name.strip(), e, changed, u["user_id"]))
            u["name"] = name.strip() or u["login_id"]
            st.success("저장했습니다." + (" 이메일이 바뀌어 다시 확인이 필요합니다." if changed and e else ""))
            st.rerun()
    st.caption("커뮤니티에서는 회사명 대신 이름(또는 아이디)과 업종만 표시됩니다.")


def page_password(forced=False):
    st.header("🔑 비밀번호 변경")
    if forced:
        st.warning("임시 비밀번호로 로그인했습니다. 새 비밀번호를 정해야 계속 사용할 수 있습니다.")
    cur_pw = st.text_input("현재 비밀번호", type="password", key="pw_cur")
    new1 = st.text_input("새 비밀번호(8자 이상, 영문+숫자)", type="password", key="pw_new1")
    new2 = st.text_input("새 비밀번호 확인", type="password", key="pw_new2")
    if st.button("변경", type="primary", key="pw_go"):
        u = _user()
        stored = q("SELECT password_hash FROM app_user WHERE user_id=%s", (u["user_id"],)).iloc[0]["password_hash"]
        problem = auth_utils.password_problem(new1)
        if not auth_utils.verify_password(cur_pw, stored):
            st.error("현재 비밀번호가 맞지 않습니다.")
        elif problem:
            st.error(problem)
        elif new1 != new2:
            st.error("새 비밀번호가 서로 다릅니다.")
        elif new1 == cur_pw:
            st.error("현재와 다른 비밀번호를 정하세요.")
        else:
            x("UPDATE app_user SET password_hash=%s, must_change_password=false WHERE user_id=%s",
              (auth_utils.hash_password(new1), u["user_id"]))
            u["must_change_password"] = False
            st.success("변경했습니다.")
            st.rerun()


# ---------------------------------------------------------------------------
# 📝 신청 정보 (입력은 고객, 생성은 운영자) — 14번 마이그레이션
# ---------------------------------------------------------------------------
STAGE_HELP = {
    "draft": "입력 중입니다. 필수(*) 항목만 채우면 제출할 수 있고, 선택 항목은 비워 두면 운영사가 판단해 채웁니다.",
    "submitted": "제출되었습니다. 운영사가 검토를 시작하면 '운영자 보완' 단계로 바뀝니다.",
    "completing": "운영사가 비어 있는 항목을 판단해 채우고 있습니다. 확인이 꼭 필요한 항목이 있으면 아래에 표시됩니다.",
    "generating": "운영사가 경영시스템 문서를 만들고 있습니다.",
    "customer_review": "문서가 만들어졌습니다. 운영사가 판단해 채운 항목을 확인해 주세요(응답하지 않은 항목은 운영사 판단대로 확정됩니다).",
    "finalized": "확정되었습니다.",
}
def _providers():
    return ic.make_providers(q)


def _intake_fields():
    df = q("SELECT field_code, section, section_seq, label, input_type, is_required, options, help_text "
           "FROM intake_field WHERE is_active ORDER BY section_seq, sort_order")
    return df.to_dict("records")


def _intake_state(intake_id):
    vals = q("SELECT field_code, value, source, confirm_required, confirm_status, customer_comment "
             "FROM intake_value WHERE intake_id=%s", (intake_id,))
    files = q("SELECT field_code, file_id, file_name, storage_path FROM intake_file WHERE intake_id=%s "
              "ORDER BY file_id", (intake_id,))
    values = {r.field_code: r.value for r in vals.itertuples()}
    return vals, values, files


def _save_intake_values(intake_id, fields, new_values, old_values, providers):
    changed = 0
    for f in fields:
        code = f["field_code"]
        if f["input_type"] == "file" or code not in new_values:
            continue
        v = new_values[code]
        if code == "sector_profile" and v == ic.NO_PROFILE:
            v = None
        if v == old_values.get(code):
            continue
        if old_values.get(code) is None and not ic.is_filled(f, v):
            continue   # 손대지 않은 빈 항목은 저장하지 않음(운영자 화면에 '고객 입력'으로 보이지 않게)
        x("INSERT INTO intake_value (intake_id, field_code, value, source, updated_by_user_id, updated_role) "
          "VALUES (%s,%s,%s::jsonb,%s,%s,'customer') ON CONFLICT (intake_id, field_code) DO UPDATE SET "
          "value=EXCLUDED.value, source=EXCLUDED.source, updated_by_user_id=EXCLUDED.updated_by_user_id, "
          "updated_role='customer', updated_at=now()",
          (intake_id, code, json.dumps(v, ensure_ascii=False), ic.source_for(f, v, new_values, providers),
           _user()["user_id"]))
        changed += 1
    return changed


def _save_intake_files(intake_id, uploads):
    n = 0
    for code, files in uploads.items():
        for fobj in files or []:
            safe = fobj.name.replace("/", "_").replace("\\", "_")
            path = f"intake/{intake_id}/{code}/{uuid.uuid4().hex[:10]}_{safe}"
            gcs_storage.upload_bytes(path, fobj.getvalue())
            x("INSERT INTO intake_file (intake_id, field_code, file_name, storage_path, size_bytes, uploaded_by_user_id) "
              "VALUES (%s,%s,%s,%s,%s,%s)", (intake_id, code, fobj.name, path, fobj.size, _user()["user_id"]))
            n += 1
    return n


def _stage_move(intake_id, frm, to, note=None, extra_sql=""):
    x(f"UPDATE intake_request SET stage=%s{extra_sql} WHERE intake_id=%s AND stage=%s", (to, intake_id, frm))
    x("INSERT INTO intake_stage_log (intake_id, from_stage, to_stage, actor_role, actor_user_id, note) "
      "VALUES (%s,%s,%s,'customer',%s,%s)", (intake_id, frm, to, _user()["user_id"], note))


def page_intake(ctx=None):
    st.header("📝 신청 정보")
    u = _user()
    reqs = q("SELECT r.intake_id, r.stage, r.created_at, r.submitted_at, a.project_no FROM intake_request r "
             "LEFT JOIN application a ON a.application_id = r.application_id WHERE r.company_id=%s "
             "ORDER BY r.intake_id DESC", (u["company_id"],))
    has_draft = (reqs["stage"] == "draft").any() if len(reqs) else False
    if u["role"] == "customer_admin" and not has_draft:
        st.caption("인증 받을 경영시스템 문서를 새로 신청할 때 시작합니다(규격 추가·개정판 전환 포함).")
        if st.button("➕ 새 신청 시작", key="intake_new"):
            co = q("SELECT company_name, biz_reg_no FROM company WHERE company_id=%s", (u["company_id"],)).iloc[0]
            iid = x("INSERT INTO intake_request (company_id, created_by_user_id) VALUES (%s,%s) RETURNING intake_id",
                    (u["company_id"], u["user_id"]))
            for code, v in (("company_name", co["company_name"]), ("biz_reg_no", co["biz_reg_no"])):
                if v:
                    x("INSERT INTO intake_value (intake_id, field_code, value, updated_by_user_id) "
                      "VALUES (%s,%s,%s::jsonb,%s)", (iid, code, json.dumps(v, ensure_ascii=False), u["user_id"]))
            x("INSERT INTO intake_stage_log (intake_id, to_stage, actor_role, actor_user_id) "
              "VALUES (%s,'draft','customer',%s)", (iid, u["user_id"]))
            st.session_state["intake_pick"] = int(iid)
            st.rerun()
    if reqs.empty:
        st.info("진행 중인 신청이 없습니다." + ("" if u["role"] == "customer_admin" else " 회사 관리자가 신청을 시작할 수 있습니다."))
        return
    labels = {int(r.intake_id): f"신청 #{r.intake_id} · {ic.STAGE_LABEL[r.stage]}"
              + (f" · {r.project_no}" if isinstance(r.project_no, str) else "") for r in reqs.itertuples()}
    if st.session_state.get("intake_pick") not in labels:
        st.session_state.pop("intake_pick", None)
    intake_id = _pick("신청", labels, "intake_pick")
    stage = reqs.set_index("intake_id").loc[intake_id, "stage"]
    st.progress((ic.STAGES.index(stage) + 1) / len(ic.STAGES), text=ic.STAGE_LABEL[stage])
    st.info(STAGE_HELP[stage])

    fields = _intake_fields()
    providers = _providers()
    vals, values, files = _intake_state(intake_id)
    file_counts = files.groupby("field_code").size().to_dict() if len(files) else {}

    if stage == "draft":
        _render_intake_form(intake_id, fields, values, files, file_counts, providers)
    else:
        _render_intake_readonly(intake_id, stage, fields, vals, values, files)


def _render_intake_form(intake_id, fields, values, files, file_counts, providers):
    cur = dict(values)
    uploads = {}
    sections = []
    for f in fields:
        if f["section"] not in sections:
            sections.append(f["section"])
    for sec in sections:
        with st.expander(sec, expanded=True):
            for f in [f for f in fields if f["section"] == sec]:
                if not ic.is_visible(f, cur):
                    continue
                code = f["field_code"]
                key = f"ik_{intake_id}_{code}"
                if f["input_type"] == "checklist":
                    key += f"_{cur.get('sector_profile') or 0}"
                v = ic.render_field(st, f, values.get(code), cur, providers, key)
                if f["input_type"] == "file":
                    uploads[code] = v
                    have = files[files["field_code"] == code] if len(files) else files
                    if len(have):
                        st.caption("올린 파일: " + ", ".join(have["file_name"]))
                else:
                    cur[code] = v
    done, total = ic.progress(fields, cur, {**file_counts, **{k: file_counts.get(k, 0) + len(v or [])
                                                              for k, v in uploads.items()}})
    st.progress(done / total if total else 1.0, text=f"필수 항목 {done}/{total}")
    c1, c2 = st.columns(2)
    if c1.button("💾 임시 저장", key=f"ik_save_{intake_id}"):
        n = _save_intake_values(intake_id, fields, cur, values, providers)
        m = _save_intake_files(intake_id, uploads)
        st.success(f"저장했습니다(항목 {n}개" + (f", 파일 {m}개" if m else "") + ").")
    is_admin = _user()["role"] == "customer_admin"
    if c2.button("📨 제출", type="primary", key=f"ik_submit_{intake_id}", disabled=not is_admin):
        _save_intake_values(intake_id, fields, cur, values, providers)
        _save_intake_files(intake_id, uploads)
        _, values2, files2 = _intake_state(intake_id)
        fc2 = files2.groupby("field_code").size().to_dict() if len(files2) else {}
        missing = ic.missing_required(fields, values2, fc2)
        if missing:
            st.error("필수 항목을 채워 주세요: " + ", ".join(missing))
        else:
            _stage_move(intake_id, "draft", "submitted", extra_sql=", submitted_at=now()")
            st.success("제출했습니다. 이후 필요한 확인은 문서가 만들어진 뒤 한 번에 요청드립니다.")
            st.rerun()
    if not is_admin:
        st.caption("제출은 회사 관리자가 합니다.")


def _render_intake_readonly(intake_id, stage, fields, vals, values, files):
    meta = vals.set_index("field_code") if len(vals) else None
    rows = []
    for f in fields:
        if not ic.is_visible(f, values):
            continue
        code = f["field_code"]
        if f["input_type"] == "file":
            have = files[files["field_code"] == code] if len(files) else files
            shown = ", ".join(have["file_name"]) if len(have) else "—"
            src = "고객 입력" if len(have) else ""
        else:
            shown = ic.display_value(f, values.get(code))
            src = ic.SOURCE_LABEL.get(meta.loc[code, "source"], "") if meta is not None and code in meta.index else ""
        rows.append({"구분": f["section"], "항목": f["label"], "내용": shown, "출처": src})
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # 확인할 항목: 운영자가 '확인 필요'로 지정한 것(어느 단계든) + 고객 확인 단계의 운영자 추정값
    if meta is None:
        return
    targets = vals[(vals["confirm_status"] == "pending")
                   | ((stage == "customer_review") & (vals["source"] == "operator_inferred")
                      & vals["confirm_status"].isna())]
    flabel = {f["field_code"]: f for f in fields}
    if len(targets):
        st.subheader(f"확인해 주세요 ({len(targets)}건)")
        answers = {}
        for r in targets.itertuples():
            f = flabel.get(r.field_code)
            if not f:
                continue
            st.markdown(f"**{f['label']}** — 운영사 판단: {ic.display_value(f, r.value)}"
                        + (" · ❗생성 전 확인 필요" if r.confirm_required else ""))
            a = st.radio("응답", ["맞음", "수정"], horizontal=True, key=f"ikc_{intake_id}_{r.field_code}",
                         label_visibility="collapsed")
            fix = st.text_input("올바른 내용", key=f"ikc_fix_{intake_id}_{r.field_code}") if a == "수정" else ""
            answers[r.field_code] = (a, fix)
        if st.button("응답 보내기", type="primary", key=f"ikc_send_{intake_id}"):
            for code, (a, fix) in answers.items():
                if a == "맞음":
                    x("UPDATE intake_value SET confirm_status='confirmed', source='customer_confirmed', "
                      "updated_role='customer', updated_by_user_id=%s, updated_at=now() WHERE intake_id=%s AND field_code=%s",
                      (_user()["user_id"], intake_id, code))
                else:
                    x("UPDATE intake_value SET confirm_status='corrected', customer_comment=%s, updated_role='customer', "
                      "updated_by_user_id=%s, updated_at=now() WHERE intake_id=%s AND field_code=%s",
                      (fix, _user()["user_id"], intake_id, code))
            st.success("보냈습니다. 수정하신 내용은 운영사가 문서에 반영합니다.")
            st.rerun()

    if stage == "customer_review":
        app = q("SELECT application_id FROM intake_request WHERE intake_id=%s", (intake_id,)).iloc[0]["application_id"]
        if pd.notna(app):
            st.subheader("만들어진 문서")
            docs = q("SELECT di.doc_id, dt.doc_type_code, dt.doc_type_name, di.revision_no, di.storage_path "
                     "FROM document_individual di JOIN doc_type dt ON dt.doc_type_id = di.doc_type_id "
                     "WHERE di.application_id=%s AND di.storage_path IS NOT NULL ORDER BY dt.doc_type_code", (int(app),))
            st.dataframe(docs.drop(columns=["doc_id", "storage_path"]), use_container_width=True, hide_index=True)
            if len(docs) and st.button("문서 전체 받기(zip) 준비", key=f"ik_docs_zip_{intake_id}"):
                buf = io.BytesIO()
                with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                    for p in docs["storage_path"]:
                        zf.writestr("/".join(p.split("/")[2:]) or p, gcs_storage.download_bytes(p))
                st.session_state[f"ik_docs_zip_{intake_id}_data"] = buf.getvalue()
            if f"ik_docs_zip_{intake_id}_data" in st.session_state:
                st.download_button("zip 저장", st.session_state[f"ik_docs_zip_{intake_id}_data"],
                                   file_name=f"review_{intake_id}.zip", key=f"ik_docs_zip_save_{intake_id}")
        reviewed = q("SELECT customer_reviewed_at FROM intake_request WHERE intake_id=%s", (intake_id,)).iloc[0, 0]
        if pd.notna(reviewed):
            st.success(f"확인 완료를 보냈습니다({str(reviewed)[:16]}). 운영사가 확정합니다.")
        elif st.button("✅ 확인 완료", key=f"ik_reviewed_{intake_id}", disabled=_user()["role"] != "customer_admin"):
            x("UPDATE intake_request SET customer_reviewed_at=now() WHERE intake_id=%s", (intake_id,))
            x("INSERT INTO intake_stage_log (intake_id, from_stage, to_stage, actor_role, actor_user_id, note) "
              "VALUES (%s,'customer_review','customer_review','customer',%s,'고객 확인 완료')", (intake_id, _user()["user_id"]))
            st.rerun()


# ---------------------------------------------------------------------------
# 라우팅
# ---------------------------------------------------------------------------
MENUS = {
    "branch": ["📝 신청 정보", "📘 내 문서함", "📁 파일 보관함", "✍ 기록 입력", "📊 기록 대장", "📋 기록 작성 예시",
               "🔒 공개 설정", "🕵 운영자 접근", "👥 사용자 관리", "👤 내 정보", "🔑 비밀번호 변경"],
    "local_branch": ["📝 신청 정보", "✍ 기록 입력", "📋 기록 작성 예시", "🔒 공개 설정", "👥 사용자 관리",
                     "👤 내 정보", "🔑 비밀번호 변경"],
}
PAGES = {
    "📝 신청 정보": page_intake,
    "👤 내 정보": page_profile,
    "📥 다운로드 키로 문서 받기": lambda ctx: (st.header("📥 다운로드 키로 문서 받기"), page_download_key()),
    "📘 내 문서함": page_documents, "📁 파일 보관함": page_files, "✍ 기록 입력": page_record_entry,
    "📊 기록 대장": page_ledger, "📋 기록 작성 예시": page_templates, "🔒 공개 설정": page_disclosure,
    "🕵 운영자 접근": page_operator_access, "👥 사용자 관리": page_users,
}


def main():
    try:
        _conn()
    except Exception as e:  # noqa: BLE001
        st.error(f"DB 연결 실패: {e}")
        st.stop()
    if not bool(q("SELECT to_regclass('public.v_member_sso') IS NOT NULL AS ok").iloc[0]["ok"]):
        st.error("브랜치용 테이블이 없습니다. scripts의 12, 13, 14, 15번 마이그레이션을 먼저 실행하세요.")
        st.stop()

    u = _user()
    if not u:
        page_login()
        return

    st.sidebar.title("고객 포털")
    st.sidebar.markdown(f"**{u['company_name']}**  \n{u['name']} · {ROLE_KO[u['role']]}")
    st.sidebar.caption(TIER_KO[u["customer_type"]])
    if st.sidebar.button("로그아웃", key="logout"):
        st.session_state.clear()
        st.rerun()
    if u["must_change_password"]:
        page_password(forced=True)
        return

    if u["customer_type"] in ("simple", "free"):
        choice = st.sidebar.radio("메뉴", BASIC_MENU, key="nav")
        if choice == "🔑 비밀번호 변경":
            page_password()
        else:
            PAGES[choice](None)
        return

    apps = _my_apps()
    if apps.empty:
        # 신청건이 아직 없으면(처음 신청하는 고객) 신청 정보 입력부터
        menu = ["📝 신청 정보", "👥 사용자 관리", "👤 내 정보", "🔑 비밀번호 변경"]
        choice = st.sidebar.radio("메뉴", menu, key="nav")
        if choice == "🔑 비밀번호 변경":
            page_password()
        else:
            PAGES[choice](None)
        return
    app_id = int(st.sidebar.selectbox(
        "신청건", apps["application_id"].tolist(),
        format_func=lambda a: apps.set_index("application_id").loc[a, "project_no"], key="cur_app"))
    ctx = _app_ctx(app_id)

    menu = MENUS[ctx["customer_type"]]
    if st.session_state.get("nav_goto") in menu:
        st.session_state["nav"] = st.session_state.pop("nav_goto")
    choice = st.sidebar.radio("메뉴", menu, key="nav")
    if choice == "🔑 비밀번호 변경":
        page_password()
    else:
        PAGES[choice](ctx)


main()
