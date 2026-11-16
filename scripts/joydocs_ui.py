"""
JoyDocs(조이독스) 화면 디자인 공용 모듈 — 허브 앱(app.py)·고객 포털(branch_app.py) 공통.
(2026-11-15 "JoyDocs 플랫폼 UI 개선안" 디자인을 Streamlit에 반영)

로고 사용 규칙
  - 대표 로고: 심볼 + JOYDOCS (상표 출원 기준과 동일)
  - 설명 문구(경영시스템 문서)는 로그인 화면처럼 처음 보는 사람이 있는 화면에만
  - 화면에는 여백 없는 웹·앱용 로고 파일(assets/brand/)을 사용

색상
  NAVY  #1F4E79  기본 색(버튼·선택 메뉴)
  INK   #14233A  본문 글자·로그인 왼쪽 바탕
  CORAL #E8553D  강조(로고의 D, 체크 표시)
"""
import base64
from functools import lru_cache
from pathlib import Path

import streamlit as st

BRAND_DIR = Path(__file__).resolve().parent.parent / "assets" / "brand"

NAVY = "#1F4E79"
INK = "#14233A"
CORAL = "#E8553D"


@lru_cache(maxsize=None)
def _svg_uri(name: str) -> str:
    """assets/brand/ 안의 SVG를 화면에 바로 넣을 수 있는 data URI로 바꾼다."""
    data = (BRAND_DIR / name).read_bytes()
    return "data:image/svg+xml;base64," + base64.b64encode(data).decode("ascii")


# ---------------------------------------------------------------------------
# 공통 스타일
# ---------------------------------------------------------------------------
_BASE_CSS = f"""
<style>
[data-testid="stAppViewContainer"] {{ color: {INK}; }}
[data-testid="stHeader"] {{ background: transparent; }}
.block-container {{ padding-top: 2.2rem; max-width: 1240px; }}

/* 제목 */
h1, h2, h3 {{ color: {INK}; letter-spacing: -0.3px; }}
[data-testid="stHeading"] h2 {{ font-size: 1.6rem; font-weight: 700; }}
.jd-crumb {{ font-size: 13px; color: #5B6475; margin: 0 0 -6px 0; }}

/* 사이드바 */
[data-testid="stSidebar"] {{ background: #F7F9FC; border-right: 1px solid #E1E6ED; }}
[data-testid="stSidebarHeader"] {{ height: 1.2rem; min-height: 0; padding: 0; }}
[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {{ padding-top: 0.4rem; }}
.jd-brand {{ display: flex; flex-direction: column; align-items: flex-start; gap: 10px;
             padding: 0 4px 16px; margin-bottom: 8px; border-bottom: 1px solid #E6EAF0; }}
.jd-brand img {{ height: 30px; width: auto; display: block; }}
.jd-chip {{ font-size: 12px; font-weight: 600; color: {NAVY}; background: #EAF0F6;
            padding: 3px 9px; border-radius: 10px; }}
.jd-group {{ font-size: 12px; font-weight: 600; color: #5B6475; padding: 14px 4px 6px; }}
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] {{ margin-bottom: 0; }}
.jd-status {{ display: flex; align-items: center; gap: 8px; font-size: 12px; color: #556274;
              padding: 12px 4px 0; margin-top: 18px; border-top: 1px solid #E6EAF0; }}
.jd-dot {{ width: 8px; height: 8px; border-radius: 4px; background: #15803D; display: inline-block; }}
.jd-dot.err {{ background: #C9432C; }}

/* 사이드바 메뉴 버튼: 왼쪽 정렬된 목록처럼 */
[data-testid="stSidebar"] .stButton button {{
    justify-content: flex-start; border: 0; box-shadow: none; min-height: 38px;
    padding: 0 10px; border-radius: 8px; font-size: 14px; color: #333A47; background: transparent;
}}
[data-testid="stSidebar"] .stButton button:hover {{ background: #EEF2F7; color: {INK}; }}
[data-testid="stSidebar"] .stButton button[kind="primary"],
[data-testid="stSidebar"] .stButton button[data-testid="stBaseButton-primary"] {{
    background: #EAF0F6; color: {NAVY}; font-weight: 600;
}}
[data-testid="stSidebar"] .stButton button p {{ font-size: 14px; }}
[data-testid="stSidebar"] .stButton button > div {{ justify-content: flex-start; width: 100%; gap: 10px; }}
[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {{ gap: 2px; }}

/* 본문 버튼·입력 */
[data-testid="stMain"] button[data-testid^="stBaseButton-primary"] {{ background: {NAVY}; border-color: {NAVY}; color: #FFFFFF; }}
[data-testid="stMain"] button[data-testid^="stBaseButton-primary"]:hover {{ background: {INK}; border-color: {INK}; }}
.stButton button, .stDownloadButton button, .stFormSubmitButton button {{ border-radius: 8px; font-weight: 600; }}
[data-baseweb="input"], [data-baseweb="select"] > div, [data-baseweb="textarea"] {{ border-radius: 8px; }}

/* 탭: 알약 모양 */
[data-testid="stTabs"] [role="tablist"] {{ gap: 4px; background: #F1F3F7; padding: 4px; border-radius: 10px;
                                          width: fit-content; max-width: 100%; }}
[data-testid="stTabs"] [role="tab"] {{ height: 34px; padding: 0 14px; border-radius: 7px; }}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] {{ background: #FFFFFF;
                                                           box-shadow: 0 1px 2px rgba(16,24,40,0.08); }}
[data-testid="stTabs"] [data-baseweb="tab-highlight"],
[data-testid="stTabs"] [data-baseweb="tab-border"] {{ display: none; }}

/* 표 */
[data-testid="stDataFrame"], [data-testid="stTable"] {{ border: 1px solid #E3E7EE; border-radius: 12px;
                                                       overflow: hidden; }}
[data-testid="stCaptionContainer"] {{ color: #5B6475; }}
</style>
"""

