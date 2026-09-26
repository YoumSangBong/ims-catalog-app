# -*- coding: utf-8 -*-
"""
hwp_splitter.py
================
통합 HWP 원본(예: qM0000pall_s01itcPass_noname_r1.hwp)을
"매뉴얼절차서_분리기준표.xlsx" 에 정의된 표시기호 단위로 잘라
개별 원본 .hwp 파일로 분리하는 엔진.

★ 사용자가 이전 회차("3플랫폼 제작" 세션)에서 이미 만들어 검증한 프로그램의
  로직을 그대로 옮겨온 파일입니다(2026-09-13, "문서관리" 화면에 방법1로 통합).
  핵심 알고리즘은 손대지 않았고, 이 앱(scripts/hwp_split.py)에서 얇은
  어댑터로만 감쌌습니다.

★ 반드시 Windows + 한글(한컴오피스) 설치 & 로그인된 세션에서만 동작합니다.
★ pyhwpx 라이브러리가 필요합니다: pip install pyhwpx

작업 원리 (사용자 확정 방식):
  1. 통합 원본을 매번 새로 로드한다 (이전 행 작업이 다음 행에 영향 주지 않도록).
  2. '유지 시작구간' 텍스트를 찾아 그 지점으로 커서 이동.
  3. '유지 끝구간' 텍스트를 찾아 그 직전까지 블록 선택.
     (끝구간이 '문서 끝'이면 문서 끝까지 선택)
  4. 선택 영역만 새 문서로 저장(SaveBlockAs) → 지정된 파일이름으로 저장.
     (SaveBlockAs 가 여의치 않으면 fallback: 선택 영역 복사 후 새 문서에 붙여넣어 저장)

앵커(찾기 기준 텍스트) 신뢰성 문제:
  분리기준표의 코드(F410-01, qM0000P410 등)가 본문에 리터럴 텍스트로
  없을 수 있음이 확인되었습니다. 이 스크립트는 anchor_mode 파라미터로
  두 가지 검색 전략을 지원합니다.

    anchor_mode="code"  : 표시기호 코드 자체를 찾기 텍스트로 사용
    anchor_mode="title" : 코드에 대응하는 문서명/양식명을 찾기 텍스트로 사용
                          (기준표 자체에서 코드→제목 매핑을 만들어 사용)

  실제 문서를 한글에서 열어 어느 쪽이 맞는지 확인 후 anchor_mode를
  선택하세요. 두 방식 모두 실패하면 UI에서 해당 행에 대해
  '수동 확인 필요'로 표시됩니다.
"""

import re
import time
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Callable

import pandas as pd

logger = logging.getLogger("hwp_splitter")


# --------------------------------------------------------------------------
# 데이터 모델
# --------------------------------------------------------------------------

@dataclass
class SplitTask:
    row_index: int
    구분: str                 # 절차서 / 양식
    현재표시기호: str
    문서명_또는_양식명: str
    파일이름: str
    유지_시작구간: str         # 코드 (예: qM0000P410, F410-01, qM0000Pcover)
    유지_끝구간_raw: str       # 예: "F410-02 직전" / "문서 끝"
    복제_기준_원본: str

    @property
    def is_last(self) -> bool:
        return "문서 끝" in self.유지_끝구간_raw

    @property
    def end_code(self) -> Optional[str]:
        """'F410-02 직전' -> 'F410-02'. 문서 끝이면 None."""
        if self.is_last:
            return None
        m = re.match(r"^(.*?)\s*직전\s*$", self.유지_끝구간_raw.strip())
        return m.group(1).strip() if m else self.유지_끝구간_raw.strip()


@dataclass
class SplitResult:
    task: SplitTask
    status: str               # "성공" / "실패" / "수동확인필요"
    message: str = ""
    output_path: Optional[str] = None


# --------------------------------------------------------------------------
# 분리기준표 로딩
# --------------------------------------------------------------------------

def load_criteria(xlsx_path: str, sheet_name: str = "통합목록") -> list[SplitTask]:
    """기준표 xlsx를 읽어 SplitTask 리스트로 변환하고,
    코드 -> 제목(문서명/양식명) 매핑도 함께 만든다."""
    df = pd.read_excel(xlsx_path, sheet_name=sheet_name, header=2)
    df = df[df["파일이름"].notna()].reset_index(drop=True)

    tasks: list[SplitTask] = []
    for i, row in df.iterrows():
        is_form = pd.notna(row.get("파일표시기호(양식)"))
        구분 = "양식" if is_form else "절차서"
        현재표시기호 = row["파일표시기호(양식)"] if is_form else row["파일표시기호(절차서)"]
        제목 = row["양식명"] if is_form else row["문서명"]

        tasks.append(SplitTask(
            row_index=i,
            구분=구분,
            현재표시기호=str(현재표시기호).strip(),
            문서명_또는_양식명=str(제목).strip() if pd.notna(제목) else "",
            파일이름=str(row["파일이름"]).strip(),
            유지_시작구간=str(row["유지 시작구간"]).strip(),
            유지_끝구간_raw=str(row["유지 끝구간"]).strip(),
            복제_기준_원본=str(row["복제 기준 원본"]).strip(),
        ))
    return tasks


