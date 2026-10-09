import os
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-secret-change-this-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def create_access_token(user_id: str, email: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": user_id, "email": email, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None


# --- Email verification / password reset (new) ---

def generate_otp_code() -> str:
    """6-digit numeric code like '042918', from `secrets` (cryptographically
    secure) rather than `random`."""
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_otp_code(code: str) -> str:
    return hash_password(code)


def verify_otp_code(code: str, code_hash: str) -> bool:
    return verify_password(code, code_hash)


def generate_verification_token() -> str:
    """One-time token returned after a code is verified; the final step
    (set password / reset password) must present it, so nobody can skip
    straight to that step knowing only an email address."""
    return secrets.token_urlsafe(32)
