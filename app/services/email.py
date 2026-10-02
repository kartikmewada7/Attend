import smtplib
from email.message import EmailMessage
from app.core.config import settings

def send_otp_email(to_email: str, otp: str, purpose_text: str) -> None:
    if not settings.SMTP_HOST or not settings.SMTP_USERNAME or not settings.SMTP_PASSWORD or not settings.SMTP_FROM_EMAIL:
        raise RuntimeError("SMTP is not configured. Add SMTP_HOST, SMTP_USERNAME, SMTP_PASSWORD and SMTP_FROM_EMAIL to .env")
    msg = EmailMessage()
    msg["Subject"] = f"AttendAI verification code - {purpose_text}"
    msg["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
    msg["To"] = to_email
    msg.set_content(
        f"Your AttendAI verification code is: {otp}\n\n"
        f"This code expires in {settings.OTP_EXPIRE_MINUTES} minutes.\n"
        "Do not share this code with anyone."
    )
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as server:
        if settings.SMTP_USE_TLS:
            server.starttls()
        server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        server.send_message(msg)
