import logging
import smtplib
from email.message import EmailMessage
import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"
RESEND_API_URL = "https://api.resend.com/emails"


def _send_via_brevo(to_email: str, subject: str, text_content: str, html_content: str) -> bool:
    """Attempt sending email via Brevo transactional API."""
    if not settings.BREVO_API_KEY:
        return False

    payload = {
        "sender": {
            "name": settings.BREVO_FROM_NAME or "AttendAI",
            "email": settings.BREVO_FROM_EMAIL or "kartikmewada168@gmail.com",
        },
        "to": [{"email": to_email}],
        "subject": subject,
        "textContent": text_content,
        "htmlContent": html_content,
    }
    headers = {
        "accept": "application/json",
        "api-key": settings.BREVO_API_KEY,
        "content-type": "application/json",
    }
    try:
        r = httpx.post(BREVO_API_URL, headers=headers, json=payload, timeout=15.0)
        if r.status_code in (200, 201, 202):
            logger.info("Email sent to %s via Brevo (status: %d)", to_email, r.status_code)
            return True
        logger.warning("Brevo returned status %d: %s", r.status_code, r.text)
    except Exception as exc:
        logger.warning("Brevo request failed: %s", exc)
    return False


def _send_via_resend(to_email: str, subject: str, text_content: str, html_content: str) -> bool:
    """Attempt sending email via Resend API."""
    if not settings.RESEND_API_KEY:
        return False

    payload = {
        "from": settings.RESEND_FROM_EMAIL or "AttendAI <onboarding@resend.dev>",
        "to": [to_email],
        "subject": subject,
        "text": text_content,
        "html": html_content,
    }
    headers = {
        "Authorization": f"Bearer {settings.RESEND_API_KEY}",
        "Content-Type": "application/json",
    }
    try:
        r = httpx.post(RESEND_API_URL, headers=headers, json=payload, timeout=15.0)
        if r.status_code in (200, 201):
            logger.info("Email sent to %s via Resend (id: %s)", to_email, r.json().get("id"))
            return True
        logger.warning("Resend returned status %d: %s", r.status_code, r.text)
    except Exception as exc:
        logger.warning("Resend request failed: %s", exc)
    return False


def _send_via_smtp(to_email: str, subject: str, text_content: str) -> bool:
    """Fallback: attempt sending via SMTP if configured and unblocked."""
    if not (settings.SMTP_HOST and settings.SMTP_USERNAME and settings.SMTP_PASSWORD and settings.SMTP_FROM_EMAIL):
        return False

    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
        msg["To"] = to_email
        msg.set_content(text_content)

        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
            if settings.SMTP_USE_TLS:
                server.starttls()
            server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            server.send_message(msg)
            logger.info("Email sent to %s via SMTP", to_email)
            return True
    except Exception as exc:
        logger.warning("SMTP delivery failed: %s", exc)
    return False


def send_otp_email(to_email: str, otp: str, purpose_text: str) -> None:
    """Send OTP email trying Brevo -> Resend -> SMTP in sequence."""
    subject = f"AttendAI verification code - {purpose_text}"
    text_content = (
        f"Your AttendAI verification code is: {otp}\n\n"
        f"This code expires in {settings.OTP_EXPIRE_MINUTES} minutes.\n"
        "Do not share this code with anyone."
    )
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #2d3748;">
        <h2>AttendAI Verification Code</h2>
        <p>Your verification code is:</p>
        <div style="font-size: 32px; font-weight: bold; letter-spacing: 8px; margin: 20px 0; color: #1a365d;">
            {otp}
        </div>
        <p>This code expires in <strong>{settings.OTP_EXPIRE_MINUTES} minutes</strong>.</p>
        <p>Do not share this code with anyone.</p>
        <hr style="border: 0; border-top: 1px solid #e2e8f0; margin: 20px 0;">
        <p style="color: #718096; font-size: 14px;">AttendAI Attendance Management System</p>
    </body>
    </html>
    """

    # Try Brevo first
    if _send_via_brevo(to_email, subject, text_content, html_content):
        return

    # Try Resend second
    if _send_via_resend(to_email, subject, text_content, html_content):
        return

    # Try SMTP third
    if _send_via_smtp(to_email, subject, text_content):
        return

    # If all failed, raise informative error
    raise RuntimeError(
        "Could not deliver OTP email. Please ensure Brevo API key is active without IP restrictions, "
        "or Resend domain is verified."
    )
