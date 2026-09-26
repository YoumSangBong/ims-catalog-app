"""
GCS(Cloud Storage) 연결 테스트 스크립트
사용법: ims-catalog-app 폴더에 이 파일을 넣고, 가상환경 활성화 후
    python 00_test_gcs_connection.py
로 실행하세요.

사전 준비 (README 안내대로 완료됐어야 함):
  1. secrets/gcs-key.json 존재
  2. .env에 GCS_BUCKET_NAME, GOOGLE_APPLICATION_CREDENTIALS 설정
  3. pip install google-cloud-storage python-dotenv 완료
     (python-dotenv는 기존 00_test_connection.py에서 이미 설치되어 있을 것)
"""
import os
from dotenv import load_dotenv

load_dotenv()

bucket_name = os.getenv("GCS_BUCKET_NAME")
cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

print(f"버킷 이름: {bucket_name}")
print(f"키 파일 경로: {cred_path}")

if not bucket_name or not cred_path:
    raise SystemExit(
        "오류: .env에 GCS_BUCKET_NAME 또는 GOOGLE_APPLICATION_CREDENTIALS가 없습니다. "
        ".env 파일을 확인하세요."
    )

if not os.path.exists(cred_path):
    raise SystemExit(
        f"오류: 키 파일을 찾을 수 없습니다 -> {cred_path}\n"
        "secrets/gcs-key.json 파일이 실제로 그 위치에 있는지 확인하세요."
    )

from google.cloud import storage  # noqa: E402

# 서비스 계정 키로 클라이언트 생성
client = storage.Client.from_service_account_json(cred_path)
bucket = client.bucket(bucket_name)
# 참고: 서비스 계정에 "Storage 개체 관리자"(objectAdmin) 권한만 있으면
# 버킷 자체를 조회하는 bucket.exists()는 403이 날 수 있음(정상) —
# 실제 파일 업로드/다운로드는 개체(object) 권한만으로 충분하므로
# 여기서는 바로 업로드 테스트로 넘어간다.

# 1) 테스트 파일 업로드
test_path = "_connection_test/hello.txt"
blob = bucket.blob(test_path)
blob.upload_from_string("GCS 연결 테스트 성공!", content_type="text/plain")
print(f"업로드 성공: gs://{bucket_name}/{test_path}")

# 3) 다시 읽어서 확인
downloaded = blob.download_as_text()
print(f"다운로드 확인: {downloaded!r}")

# 4) 테스트 파일 삭제 (버킷을 깨끗하게 유지)
blob.delete()
print("테스트 파일 삭제 완료.")

print("\n모든 테스트 통과 - GCS 연동 준비 완료.")
