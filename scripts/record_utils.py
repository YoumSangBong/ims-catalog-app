"""
양식 실적 기록 공용 유틸 (허브 앱 · 향후 브랜치 앱 공용, 2026-10-29)

- 표시 폭/줄 수/숫자 구간 등 필드 사용 메타데이터 계산(form_field_usage용)
- 실적 값 해시
- 로컬 브랜치용 저장 파일(zip = 기록 json + 보기용 표) 생성 / 복구
- 공용 템플릿 제공용 익명화

양식별 필드 정의(form_field)는 5순위에서 확정 예정이므로, 지금은 기록 값을
{"항목": "값"} 형태의 단순 사전으로 다룬다. 필드 정의가 생기면 그 이름을 그대로 키로 쓴다.
"""
import hashlib
import io
import json
import re
import unicodedata
import zipfile
from datetime import date, datetime

LOCAL_FORMAT = "ims-form-record"
LOCAL_FORMAT_VERSION = 1

_NUMERIC_RE = re.compile(r"^[\s+-]?[\d,]+(\.\d+)?\s*$")


# ---------------------------------------------------------------------------
# 필드 메타데이터
# ---------------------------------------------------------------------------
def display_width(text: str) -> int:
    """전각(한글·한자·전각기호)=2, 그 외=1. 여러 줄이면 가장 긴 줄 기준."""
    if not text:
        return 0
    return max(
        sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in line)
        for line in str(text).splitlines() or [""]
    )


def is_numeric_value(text) -> bool:
    return bool(text) and bool(_NUMERIC_RE.match(str(text)))


def numeric_bucket(text) -> str:
    """정수부 자릿수 구간만 남김(규모 노출 방지): '1-3' | '4-6' | '7-9' | '10+'."""
    digits = len(re.sub(r"\D", "", str(text).split(".")[0]))
    if digits <= 3:
        return "1-3"
    if digits <= 6:
        return "4-6"
    if digits <= 9:
        return "7-9"
    return "10+"


def field_usage_rows(payload: dict, field_widths: dict | None = None) -> list[dict]:
    """기록 값 사전 → form_field_usage 행(내용 없이 길이 정보만).
    field_widths: {항목: 현재 칸 폭(표시 폭 단위)} — 알면 넘침 여부 계산, 모르면 None."""
    rows = []
    for name, value in payload.items():
        text = "" if value is None else str(value)
        filled = text.strip() != ""
        row = {"field_name": str(name)[:100], "is_filled": filled,
               "char_count": None, "display_width": None, "line_count": None,
               "overflow": None, "numeric_bucket": None}
        if filled and is_numeric_value(text):
            row["numeric_bucket"] = numeric_bucket(text)
        elif filled:
            w = display_width(text)
            row.update(char_count=len(text), display_width=w,
                       line_count=len(text.splitlines()) or 1)
            limit = (field_widths or {}).get(name)
            if limit:
                row["overflow"] = w > int(limit)
        rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# 해시 / 로컬 저장 파일
# ---------------------------------------------------------------------------
def payload_hash(payload: dict) -> str:
    canon = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def _json_default(o):
    if isinstance(o, (date, datetime)):
        return o.isoformat()
    return str(o)


def build_local_package(meta: dict, payload: dict) -> bytes:
    """로컬 브랜치용 저장 파일(zip). 서버에는 저장하지 않는다.
    meta: project_no, doc_type_code, doc_type_name, form_revision_no, record_date, evidence_ref"""
    doc = {
        "format": LOCAL_FORMAT,
        "version": LOCAL_FORMAT_VERSION,
        **meta,
        "payload": payload,
        "payload_hash": payload_hash(payload),
        "exported_at": datetime.now().isoformat(timespec="seconds"),
    }
    base = f"{meta.get('doc_type_code', 'form')}_{meta.get('record_date', '')}"
    lines = ["항목,값"] + [
        '"{}","{}"'.format(str(k).replace('"', '""'), str(v).replace('"', '""'))
        for k, v in payload.items()
    ]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{base}.json", json.dumps(doc, ensure_ascii=False, indent=2, default=_json_default))
        # 엑셀에서 한글이 깨지지 않도록 BOM 포함
        zf.writestr(f"{base}_보기용.csv", "﻿" + "\n".join(lines))
    return buf.getvalue()


def read_local_package(data: bytes) -> dict:
    """zip 또는 json 바이트 → 기록 사전. 형식·해시가 맞지 않으면 ValueError."""
    if data[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = [n for n in zf.namelist() if n.lower().endswith(".json")]
            if not names:
                raise ValueError("zip 안에 기록 json 파일이 없습니다.")
            data = zf.read(names[0])
    try:
        doc = json.loads(data.decode("utf-8-sig"))
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"기록 파일을 읽을 수 없습니다: {e}") from e
    if doc.get("format") != LOCAL_FORMAT or not isinstance(doc.get("payload"), dict):
        raise ValueError("이 플랫폼에서 내려받은 기록 파일이 아닙니다.")
    doc["hash_ok"] = payload_hash(doc["payload"]) == doc.get("payload_hash")
    return doc


# ---------------------------------------------------------------------------
# 익명화 (공용 템플릿 제공용)
# ---------------------------------------------------------------------------
_PHONE_RE = re.compile(r"\b0\d{1,2}-?\d{3,4}-?\d{4}\b")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_BIZNO_RE = re.compile(r"\b\d{3}-?\d{2}-?\d{5}\b")


def anonymize_payload(payload: dict, sensitive_terms: list[str] | None = None) -> dict:
    """회사명·인명 등 지정 단어 → 일반명칭, 연락처/이메일/사업자번호 제거, 숫자 → 자릿수 구간.
    sensitive_terms: 회사명, 담당자명, 거래처명 등(긴 것부터 치환)."""
    terms = sorted({t.strip() for t in (sensitive_terms or []) if t and t.strip()}, key=len, reverse=True)
    out = {}
    for k, v in payload.items():
        text = "" if v is None else str(v)
        if is_numeric_value(text):
            out[k] = f"[{numeric_bucket(text)}자리 수]"
            continue
        text = _EMAIL_RE.sub("[이메일]", text)
        text = _BIZNO_RE.sub("[사업자번호]", text)
        text = _PHONE_RE.sub("[연락처]", text)
        for t in terms:
            text = text.replace(t, "[○○]")
        out[k] = text
    return out