_LOGIN_CSS = f"""
<style>
.block-container {{ padding-top: 1.5rem; max-width: 1280px; }}
.jd-hero {{ background: {INK}; color: #FFFFFF; border-radius: 16px; padding: 44px 48px;
            min-height: 78vh; box-sizing: border-box; display: flex; flex-direction: column;
            justify-content: space-between; gap: 40px; }}
.jd-hero img.jd-logo {{ height: 52px; width: auto; display: block; align-self: flex-start; }}
.jd-hero h1 {{ margin: 0 0 22px; font-size: 34px; line-height: 1.35; font-weight: 700;
               letter-spacing: -0.5px; color: #FFFFFF; padding: 0; }}
.jd-hero p {{ margin: 0 0 22px; font-size: 15px; line-height: 1.7; color: #C9D2DE; max-width: 460px; }}
.jd-hero ul {{ margin: 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: 14px; }}
.jd-hero li {{ display: flex; align-items: center; gap: 12px; font-size: 14px; color: #FFFFFF; }}
.jd-hero li span.jd-opt {{ color: #A9B4C3; }}
.jd-hero .jd-copy {{ font-size: 12px; color: #A9B4C3; }}
.jd-login-symbol {{ display: flex; justify-content: center; margin: 9vh 0 14px; }}
.jd-login-symbol img {{ width: 44px; height: 44px; }}
.jd-login-title {{ margin: 0; font-size: 22px; font-weight: 700; color: {INK}; }}
.jd-login-sub {{ margin: 4px 0 6px; font-size: 13px; color: #556274; }}
</style>
"""

_CHECK = (f'<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="{CORAL}" stroke-width="2.4" '
          'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12l5 5L20 7"/></svg>')


def apply_theme():
    """모든 화면 공통 스타일. set_page_config 바로 다음에 한 번 호출."""
    st.markdown(_BASE_CSS, unsafe_allow_html=True)


