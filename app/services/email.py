import httpx

from app.core.config import settings


RESEND_API_URL = "https://api.resend.com/emails"


def send_otp_email(to_email: str, otp: str, purpose_text: str) -> None:
    if not settings.RESEND_API_KEY:
        raise RuntimeError(
            "Resend is not configured. Add RESEND_API_KEY to .env"
        )

    if not settings.RESEND_FROM_EMAIL:
        raise RuntimeError(
            "Resend sender is not configured. Add RESEND_FROM_EMAIL to .env"
        )

    subject = f"AttendAI verification code - {purpose_text}"

    text = (
        f"Your AttendAI verification code is: {otp}\n\n"
        f"This code expires in {settings.OTP_EXPIRE_MINUTES} minutes.\n"
        "Do not share this code with anyone."
    )

    html = f"""
    <html>
      <body style="font-family: Arial, sans-serif;">
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
        "from": settings.RESEND_FROM_EMAIL,
        "to": [to_email],
        "subject": subject,
        "text": text,
        "html": html,
    }

    headers = {
        "Authorization": f"Bearer {settings.RESEND_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        response = httpx.post(
            RESEND_API_URL,
            headers=headers,
            json=payload,
            timeout=20.0,
        )

        if response.status_code >= 400:
            raise RuntimeError(
                f"Resend API error {response.status_code}: "
                f"{response.text}"
            )

    except httpx.RequestError as exc:
        raise RuntimeError(
            f"Unable to connect to Resend: {exc}"
        ) from exc
