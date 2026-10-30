# hub_branch_v4 — 회원 정보 보완(커뮤니티 SSO 준비) (2026-10-30)

## 파일 (ims-catalog-app 폴더에 덮어쓰기) — v3 전체 포함
- app.py, branch_app.py              (교체)
- scripts/auth_utils.py               (교체) 이메일 형식 확인 추가
- scripts/15_migrate_member_sso.py    (신규)
- 나머지 scripts는 v3와 동일

## 실행 순서 (이미 실행한 번호는 다시 실행해도 안전)
python scripts/12_migrate_hub_branch.py
python scripts/13_migrate_branch_app.py
python scripts/14_migrate_intake.py
python scripts/15_migrate_member_sso.py
streamlit run app.py
streamlit run branch_app.py --server.port 8502
