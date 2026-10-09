from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, EmailStr, Field

from app.auth.security import (
    create_access_token,
    decode_access_token,
    generate_otp_code,
    generate_verification_token,
    hash_otp_code,
    hash_password,
    verify_otp_code,
    verify_password,
)
from app.database import otp_repository as otp_repo
from app.database import user_repository as user_repo
from app.services.email_service import EmailNotAvailableError, send_otp_email

router = APIRouter()

# Min gap between two "send me a code" requests for the same
# (email, purpose) -- stops a Resend button spamming an inbox.
RESEND_COOLDOWN_SECONDS = 30


class AuthResponse(BaseModel):
    access_token: str
    email: str
    name: str | None = None


class CurrentUserResponse(BaseModel):
    id: str
    email: str
    name: str | None = None


class RequestCodeRequest(BaseModel):
    email: EmailStr


class VerifyCodeRequest(BaseModel):
    email: EmailStr
    code: str = Field(..., min_length=6, max_length=6)


class VerifyCodeResponse(BaseModel):
    verified_token: str


class CompleteSignupRequest(BaseModel):
    email: EmailStr
    verified_token: str
    password: str = Field(..., min_length=8)
    name: str = Field(..., min_length=1, max_length=120)


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    verified_token: str
    new_password: str = Field(..., min_length=8)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class MessageResponse(BaseModel):
    message: str


def _request_code(email: str, purpose: str) -> MessageResponse:
    seconds_since = otp_repo.seconds_since_last_code(email, purpose)
    if seconds_since is not None and seconds_since < RESEND_COOLDOWN_SECONDS:
        wait = int(RESEND_COOLDOWN_SECONDS - seconds_since) + 1
        raise HTTPException(status_code=429, detail=f"Please wait {wait}s before requesting another code.")

    code = generate_otp_code()
    otp_repo.create_code(email, hash_otp_code(code), purpose)
    try:
        send_otp_email(email, code, purpose)
    except EmailNotAvailableError as exc:
        # Don't leave a code in the DB that nobody received (it would
        # also trigger the resend cooldown for a code that never arrived).
        otp_repo.delete_codes_for(email, purpose)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return MessageResponse(message="A verification code has been sent to your email.")


def _verify_code(email: str, code: str, purpose: str) -> VerifyCodeResponse:
    record = otp_repo.get_pending_code(email, purpose)
    if not record:
        raise HTTPException(status_code=400, detail="No pending code found. Please request a new one.")
    if record.attempts >= otp_repo.MAX_ATTEMPTS:
        raise HTTPException(status_code=400, detail="Too many attempts. Please request a new code.")

    otp_repo.increment_attempts(record.id)
    if not verify_otp_code(code, record.code_hash):
        raise HTTPException(status_code=400, detail="Incorrect code. Please try again.")

    token = generate_verification_token()
    otp_repo.mark_verified(record.id, token)
    return VerifyCodeResponse(verified_token=token)


# ---------------- Signup: email -> code -> name + password ----------------

@router.post("/auth/signup/request-code", response_model=MessageResponse)
def signup_request_code(req: RequestCodeRequest):
    if user_repo.get_user_by_email(req.email):
        raise HTTPException(status_code=400, detail="An account with this email already exists.")
    return _request_code(req.email, "signup")


@router.post("/auth/signup/verify-code", response_model=VerifyCodeResponse)
def signup_verify_code(req: VerifyCodeRequest):
    return _verify_code(req.email, req.code, "signup")


@router.post("/auth/signup/complete", response_model=AuthResponse)
def signup_complete(req: CompleteSignupRequest):
    record = otp_repo.get_verified_code(req.email, "signup", req.verified_token)
    if not record:
        raise HTTPException(status_code=400, detail="Verification expired or invalid. Please start signup again.")
    if user_repo.get_user_by_email(req.email):
        raise HTTPException(status_code=400, detail="An account with this email already exists.")

    user = user_repo.create_user(req.email, hash_password(req.password), name=req.name)
    otp_repo.delete_codes_for(req.email, "signup")
    return AuthResponse(access_token=create_access_token(user.id, user.email), email=user.email, name=user.name)


# ---------------- Forgot password: email -> code -> new password ----------------

@router.post("/auth/forgot-password/request-code", response_model=MessageResponse)
def forgot_password_request_code(req: RequestCodeRequest):
    # Same generic reply whether or not the account exists, so this
    # can't be used to discover which emails are registered.
    if user_repo.get_user_by_email(req.email):
        return _request_code(req.email, "reset")
    return MessageResponse(message="If an account exists for this email, a code has been sent.")


@router.post("/auth/forgot-password/verify-code", response_model=VerifyCodeResponse)
def forgot_password_verify_code(req: VerifyCodeRequest):
    return _verify_code(req.email, req.code, "reset")


@router.post("/auth/forgot-password/reset", response_model=MessageResponse)
def forgot_password_reset(req: ResetPasswordRequest):
    record = otp_repo.get_verified_code(req.email, "reset", req.verified_token)
    if not record:
        raise HTTPException(status_code=400, detail="Verification expired or invalid. Please start again.")
    user = user_repo.get_user_by_email(req.email)
    if not user:
        raise HTTPException(status_code=400, detail="No account found for this email.")

    user_repo.update_password(user.id, hash_password(req.new_password))
    otp_repo.delete_codes_for(req.email, "reset")
    return MessageResponse(message="Your password has been reset. You can now log in.")


# ---------------- Login / session ----------------

@router.post("/auth/login", response_model=AuthResponse)
def login(req: LoginRequest):
    user_repo.ensure_auth_schema()
    user = user_repo.get_user_by_email(req.email)
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    return AuthResponse(access_token=create_access_token(user.id, user.email), email=user.email, name=user.name)


def get_current_user_id(authorization: str | None = Header(default=None)) -> str:
    """FastAPI dependency -- add `user_id: str = Depends(get_current_user_id)`
    to any route that should require login."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated.")
    payload = decode_access_token(authorization.removeprefix("Bearer ").strip())
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired session.")
    user_id = payload["sub"]
    # A token can be validly signed but reference a user that no longer
    # exists (deleted account, DB reset during dev). Return a clean 401
    # the frontend can react to, instead of a raw FK-violation 500.
    if user_repo.get_user_by_id(user_id) is None:
        raise HTTPException(status_code=401, detail="Session no longer valid. Please log in again.")
    return user_id


@router.get("/auth/me", response_model=CurrentUserResponse)
def get_me(authorization: str | None = Header(default=None)):
    """Restores {email, name} for the profile menu on page load from
    just the stored token."""
    user_id = get_current_user_id(authorization)
    user = user_repo.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Session no longer valid. Please log in again.")
    return CurrentUserResponse(id=user.id, email=user.email, name=user.name)
