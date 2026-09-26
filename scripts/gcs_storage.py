"""
gcs_storage.py — Google Cloud Storage 업로드/다운로드 헬퍼

.env에 GCS_BUCKET_NAME, GOOGLE_APPLICATION_CREDENTIALS가 설정되어 있어야 합니다
(이미 00_test_gcs_connection.py로 연동 테스트를 완료하셨다면 그대로 재사용됩니다).
"""
import os
from functools import lru_cache

from google.cloud import storage


@lru_cache(maxsize=1)
def _client():
    cred_path = os.environ["GOOGLE_APPLICATION_CREDENTIALS"]
    return storage.Client.from_service_account_json(cred_path)


def _bucket():
    return _client().bucket(os.environ["GCS_BUCKET_NAME"])


def upload_bytes(storage_path: str, data: bytes, content_type: str = "application/octet-stream"):
    """바이트 데이터를 storage_path에 업로드."""
    blob = _bucket().blob(storage_path)
    blob.upload_from_string(data, content_type=content_type)


def upload_file(storage_path: str, local_file_path: str):
    """로컬 파일을 storage_path에 업로드(스트림릿 업로더가 임시 저장한 파일용)."""
    blob = _bucket().blob(storage_path)
    blob.upload_from_filename(local_file_path)


def download_bytes(storage_path: str) -> bytes:
    """storage_path의 파일을 바이트로 다운로드(스트림릿 download_button에 바로 사용)."""
    blob = _bucket().blob(storage_path)
    return blob.download_as_bytes()


def file_exists(storage_path: str) -> bool:
    return _bucket().blob(storage_path).exists()
