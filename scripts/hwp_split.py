"""
hwp_split.py — "문서분리" 어댑터 (2026-09-13, "3플랫폼 제작" 세션의 기존 분리
프로그램을 "문서관리" 화면에 통합 — 방법1. 같은 날 5차에서 화면에서 뺐다가,
6차에서 "분리기준표 자동 생성" 방식으로 재도입함)

핵심 분리 로직(pyhwpx로 통합 HWP를 앵커 텍스트 기준 블록 선택→저장)은
hwp_splitter.py에 그대로 옮겨와 있습니다(사용자가 이미 검증한 코드, 수정하지
않음). 이 파일은 그 엔진을 "문서관리" 화면(app.py)이 기대하는 인터페이스로
감싸는 얇은 어댑터입니다.

원래 방식(분리기준표.xlsx 직접 준비)은 split_hwp_file()로 그대로 남겨뒀지만,
실사용에서는 이게 매 프로젝트 파일마다 새로 만들어야 하는 부담이 커서(사용자
피드백, 2026-09-13) 기본 경로는 build_virtual_tasks_from_doc_list() +
split_hwp_file_auto()로 바뀌었습니다: hwp_splitter.SplitTask가 필요로 하는
필드(구분/현재표시기호/문서명/파일이름/유지 시작·끝구간)를 이 신청건에 이미
등록된 문서 목록(doc_type, 코드+명칭, 이미 화면에 표시되는 그 순서)에서 그대로
계산해 만들어 냅니다 — "유지 끝구간"은 사실상 항상 "다음 항목 코드 직전"(마지막
항목만 "문서 끝")이라 자동 계산이 가능하기 때문입니다. 두 경로 모두 실제 엔진
루프(_run_engine)를 공유하므로 앵커 탐색·저장 로직은 완전히 동일합니다.

  - 기준표의 "현재표시기호"는 그 프로젝트의 project 접두어가 붙어 있을 수
    있습니다(예: 절차서는 "qM0000P410"처럼 std+sector 접두어가 붙고, 양식은
    "F410-01"처럼 이미 doc_type.doc_type_code 그대로인 경우가 확인됨).
    extract_doc_type_code()가 알려진 doc_type_code 형태(M001/P610/
    P812(HS-1)/F612e-01 등)를 문자열 끝에서 찾아 접두어를 떼어냅니다.
    매칭되지 않는 코드(표지, 목차 등 doc_type이 아닌 페이지)는 조용히
    건너뛰고 app.py가 "수동 확인 필요" 목록으로 보여줍니다.
"""
import re
from pathlib import Path

import hwp_splitter

# doc_type.doc_type_code로 쓰이는 알려진 형태만 인식(끝에서부터 매칭해
# 프로젝트별 접두어를 제거). 새로운 코드 형태가 나오면 이 패턴에 추가하세요.
_DOC_CODE_PATTERN = re.compile(r"(M\d{3}|P\d{3}(?:\([^)]*\))?|F\d{3}[a-z]?-\d{2})$")

# 파일명 전체(예: "qM0000P410_조직의상황관리.hwp", "P610 리스크및기회관리.hwp")
# 어디서든 코드를 찾기 위한 버전 — 끝이 아니라 뒤에 숫자가 더 이어지지만 않으면
# (오탐 방지: "P4100"이 "P410"으로 잘못 잡히는 것 방지) 첫 매치를 사용. 괄호 뒤
# 접미어는 실제 doc_type_code에 쓰이는 HS/EHS 구분자 형태만 인정한다(예:
# "P812(HS-1)") — 사람이 파일명에 덧붙인 한글 설명("P530(조직관리)")까지
# 코드의 일부로 잘못 삼키는 것을 방지하기 위함(끝앵커용 _DOC_CODE_PATTERN과
# 다른 점).
_DOC_CODE_PATTERN_ANYWHERE = re.compile(r"(M\d{3}|P\d{3}(?:\(E?HS-\d\))?|F\d{3}[a-z]?-\d{2})(?!\d)")

# 사람이 지은 파일명은 문자와 숫자 사이에 하이픈을 넣는 경우가 흔함(예: "P-530",
# "F-410-01") — 실제 doc_type_code에는 그 하이픈이 없으므로(P530, F410-01)
# 매칭 전에 letter-하이픈-숫자 형태만 정규화해서 제거한다.
_LETTER_HYPHEN_NUM = re.compile(r"\b([MPF])-(\d{3})")

# 파일이름에 못 쓰는 문자(윈도우 기준) 치환용.
_UNSAFE_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|]')


def extract_doc_type_code(raw_code: str) -> str | None:
    """분리기준표의 '현재표시기호'에서 doc_type.doc_type_code에 해당하는
    부분만 뽑아낸다. 매칭되는 패턴이 없으면 None(표지/목차 등 doc_type이
    아닌 항목으로 간주)."""
    raw_code = (raw_code or "").strip()
    m = _DOC_CODE_PATTERN.search(raw_code)
    return m.group(1) if m else None


def extract_doc_type_code_from_filename(filename: str) -> str | None:
    """분산된 완성본 파일들을 일괄 업로드할 때, 파일명 어디에 코드가 있어도
    (접두어/접미어에 설명 텍스트가 붙어 있어도, "P-530"처럼 문자·숫자 사이에
    하이픈이 있어도) doc_type_code를 찾아낸다. extract_doc_type_code()와 달리
    문자열 '끝'이 아니라 파일명 전체에서 찾는다 — 분리기준표의 '표시기호' 셀
    (코드만 있음)이 아니라 사람이 지은 자유 형식 파일명을 대상으로 하기 때문.
    매칭 실패 시 None."""
    stem = (filename or "").rsplit(".", 1)[0]
    normalized = _LETTER_HYPHEN_NUM.sub(r"\1\2", stem)
    m = _DOC_CODE_PATTERN_ANYWHERE.search(normalized)
    return m.group(1) if m else None


