"""
Email service -- sends the OTP codes for signup verification and
forgot-password. Same provider pattern as tts_service.py /
voice_service.py (Rule 10): auth routes only call get_email_provider(),
never smtplib directly, so switching to Brevo/Resend/SES later means
adding one EmailProvider subclass.

Default is SMTP with a Gmail App Password: no new third-party account
needed (Google Account -> Security -> 2-Step Verification -> App
passwords). Gmail allows roughly 500 sends/day, plenty for dev/demo.
"""
from __future__ import annotations

import smtplib
import threading
from abc import ABC, abstractmethod
from email.message import EmailMessage

from app.config import get_settings


class EmailServiceError(Exception):
    """Base for errors this module raises."""


class EmailNotAvailableError(EmailServiceError):
    """Email can't be sent right now (bad credentials, no network...)."""


class EmailProvider(ABC):
    name: str = "base"

    @abstractmethod
    def send(self, to_email: str, subject: str, body_text: str) -> None: ...


class SMTPEmailProvider(EmailProvider):
    name = "smtp"

    def send(self, to_email: str, subject: str, body_text: str) -> None:
        settings = get_settings()
        if not settings.SMTP_USERNAME or not settings.SMTP_PASSWORD:
            raise EmailNotAvailableError(
                "Email is not configured. Set SMTP_USERNAME and SMTP_PASSWORD "
                "in backend/.env (a Gmail App Password works)."
            )
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
        msg["To"] = to_email
        msg.set_content(body_text)
        try:
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as server:
                server.starttls()
                server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
                server.send_message(msg)
        except Exception as exc:
            raise EmailNotAvailableError(f"Unable to send email: {exc}") from exc


_provider_lock = threading.Lock()
_provider_instance: EmailProvider | None = None


def get_email_provider() -> EmailProvider:
    global _provider_instance
    if _provider_instance is not None:
        return _provider_instance
    with _provider_lock:
        if _provider_instance is not None:
            return _provider_instance
        if get_settings().EMAIL_PROVIDER != "smtp":
            raise EmailNotAvailableError(
                f"Unknown EMAIL_PROVIDER '{get_settings().EMAIL_PROVIDER}'. Only 'smtp' is implemented."
            )
        _provider_instance = SMTPEmailProvider()
        return _provider_instance


def reset_email_provider_cache() -> None:
    global _provider_instance
    with _provider_lock:
        _provider_instance = None


def send_otp_email(to_email: str, code: str, purpose: str) -> None:
    """purpose: 'signup' | 'reset' -- only changes the wording."""
    app = get_settings().APP_NAME
    if purpose == "signup":
        subject = f"Verify your email - {app}"
        body = (
            f"Your {app} verification code is: {code}\n\n"
            "Enter this code to confirm your email and continue creating your account.\n"
            "This code expires in 10 minutes.\n\n"
            "If you didn't try to sign up, you can safely ignore this email."
        )
    else:
        subject = f"Reset your password - {app}"
        body = (
            f"Your {app} password reset code is: {code}\n\n"
            "Enter this code to reset your password.\n"
            "This code expires in 10 minutes.\n\n"
            "If you didn't request this, ignore this email - your password won't change."
        )
    get_email_provider().send(to_email, subject, body)
