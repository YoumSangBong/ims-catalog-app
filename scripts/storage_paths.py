"""
storage_paths.py — GCS 저장 경로 규칙 (2026-09-13 확정)

경로 규칙:
  {std_code}/{project_no}/{category}/{doc_type_code}_rev{revision_no}.{format}

category 6종 (storage folder 6분류에 대응):
  integrated          통합본
  individual          매뉴얼/절차서 완성본
  individual_content  매뉴얼/절차서 내용본
  form                양식
  guideline           지침서 완성본
  guideline_content   지침서 내용본
"""

CATEGORY_INTEGRATED = "integrated"
CATEGORY_INDIVIDUAL = "individual"
CATEGORY_INDIVIDUAL_CONTENT = "individual_content"
CATEGORY_FORM = "form"
CATEGORY_GUIDELINE = "guideline"
CATEGORY_GUIDELINE_CONTENT = "guideline_content"

# 화면 표시용 한글 레이블
CATEGORY_LABELS = {
    CATEGORY_INTEGRATED: "통합본",
    CATEGORY_INDIVIDUAL: "매뉴얼/절차서",
    CATEGORY_INDIVIDUAL_CONTENT: "매뉴얼/절차서(내용본)",
    CATEGORY_FORM: "양식",
    CATEGORY_GUIDELINE: "지침서",
    CATEGORY_GUIDELINE_CONTENT: "지침서(내용본)",
}


def category_for_doc_type(doc_type_category: str, is_content: bool = False) -> str:
    """doc_type.category('manual'|'procedure'|'form'|'guideline')와 내용본 여부로
    storage 경로의 category 세그먼트를 결정한다."""
    if doc_type_category == "form":
        return CATEGORY_FORM
    if doc_type_category == "guideline":
        return CATEGORY_GUIDELINE_CONTENT if is_content else CATEGORY_GUIDELINE
    # manual, procedure
    return CATEGORY_INDIVIDUAL_CONTENT if is_content else CATEGORY_INDIVIDUAL


def build_storage_path(std_code: str, project_no: str, category: str,
                        doc_type_code: str, revision_no: int, fmt: str) -> str:
    """개별본/내용본 경로. 예: e/e_test1/individual/P612_rev1.hwp"""
    return f"{std_code}/{project_no}/{category}/{doc_type_code}_rev{revision_no}.{fmt}"


def build_integrated_path(std_code: str, project_no: str, bundle_scope: str,
                           revision_no: int, fmt: str) -> str:
    """통합본 경로. 예: e/e_test1/integrated/core_rev1.hwp"""
    return f"{std_code}/{project_no}/{CATEGORY_INTEGRATED}/{bundle_scope}_rev{revision_no}.{fmt}"
