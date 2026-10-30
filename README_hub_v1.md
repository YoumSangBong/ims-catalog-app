# hub_update_v1 — 허브 앱 1단계 (2026-10-29)

## 교체/추가 파일
- app.py (교체) — 4. 고객·발행 관리 / 5. 양식 실적 기록 / 6. 템플릿 관리 추가. 1~3번 화면은 변경 없음.
- scripts/record_utils.py (신규) — 메타데이터·익명화·로컬 기록 파일 유틸
- scripts/12_migrate_hub_branch.py (교체) — 접속을 기존 스크립트처럼 db.py(.env의 DB_HOST 등)로 변경

## 순서
1. 위 파일을 ims-catalog-app 폴더에 덮어쓰기
2. python scripts/12_migrate_hub_branch.py   ("완료" 메시지 확인)
3. streamlit run app.py
