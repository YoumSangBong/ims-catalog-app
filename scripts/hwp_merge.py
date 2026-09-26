# -*- coding: utf-8 -*-
"""
hwp_merge.py — "문서통합" 물리적 병합 자동화 (2026-09-13 작성, 2026-09-13 재검토판)

*** 여전히 미검증 초안입니다 — 반드시 실제 한글 PC에서 백업 후, 파일 2~3개만으로
    먼저 테스트해주세요. hwp_splitter.py(분리)와 달리, "여러 파일을 하나로
    합치는" 병합 프로그램은 사용자로부터 전달받은 적이 없어서, 검증된 프로그램을
    그대로 이식한 게 아닙니다. ***

이번 재검토에서 바뀐 점 (사용자가 공유해주신 "3플랫폼 제작" 세션 대화 내용 반영):

  1. 이전 초안에 있던 `hwp.insert_file()` 우선 시도는 삭제했습니다.
     — hwp_splitter.py(HwpEngine, 검증된 실물 코드)의 어디에도 insert_file은
       등장하지 않습니다. 실제로 그런 메서드가 있는지조차 확인된 적이 없어서
       "우선 방법"으로 놓는 건 근거가 약하다고 판단했습니다. (완전히 빼지는
       않고, 실패해도 무해하므로 맨 처음에 한 번 시도만 하고 바로 fallback함)
  2. 기본 방법(fallback→사실상 주 방법)을 hwp_splitter.py가 실제로 쓰는 것과
     동일한 저수준 API 호출로만 구성했습니다: open / MoveDocBegin / MoveDocEnd /
     get_pos / select_text / Copy / Paste / FileNew / save_as / Quit.
     "전체 선택" 부분은 split 코드의 fallback 선택 로직(MoveDocBegin→get_pos,
     MoveDocEnd→get_pos, select_text(시작,끝))과 완전히 동일한 패턴이고,
     대상이 "찾은 구간"이 아니라 "문서 전체"라는 점만 다릅니다.
  3. 다만 이렇게 해도 "완전히 검증됐다"고는 할 수 없습니다 — split 프로그램은
     "한 파일을 열어 구간을 잘라 저장"만 반복했지, "여러 파일을 순서대로 복사해서
     하나의 누적 문서에 이어 붙이는" 작업은 그 프로그램에서 한 번도 실행해본 적이
     없는 새로운 조합입니다. 그래서 개별 API 호출은 전부 실물 코드에서 그대로
     가져왔지만, 그것들을 이렇게 순서대로 조합했을 때 실제로 서식이 안 깨지고
     동작하는지는 이번에 처음 확인하는 것입니다.
  4. 페이지나눔(BreakPage)·쪽번호 연속성은 반영을 "시도"만 합니다 — 대화록에
     "HWP 페이지 번호 필드 문제를 상용구 삽입으로 해결했다"는 내용이 있는데,
     그 상용구 자체(실제 코드)는 전달받지 못해서 그대로 이식할 수 없었습니다.
     즉 병합 후 쪽번호가 꼬일 가능성이 있고, 실제 PC 확인이 꼭 필요합니다.

사용법: (Windows, 한글 설치·로그인된 PC에서)
    pip install pyhwpx

호출 계약(app.py 쪽은 그대로 두어도 됨):
    merge_hwp_files(local_paths, output_path, visible=False)
    - local_paths: 병합할 순서대로 정렬된 완성본 .hwp 로컬 경로 리스트
      (순서 정렬은 app.py의 _doc_list_for_application()이 이미 매뉴얼→절차서→
      코드번호 순으로 해주고 있어서, 이 함수는 "받은 순서 그대로" 합칩니다.)
    - 실패 시 예외를 던집니다(NotImplementedError: pyhwpx 없음 / 그 외: 병합 중 오류).
      app.py는 이미 이 두 경우를 구분해서 처리하도록 되어 있습니다.
"""


