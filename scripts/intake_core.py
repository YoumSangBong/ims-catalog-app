"""
신청 정보 일괄 입력 공용 모듈 (브랜치 앱 입력 화면 · 허브 앱 접수 화면 공용, 2026-10-29)

DB에 직접 접근하지 않는다. 선택지·업종 기본값은 호출하는 앱이 providers로 넘겨준다:
  providers = {
    "standards":     () -> {std_code: 표시명},
    "sector_main":   () -> {code: 표시명},
    "profiles":      (sector_main_code) -> {profile_id: 표시명},
    "profile_items": (profile_id, key) -> [항목, ...],   # key = env_aspects / hazards / key_laws_sh ...
  }
"""
STAGES = ["draft", "submitted", "completing", "generating", "customer_review", "finalized"]
STAGE_LABEL = {
    "draft": "① 입력중", "submitted": "② 제출", "completing": "③ 운영자 보완",
    "generating": "④ 생성중", "customer_review": "⑤ 고객 확인", "finalized": "⑥ 확정",
}
SOURCE_LABEL = {
    "customer": "고객 입력", "profile_default": "업종 기본값",
    "operator_inferred": "운영자 추정", "customer_confirmed": "고객 확인",
}
CONFIRM_LABEL = {"pending": "확인 대기", "confirmed": "맞음", "corrected": "수정함", "auto_accepted": "미응답→적용"}
NO_PROFILE = 0   # 세부 업종 '모름'


def std_families(codes):
    return {str(c).lower() for c in (codes or [])}


def _opts(field):
    o = field.get("options")
    return o if isinstance(o, dict) else {}


def is_visible(field, values):
    """규격 선택에 따라 보이는 항목(예: 환경측면은 14001 선택 시에만)."""
    need = _opts(field).get("std")
    if not need:
        return True
    need = need if isinstance(need, list) else [need]
    fam = std_families(values.get("standards"))
    return bool(fam & set(need))


def is_filled(field, value, file_count=0):
    t = field["input_type"]
    if t == "file":
        return file_count > 0
    if value is None:
        return False
    if t in ("text", "textarea", "select"):
        return str(value).strip() != "" and value != NO_PROFILE
    if t == "multiselect":
        return len(value) > 0
    if t == "yesno_reason":
        ans = (value or {}).get("answer")
        return ans == "있음" or (ans == "없음" and str((value or {}).get("reason", "")).strip() != "")
    if t == "dept_list":
        return any(str(d.get("부서명", "")).strip() for d in value or [])
    if t == "checklist":
        return bool((value or {}).get("checked")) or str((value or {}).get("extra", "")).strip() != ""
    return False


def missing_required(fields, values, file_counts=None):
    """제출 전 미입력 필수 항목 라벨 목록(보이지 않는 항목은 제외)."""
    file_counts = file_counts or {}
    return [f["label"] for f in fields
            if f["is_required"] and is_visible(f, values)
            and not is_filled(f, values.get(f["field_code"]), file_counts.get(f["field_code"], 0))]


def progress(fields, values, file_counts=None):
    file_counts = file_counts or {}
    req = [f for f in fields if f["is_required"] and is_visible(f, values)]
    done = sum(is_filled(f, values.get(f["field_code"]), file_counts.get(f["field_code"], 0)) for f in req)
    return done, len(req)


def profile_default(field, values, providers):
    """체크리스트 항목의 업종 기본값(세부 업종을 골랐을 때만)."""
    pid = values.get("sector_profile")
    keys = _opts(field).get("profile_key")
    if not pid or pid == NO_PROFILE or not keys:
        return []
    keys = keys if isinstance(keys, list) else [keys]
    items = []
    for k in keys:
        for it in providers["profile_items"](pid, k) or []:
            if it not in items:
                items.append(it)
    return items


def source_for(field, value, values, providers):
    """저장 시 출처 판정: 체크리스트를 손대지 않았으면 '업종 기본값'."""
    if field["input_type"] == "checklist":
        default = profile_default(field, values, providers)
        v = value or {}
        if default and list(v.get("checked") or []) == default and not str(v.get("extra", "")).strip():
            return "profile_default"
    return "customer"


def display_value(field, value):
    """읽기 전용 표시용 문자열."""
    t = field["input_type"]
    if value is None or value == "" or value == []:
        return "—"
    if t == "multiselect":
        return ", ".join(map(str, value))
    if t == "yesno_reason":
        v = value or {}
        return v.get("answer", "—") + (f" (사유: {v.get('reason')})" if v.get("answer") == "없음" else "")
    if t == "dept_list":
        return ", ".join(
            d.get("부서명", "") + (f"({d['부서장']})" if d.get("부서장") else "")
            + (f"←{d['상위부서']}" if d.get("상위부서") else "")
            for d in value if str(d.get("부서명", "")).strip())
    if t == "checklist":
        v = value or {}
        s = ", ".join(v.get("checked") or [])
        return s + (f" / 추가: {v['extra']}" if str(v.get("extra", "")).strip() else "") or "—"
    return str(value)


# ---------------------------------------------------------------------------
# 선택지 제공자 (q: SQL → DataFrame 함수를 받아 허브·브랜치가 같은 목록을 씀)
# ---------------------------------------------------------------------------
_PROFILE_KEYS = {"env_aspects", "hazards", "key_laws_env", "key_laws_sh", "quality_chars", "process_hints"}