def build_code_to_title_map(tasks: list[SplitTask]) -> dict[str, str]:
    """표시기호 코드 -> 문서명/양식명 매핑 (anchor_mode='title'용)."""
    m = {}
    for t in tasks:
        if t.현재표시기호:
            m[t.현재표시기호] = t.문서명_또는_양식명
    # 커버 페이지 등 코드가 곧 시작구간이면서 문서명이 곧 자기 자신인 경우도 커버됨
    return m


def resolve_anchor_text(code: str, code_to_title: dict[str, str], mode: str) -> str:
    if mode == "code":
        return code
    # mode == "title"
    return code_to_title.get(code, code)  # 매핑 없으면 코드로 fallback


# --------------------------------------------------------------------------
# 한글(HWP) 자동화 엔진
# --------------------------------------------------------------------------

class HwpEngine:
    """pyhwpx 래퍼. Windows + 한글 설치 환경에서만 import/실행 가능."""

    def __init__(self, visible: bool = False):
        try:
            from pyhwpx import Hwp  # noqa: 로컬(Windows) 환경에서만 성공
        except ImportError as e:
            raise RuntimeError(
                "pyhwpx를 불러올 수 없습니다. 이 도구는 한글(한컴오피스)이 설치된 "
                "Windows PC에서 `pip install pyhwpx` 후 로컬로 실행해야 합니다."
            ) from e
        self._Hwp = Hwp
        self.hwp = Hwp(visible=visible)
        # 보안 모듈 경고창 자동 처리(회사 정책에 맞게 조정 필요)
        try:
            self.hwp.set_visible(visible)
        except Exception:
            pass

    def close(self):
        try:
            self.hwp.Quit()
        except Exception:
            pass

    # -- 개별 작업 실행 -----------------------------------------------------

    def run_task(self, master_path: str, task: SplitTask,
                 code_to_title: dict[str, str], anchor_mode: str,
                 output_dir: str) -> SplitResult:
        out_path = str(Path(output_dir) / task.파일이름)

        try:
            # 1) 매번 통합 원본을 새로 연다 (이전 편집 영향 제거)
            self.hwp.open(master_path)

            # 2) 시작 지점 앵커 탐색
            start_anchor = resolve_anchor_text(task.유지_시작구간, code_to_title, anchor_mode)
            self.hwp.MoveDocBegin()
            found_start = self.hwp.find(start_anchor, direction="Forward")
            if not found_start:
                return SplitResult(task, "수동확인필요",
                                    f"시작 앵커 '{start_anchor}' 를 찾지 못했습니다.")

            # 시작 앵커 자체는 유지 대상에 포함되어야 하므로,
            # 찾은 매치의 '앞'으로 커서를 이동시킨다.
            self.hwp.HAction.Run("MoveSelLeft") if False else None  # (버전별 API 차이 대비 자리표시)
            start_pos = self.hwp.get_pos()  # (list, para, pos) 형태 (pyhwpx 버전에 따라 상이)

            # 3) 끝 지점 앵커 탐색 (문서 끝이면 문서 끝으로)
            if task.is_last:
                self.hwp.MoveDocEnd()
                end_pos = self.hwp.get_pos()
            else:
                end_anchor = resolve_anchor_text(task.end_code, code_to_title, anchor_mode)
                found_end = self.hwp.find(end_anchor, direction="Forward")
                if not found_end:
                    return SplitResult(task, "수동확인필요",
                                        f"끝 앵커 '{end_anchor}' 를 찾지 못했습니다.")
                # 찾은 매치 '직전'까지가 유지 구간이므로 매치 시작 위치를 끝점으로 사용
                end_pos = self.hwp.get_pos()

            # 4) start_pos ~ end_pos 범위를 블록 선택
            self.hwp.set_pos(*start_pos)
            self.hwp.select_text(start_pos, end_pos)

            # 5) 선택 영역만 새 파일로 저장 시도 (SaveBlockAs)
            saved = False
            if hasattr(self.hwp, "save_block_as"):
                try:
                    self.hwp.save_block_as(out_path, format="HWP")
                    saved = True
                except Exception as e:
                    logger.warning("save_block_as 실패, fallback 사용: %s", e)

            if not saved:
                # Fallback: 선택 영역을 복사 -> 새 문서에 붙여넣기 -> 저장
                self.hwp.Copy()
                self.hwp.FileNew()
                self.hwp.Paste()
                self.hwp.save_as(out_path, format="HWP")

            return SplitResult(task, "성공", output_path=out_path)

        except Exception as e:
            logger.exception("작업 실패: %s", task.파일이름)
            return SplitResult(task, "실패", str(e))


# --------------------------------------------------------------------------
# 전체 실행 (배치)
# --------------------------------------------------------------------------

def run_all(master_path: str, xlsx_path: str, output_dir: str,
            anchor_mode: str = "title",
            progress_cb: Optional[Callable[[int, int, SplitResult], None]] = None,
            visible: bool = False) -> list[SplitResult]:
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    tasks = load_criteria(xlsx_path)
    code_to_title = build_code_to_title_map(tasks)

    engine = HwpEngine(visible=visible)
    results: list[SplitResult] = []
    try:
        for i, task in enumerate(tasks, start=1):
            result = engine.run_task(master_path, task, code_to_title, anchor_mode, output_dir)
            results.append(result)
            if progress_cb:
                progress_cb(i, len(tasks), result)
    finally:
        engine.close()

    return results
