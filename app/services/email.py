import httpx

from app.core.config import settings


BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"


def send_otp_email(to_email: str, otp: str, purpose_text: str) -> None:
    if not settings.BREVO_API_KEY:
        raise RuntimeError("BREVO_API_KEY is not configured")

    if not settings.BREVO_FROM_EMAIL:
        raise RuntimeError("BREVO_FROM_EMAIL is not configured")

    subject = f"AttendAI verification code - {purpose_text}"

    text_content = (
        f"Your AttendAI verification code is: {otp}\n\n"
        f"This code expires in {settings.OTP_EXPIRE_MINUTES} minutes.\n"
        "Do not share this code with anyone."
    )

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6;">

        <h2>AttendAI Verification Code</h2>

        <p>Your verification code is:</p>

        <div style="
            font-size: 32px;
            font-weight: bold;
            letter-spacing: 8px;
            margin: 20px 0;
        ">
            {otp}
        </div>

        <p>
            This code expires in
            <strong>{settings.OTP_EXPIRE_MINUTES} minutes</strong>.
        </p>

        <p>Do not share this code with anyone.</p>

        <hr>

        <p style="color: #666;">
            AttendAI Attendance Management System
        </p>

    </body>
    </html>
    """

    payload = {
        "sender": {
            "name": settings.BREVO_FROM_NAME,
            "email": settings.BREVO_FROM_EMAIL,
        },
        "to": [
            {
                "email": to_email,
            }
        ],
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
        response = httpx.post(
            BREVO_API_URL,
            headers=headers,
            json=payload,
            timeout=20.0,
        )

        if response.status_code >= 400:
            raise RuntimeError(
                f"Brevo API error {response.status_code}: {response.text}"
            )

    except httpx.RequestError as exc:
        raise RuntimeError(
            f"Unable to connect to Brevo: {exc}"
        ) from exc
