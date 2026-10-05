import logging
import smtplib
from email.message import EmailMessage

from app.core.config import settings

logger = logging.getLogger(__name__)


def _send_via_smtp(
    to_email: str,
    subject: str,
    text_content: str,
    html_content: str,
) -> bool:
    """Send email through configured SMTP server."""

    if not (
        settings.SMTP_HOST
        and settings.SMTP_USERNAME
        and settings.SMTP_PASSWORD
        and settings.SMTP_FROM_EMAIL
    ):
        logger.error("SMTP configuration is incomplete.")
        return False

    try:
        msg = EmailMessage()

        msg["Subject"] = subject
        msg["From"] = (
            f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
        )
        msg["To"] = to_email

        # Plain-text version
        msg.set_content(text_content)

        # HTML version
        msg.add_alternative(html_content, subtype="html")

        # Port 465 = implicit SSL
        if int(settings.SMTP_PORT) == 465:
            with smtplib.SMTP_SSL(
                settings.SMTP_HOST,
                int(settings.SMTP_PORT),
                timeout=20,
            ) as server:
                server.login(
                    settings.SMTP_USERNAME,
                    settings.SMTP_PASSWORD,
                )
                server.send_message(msg)

        # Port 587 / 25 = normal SMTP
        else:
            with smtplib.SMTP(
                settings.SMTP_HOST,
                int(settings.SMTP_PORT),
                timeout=20,
            ) as server:

                server.ehlo()

                if settings.SMTP_USE_TLS:
                    server.starttls()
                    server.ehlo()

                server.login(
                    settings.SMTP_USERNAME,
                    settings.SMTP_PASSWORD,
                )

                server.send_message(msg)

        logger.info(
            "OTP email sent successfully via SMTP to %s",
            to_email,
        )

        return True

    except smtplib.SMTPAuthenticationError as exc:
        logger.error(
            "SMTP authentication failed: %s",
            exc,
        )
        return False

    except smtplib.SMTPConnectError as exc:
        logger.error(
            "Could not connect to SMTP server: %s",
            exc,
        )
        return False

    except smtplib.SMTPException as exc:
        logger.error(
            "SMTP error while sending email: %s",
            exc,
        )
        return False

    except Exception as exc:
        logger.exception(
            "Unexpected SMTP email error: %s",
            exc,
        )
        return False


def send_otp_email(
    to_email: str,
    otp: str,
    purpose_text: str,
) -> None:
    """Send AttendAI OTP email using SMTP."""

    subject = f"AttendAI verification code - {purpose_text}"

    text_content = (
        f"Your AttendAI verification code is: {otp}\n\n"
        f"This code expires in "
        f"{settings.OTP_EXPIRE_MINUTES} minutes.\n"
        "Do not share this code with anyone.\n\n"
        "AttendAI Attendance Management System"
    )

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>AttendAI Verification Code</title>
    </head>

    <body
        style="
            margin: 0;
            padding: 0;
            background: #f4f7fb;
            font-family: Arial, sans-serif;
        "
    >
        <div
            style="
                max-width: 560px;
                margin: 40px auto;
                background: #ffffff;
                border-radius: 12px;
                padding: 32px;
                box-shadow: 0 4px 18px rgba(0,0,0,0.08);
            "
        >
            <h2
                style="
                    margin-top: 0;
                    color: #1a365d;
                "
            >
                AttendAI Verification Code
            </h2>

            <p style="color: #4a5568;">
                Your verification code is:
            </p>

            <div
                style="
                    margin: 24px 0;
                    padding: 18px;
                    text-align: center;
                    background: #edf2f7;
                    border-radius: 8px;
                    font-size: 32px;
                    font-weight: bold;
                    letter-spacing: 8px;
                    color: #1a365d;
                "
            >
                {otp}
            </div>

            <p style="color: #4a5568;">
                This code expires in
                <strong>
                    {settings.OTP_EXPIRE_MINUTES} minutes
                </strong>.
            </p>

            <p style="color: #4a5568;">
                Do not share this code with anyone.
            </p>

            <hr
                style="
                    border: 0;
                    border-top: 1px solid #e2e8f0;
                    margin: 24px 0;
                "
            >

            <p
                style="
                    color: #718096;
                    font-size: 13px;
                "
            >
                AttendAI Attendance Management System
            </p>
        </div>
    </body>
    </html>
    """

    if _send_via_smtp(
        to_email,
        subject,
        text_content,
        html_content,
    ):
        return

    raise RuntimeError(
        "Could not deliver OTP email through SMTP. "
        "Please check SMTP_HOST, SMTP_PORT, SMTP_USERNAME, "
        "SMTP_PASSWORD and SMTP_FROM_EMAIL."
    )