def _select_whole_document(hwp) -> None:
    """현재 hwp에 열려있는 문서 전체를 선택한다.

    hwp_splitter.py의 fallback 선택 로직(MoveDocBegin→get_pos, MoveDocEnd→get_pos,
    select_text(시작,끝))과 동일한 패턴을 그대로 사용 — 대상만 "찾은 구간"이
    아니라 "문서 전체"로 바꿨다.
    """
    hwp.MoveDocBegin()
    begin_pos = hwp.get_pos()
    hwp.MoveDocEnd()
    end_pos = hwp.get_pos()
    hwp.select_text(begin_pos, end_pos)


def merge_hwp_files(local_paths: list, output_path: str, visible: bool = False) -> None:
    """local_paths(순서대로 병합할 완성본 .hwp 로컬 경로 목록)를 하나의
    output_path로 합친다. 첫 번째 파일을 기준 문서(서식·머리말 유지)로 열고,
    나머지 파일을 차례로 문서 끝에 이어붙인 뒤 output_path로 저장한다.
    """
    if not local_paths:
        raise ValueError("병합할 파일이 없습니다.")

    try:
        from pyhwpx import Hwp  # noqa: 로컬(Windows) 환경에서만 성공
    except ImportError as e:
        raise NotImplementedError(
            "pyhwpx를 불러올 수 없습니다. 이 기능은 한글(한컴오피스)이 설치된 "
            "Windows PC에서 `pip install pyhwpx` 후 로컬로 실행해야 합니다."
        ) from e

    hwp = Hwp(visible=visible)
    try:
        # 1) 첫 번째 파일을 기준 문서로 연다 — 이 문서의 용지/머리말/쪽번호
        #    설정이 병합본 전체의 기준이 된다.
        hwp.open(local_paths[0])

        # 2) 나머지 파일을 차례로 문서 끝에 이어붙인다.
        for path in local_paths[1:]:
            hwp.MoveDocEnd()

            # (참고용 1회 시도) insert_file이 실제로 있고 커서 위치에 다른 hwp
            # 파일을 통째로 삽입해준다면 가장 깔끔하지만, hwp_splitter.py(검증된
            # 실물 코드)에는 등장하지 않는 메서드라 존재 여부 자체가 불확실합니다.
            # 없거나 실패해도 무해하므로, 있으면 쓰고 없으면 바로 아래 fallback으로.
            inserted = False
            if hasattr(hwp, "insert_file"):
                try:
                    hwp.insert_file(path)
                    inserted = True
                except Exception:
                    inserted = False

            if not inserted:
                # fallback(=사실상 주 방법): 별도 인스턴스에서 원본을 열어 전체
                # 선택 → 복사(원본은 절대 수정하지 않음) → 기준 문서에 붙여넣기.
                # Windows 클립보드는 프로세스 공유 자원이라, 다른 Hwp 인스턴스에서
                # Copy()해도 기준 문서(hwp)에서 Paste()로 받을 수 있다는 전제이며,
                # 이 전제 자체가 이번에 처음 실물 확인이 필요한 부분입니다.
                sub_hwp = Hwp(visible=visible)
                try:
                    sub_hwp.open(path)
                    _select_whole_document(sub_hwp)
                    sub_hwp.Copy()
                finally:
                    sub_hwp.Quit()

                hwp.MoveDocEnd()

                # 문서 구분을 위해 쪽나눔을 시도한다 — pyhwpx/한글 버전에 따라
                # 지원 여부가 다를 수 있어 실패해도 병합 자체는 계속 진행한다.
                # ★ 미검증: 이 방식이 맞는지, 아니면 쪽번호가 이어지도록 놔둬야
                #   하는지는 실물 PC에서 확인이 필요합니다(대화록의 "상용구로
                #   쪽번호 문제 해결" 사례 참고 — 그 상용구 자체는 전달받지 못함).
                try:
                    hwp.HAction.Run("BreakPage")
                except Exception:
                    pass

                hwp.Paste()

        # 3) 병합된 문서를 저장.
        hwp.save_as(output_path, format="HWP")
    finally:
        try:
            hwp.Quit()
        except Exception:
            pass