def make_providers(q):
    import json

    def standards():
        df = q("SELECT std_code, iso_num, edition_label FROM standard WHERE COALESCE(is_active, true) "
               "AND (valid_until IS NULL OR valid_until >= current_date) ORDER BY sort_order, std_code")
        return {r.std_code: f"{r.std_code} — {r.iso_num}" + (f" {r.edition_label}" if r.edition_label else "")
                for r in df.itertuples()}

    def sector_main():
        return {r.code: f"{r.code} — {r.name}" for r in q("SELECT code, name FROM sector_main ORDER BY code").itertuples()}

    def profiles(main):
        df = q("SELECT profile_id, sector_code, profile_seq, sector_name FROM sector_profile WHERE sector_main=%s "
               "ORDER BY sector_code, profile_seq", (main,))
        return {int(r.profile_id): f"{r.sector_code}{int(r.profile_seq):02d} {r.sector_name}" for r in df.itertuples()}

    def profile_items(pid, key):
        if key not in _PROFILE_KEYS:
            return []
        df = q(f"SELECT {key} AS v FROM sector_profile WHERE profile_id=%s", (int(pid),))
        v = df.iloc[0]["v"] if len(df) else []
        if isinstance(v, str):
            v = json.loads(v)
        return [str(i) for i in (v or [])]

    return {"standards": standards, "sector_main": sector_main, "profiles": profiles, "profile_items": profile_items}


# ---------------------------------------------------------------------------
# Streamlit 렌더링 (st를 인자로 받아 앱에 종속되지 않게)
# ---------------------------------------------------------------------------
def render_field(st, field, value, values, providers, key, disabled=False):
    """한 항목 입력 위젯 → 새 값(file 타입은 업로드 파일 리스트 반환)."""
    import pandas as pd

    t = field["input_type"]
    label = field["label"] + (" *" if field["is_required"] else "")
    help_text = field.get("help_text") or None
    opts = _opts(field)

    if t == "text":
        return st.text_input(label, value=value or "", help=help_text, key=key, disabled=disabled).strip()
    if t == "textarea":
        return st.text_area(label, value=value or "", help=help_text, key=key, disabled=disabled, height=80).strip()
    if t == "select":
        if opts.get("source") == "sector_main":
            choices = providers["sector_main"]()
        elif opts.get("source") == "sector_profile":
            choices = {NO_PROFILE: "(모름 — 운영자가 판단)"}
            choices.update(providers["profiles"](values.get("sector_main")) if values.get("sector_main") else {})
        else:
            choices = {c: c for c in opts.get("choices", [])}
        ids = list(choices)
        if not ids:
            st.caption(f"{label}: 선택지 없음")
            return value
        idx = ids.index(value) if value in ids else 0
        if field["is_required"] and value not in ids and opts.get("source") != "sector_profile":
            ids = [""] + ids
            choices = {"": "선택하세요", **choices}
            idx = 0
        v = st.selectbox(label, ids, index=idx, format_func=lambda c: choices.get(c, str(c)),
                         help=help_text, key=key, disabled=disabled)
        return v
    if t == "multiselect":
        choices = providers["standards"]() if opts.get("source") == "standard" else {c: c for c in opts.get("choices", [])}
        cur = [c for c in (value or []) if c in choices]
        return st.multiselect(label, list(choices), default=cur, format_func=lambda c: choices.get(c, c),
                              help=help_text, key=key, disabled=disabled)
    if t == "yesno_reason":
        v = value or {"answer": opts.get("default", "있음"), "reason": ""}
        ans = st.radio(label, ["있음", "없음"], index=0 if v.get("answer") != "없음" else 1, horizontal=True,
                       help=help_text, key=key + "_a", disabled=disabled)
        reason = ""
        if ans == "없음":
            reason = st.text_input("'없음' 사유 *", value=v.get("reason", ""), key=key + "_r", disabled=disabled).strip()
        return {"answer": ans, "reason": reason}
    if t == "dept_list":
        st.markdown(f"**{label}**")
        if help_text:
            st.caption(help_text)
        rows = value or [{"부서명": "", "부서장": "", "상위부서": ""}]
        df = pd.DataFrame(rows, columns=["부서명", "부서장", "상위부서"])
        ed = st.data_editor(df, num_rows="dynamic", use_container_width=True, key=key, disabled=disabled)
        out = []
        for r in ed.itertuples(index=False):
            name = "" if pd.isna(r[0]) else str(r[0]).strip()
            if name:
                out.append({"부서명": name, "부서장": "" if pd.isna(r[1]) else str(r[1]).strip(),
                            "상위부서": "" if pd.isna(r[2]) else str(r[2]).strip()})
        return out
    if t == "checklist":
        st.markdown(f"**{label}**")
        default = profile_default(field, values, providers)
        v = value if value is not None else {"checked": default, "extra": ""}
        if not default:
            st.caption("세부 업종을 고르지 않아 기본 목록이 없습니다. 아시는 내용만 적어 주시면 나머지는 운영자가 판단합니다.")
            checked = list(v.get("checked") or [])
        else:
            if help_text:
                st.caption(help_text)
            pool = default + [c for c in (v.get("checked") or []) if c not in default]
            checked = st.multiselect("해당 항목", pool, default=[c for c in (v.get("checked") or []) if c in pool],
                                     key=key + "_c", disabled=disabled, label_visibility="collapsed")
        extra = st.text_input("목록에 없는 항목(쉼표 구분)", value=v.get("extra", ""), key=key + "_x",
                              disabled=disabled).strip()
        return {"checked": checked, "extra": extra}
    if t == "file":
        return st.file_uploader(label, accept_multiple_files=True, help=help_text, key=key, disabled=disabled)
    st.caption(f"알 수 없는 입력 형식: {t}")
    return value