def page_header(title: str, crumb: str | None = None):
    """화면 제목(위에 작은 경로 표시)."""
    if crumb:
        st.markdown(f'<p class="jd-crumb">{crumb}</p>', unsafe_allow_html=True)
    st.header(title, anchor=False)


# ---------------------------------------------------------------------------
# 사이드바
# ---------------------------------------------------------------------------
def sidebar_brand(chip: str | None = None):
    """사이드바 맨 위 대표 로고(심볼 + JOYDOCS, 설명 문구 없음)와 역할 표시."""
    chip_html = f'<span class="jd-chip">{chip}</span>' if chip else ""
    st.sidebar.markdown(
        f'<div class="jd-brand"><img src="{_svg_uri("joydocs_light.svg")}" alt="JOYDOCS">{chip_html}</div>',
        unsafe_allow_html=True,
    )


def sidebar_nav(groups, key: str, default: str) -> str:
    """그룹으로 묶인 사이드바 메뉴. 선택한 항목의 값(value)을 돌려준다.

    groups = [("그룹 이름", [(value, 표시 이름, ":material/아이콘:"), ...]), ...]
    """
    values = [v for _, items in groups for v, _, _ in items]
    if st.session_state.get(key) not in values:
        st.session_state[key] = default
    for group, items in groups:
        st.sidebar.markdown(f'<div class="jd-group">{group}</div>', unsafe_allow_html=True)
        for value, label, icon in items:
            active = st.session_state[key] == value
            if st.sidebar.button(label, key=f"{key}__{value}", icon=icon,
                                 type="primary" if active else "secondary", width="stretch"):
                if not active:
                    st.session_state[key] = value
                    st.rerun()
    return st.session_state[key]


def sidebar_status(ok: bool, left: str, right: str = ""):
    """사이드바 아래 연결 상태 표시."""
    st.sidebar.markdown(
        f'<div class="jd-status"><span class="jd-dot{"" if ok else " err"}"></span>'
        f'<span style="flex:1">{left}</span><span>{right}</span></div>',
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# 고객 포털 로그인
# ---------------------------------------------------------------------------
LOGIN_HEADLINE = "경영시스템 문서를<br>바로 받고, 계속 관리하세요"
LOGIN_INTRO = "인증에 필요한 매뉴얼, 절차서, 양식을 회사 정보에 맞춰 생성하고 한곳에서 보관합니다."
LOGIN_POINTS = [("발행 문서 다운로드와 개정 이력 관리", ""), ("양식별 실적 기록 작성·보관", "(옵션)")]


def apply_login_theme():
    st.markdown(_LOGIN_CSS, unsafe_allow_html=True)


def login_hero(copyright_text: str = "© JoyDocs"):
    """로그인 화면 왼쪽 소개 영역(설명 문구 포함 로고)."""
    points = "".join(
        f'<li>{_CHECK}<span>{text}{f" <span class=jd-opt>{opt}</span>" if opt else ""}</span></li>'
        for text, opt in LOGIN_POINTS
    )
    st.markdown(
        f"""<div class="jd-hero">
<img class="jd-logo" src="{_svg_uri('joydocs_desc_dark.svg')}" alt="JOYDOCS 경영시스템 문서">
<div><h1>{LOGIN_HEADLINE}</h1><p>{LOGIN_INTRO}</p><ul>{points}</ul></div>
<span class="jd-copy">{copyright_text}</span>
</div>""",
        unsafe_allow_html=True,
    )


def login_symbol():
    """로그인 카드 위 작은 컬러 심볼."""
    st.markdown(
        f'<div class="jd-login-symbol"><img src="{_svg_uri("joydocs_symbol.svg")}" alt=""></div>',
        unsafe_allow_html=True,
    )


def login_title(title: str = "로그인", sub: str = "조이독스 고객 포털에 오신 것을 환영합니다"):
    st.markdown(f'<p class="jd-login-title">{title}</p><p class="jd-login-sub">{sub}</p>',
                unsafe_allow_html=True)