def build_virtual_tasks_from_doc_list(doc_rows: list) -> list:
    """분리기준표 xlsx 없이, 이 신청건에 이미 적용되는 문서 목록에서 "가상
    분리기준표"(SplitTask 리스트)를 자동 생성한다(2026-09-13, 문서분리 재도입).

    doc_rows: [{"category": "manual"|"procedure"|"form",
                "doc_type_code": str, "doc_type_name": str}, ...]
    — 반드시 통합본 안에서 실제로 등장하는 순서와 같아야 한다(순서가 다르면
    앵커를 못 찾거나 엉뚱한 구간이 잘릴 수 있음). app.py에서 사용자가 순서를
    조정/제외할 수 있는 표를 보여준 뒤, 그 결과를 이 함수에 넘긴다.

    "유지 시작구간"은 그 항목의 코드 자신, "유지 끝구간"은 다음 항목 코드
    직전(마지막 항목은 "문서 끝")으로 자동 계산한다 — 실제 분리기준표에서도
    이 두 값이 사실상 이렇게 계산 가능한 값이었기 때문에(사용자가 손으로
    입력했을 뿐 로직상 파생값), 자동 생성이 원본 기준표와 동등하다.
    """
    n = len(doc_rows)
    tasks = []
    for i, row in enumerate(doc_rows):
        code = str(row["doc_type_code"]).strip()
        name = str(row["doc_type_name"]).strip()
        구분 = "양식" if row.get("category") == "form" else "절차서"
        if i == n - 1:
            끝구간 = "문서 끝"
        else:
            끝구간 = f"{str(doc_rows[i + 1]['doc_type_code']).strip()} 직전"
        safe_name = _UNSAFE_FILENAME_CHARS.sub("_", name)
        tasks.append(hwp_splitter.SplitTask(
            row_index=i,
            구분=구분,
            현재표시기호=code,
            문서명_또는_양식명=name,
            파일이름=f"{code}_{safe_name}.hwp",
            유지_시작구간=code,
            유지_끝구간_raw=끝구간,
            복제_기준_원본="",
        ))
    return tasks


def _run_engine(master_hwp_path: str, tasks: list, output_dir: str,
                 anchor_mode: str, visible: bool, progress_cb) -> list:
    """hwp_splitter.HwpEngine을 이용해 tasks를 실행하고, app.py가 기대하는
    dict 리스트로 변환한다. split_hwp_file()/split_hwp_file_auto() 공용 루프
    (엔진/앵커 재시도 로직은 완전히 동일, tasks를 어떻게 만들었는지만 다름)."""
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    code_to_title = hwp_splitter.build_code_to_title_map(tasks)
    modes_to_try = ["title", "code"] if anchor_mode == "both" else [anchor_mode]

    engine = hwp_splitter.HwpEngine(visible=visible)
    raw_results = []
    try:
        for i, task in enumerate(tasks, start=1):
            result = None
            for mode in modes_to_try:
                result = engine.run_task(master_hwp_path, task, code_to_title, mode, output_dir)
                if result.status == "성공":
                    break
            raw_results.append(result)
            if progress_cb:
                progress_cb(i, len(tasks), result)
    finally:
        engine.close()

    out = []
    for r in raw_results:
        out.append({
            "raw_code": r.task.현재표시기호,
            "doc_type_code": extract_doc_type_code(r.task.현재표시기호) if r.status == "성공" else None,
            "구분": r.task.구분,
            "파일이름": r.task.파일이름,
            "status": r.status,
            "message": r.message,
            "file_path": r.output_path,
        })
    return out


def split_hwp_file(master_hwp_path: str, criteria_xlsx_path: str, output_dir: str,
                    anchor_mode: str = "both", visible: bool = False,
                    progress_cb=None) -> list:
    """(기존 방식, 필요시 사용) 통합 HWP를 criteria_xlsx_path(사람이 직접 준비한
    분리기준표)에 따라 output_dir 아래 개별 파일들로 분리한다. 보통은
    split_hwp_file_auto()(기준표 자동 생성)를 쓰고, 자동 생성 결과가 실제
    통합본과 안 맞을 때만 이 함수로 정밀한 기준표를 직접 준비해 쓴다.

    anchor_mode: "title"(문서명/양식명 텍스트만) / "code"(표시기호 코드 텍스트만) /
    "both"(기본값 — 각 항목마다 title로 먼저 시도하고, 실패하면 그 항목만 code로
    재시도).

    반환값: [{"raw_code": str, "doc_type_code": str|None, "구분": str,
              "파일이름": str, "status": "성공"|"실패"|"수동확인필요",
              "message": str, "file_path": str|None}, ...]
    """
    tasks = hwp_splitter.load_criteria(criteria_xlsx_path)
    return _run_engine(master_hwp_path, tasks, output_dir, anchor_mode, visible, progress_cb)


def split_hwp_file_auto(master_hwp_path: str, doc_rows: list, output_dir: str,
                         anchor_mode: str = "both", visible: bool = False,
                         progress_cb=None) -> list:
    """(기본 방식, 2026-09-13 재도입) 분리기준표 xlsx 없이, 이 신청건의 문서
    목록(doc_rows — build_virtual_tasks_from_doc_list() 참고)만으로 통합 HWP를
    분리한다. 반환값 형식은 split_hwp_file()과 동일."""
    tasks = build_virtual_tasks_from_doc_list(doc_rows)
    return _run_engine(master_hwp_path, tasks, output_dir, anchor_mode, visible, progress_cb)
