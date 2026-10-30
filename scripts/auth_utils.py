"""
허브/브랜치 공용 인증 유틸 (2026-10-29). 외부 패키지 없이 표준 라이브러리만 사용.

비밀번호 저장 형식: pbkdf2_sha256$<반복횟수>$<salt hex>$<hash hex>
"""
import hashlib
import hmac
import secrets

ITERATIONS = 200_000
MIN_PASSWORD_LEN = 8


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    return f"pbkdf2_sha256${ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored or not password:
        return False
    try:
        algo, iters, salt_hex, hash_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iters))
        return hmac.compare_digest(dk.hex(), hash_hex)
    except (ValueError, TypeError):
        return False


def password_problem(password: str) -> str | None:
    """정책 위반 사유(없으면 None): 8자 이상, 영문과 숫자 포함."""
    if len(password or "") < MIN_PASSWORD_LEN:
        return f"비밀번호는 {MIN_PASSWORD_LEN}자 이상이어야 합니다."
    if not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
        return "비밀번호에 영문과 숫자를 모두 포함하세요."
    return None


def temp_password() -> str:
    """임시 비밀번호(영문+숫자 10자). 첫 로그인 시 변경 강제."""
    alphabet = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(10))
        if password_problem(pw) is None:
            return pw


def key_hash(key_text: str) -> str:
    """다운로드 키 해시(허브 발급 시 DB의 encode(sha256(...),'hex')와 동일). 공백·대소문자 그대로."""
    return hashlib.sha256(key_text.strip().encode("utf-8")).hexdigest()


def email_problem(email: str) -> str | None:
    """이메일 형식 확인(없으면 None). 빈 값은 호출하는 쪽에서 필수 여부 판단."""
    import re
    e = (email or "").strip()
    if e and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", e):
        return "이메일 형식이 올바르지 않습니다."
    return None
