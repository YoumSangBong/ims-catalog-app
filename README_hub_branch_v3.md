# hub_branch_v3 — 신청 정보 일괄 입력(입력은 고객, 생성은 운영자) (2026-10-29)

## 파일 (ims-catalog-app 폴더에 덮어쓰기) — v2 전체 포함
- app.py, branch_app.py                     (교체)
- scripts/intake_core.py                     (신규) 신청 입력 공용 모듈
- scripts/14_migrate_intake.py               (신규) 신청 입력 테이블 + 항목 마스터 23개
- scripts/record_utils.py, auth_utils.py, 12_..., 13_... (v2와 동일, 처음 받는 경우 필요)

## 실행 순서 (이미 실행한 번호는 다시 실행해도 안전)
1. python scripts/12_migrate_hub_branch.py
2. python scripts/13_migrate_branch_app.py
3. python scripts/14_migrate_intake.py
4. streamlit run app.py                          (허브, 8501)
5. streamlit run branch_app.py --server.port 8502 (브랜치, 8502)

## 처음 써볼 때
1. 허브 [4 → 고객 유형 → ➕ 신규 고객(회사) 등록] → [브랜치 계정]에서 관리자 계정 발급
2. 브랜치 로그인 → [📝 신청 정보 → ➕ 새 신청 시작] → 필수(*)만 채우고 제출
3. 허브 [7. 신청 접수] → 빈 선택 항목 보완(운영자 추정) → 신청건 생성 → 단계 진행
4. 문서 생성 후 '⑤ 고객 확인'으로 넘기면 고객이 추정값을 [맞음/수정]으로 한 번에 확인
5. 허브에서 확정(미응답 추정값은 운영자 판단대로 적용)
