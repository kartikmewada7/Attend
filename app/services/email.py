import logging
from datetime import date, datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

import httpx

IST = ZoneInfo("Asia/Kolkata")

from app.core.config import settings

logger = logging.getLogger(__name__)

BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"


def send_email(
    to_email: str,
    subject: str,
    text_content: str,
    html_content: str,
) -> None:
    if not settings.BREVO_API_KEY:
        raise RuntimeError("BREVO_API_KEY is not configured")

    if not settings.BREVO_FROM_EMAIL:
        raise RuntimeError("BREVO_FROM_EMAIL is not configured")

    payload = {
        "sender": {
            "name": settings.BREVO_FROM_NAME or "AttendAI",
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
            logger.error(
                "Brevo API error %s: %s",
                response.status_code,
                response.text,
            )
            raise RuntimeError(
                f"Brevo API error {response.status_code}: "
                f"{response.text}"
            )

        logger.info(
            "Email sent successfully to %s via Brevo",
            to_email,
        )

    except httpx.RequestError as exc:
        logger.exception("Brevo connection failed")
        raise RuntimeError(
            f"Unable to connect to Brevo: {exc}"
        ) from exc


def send_otp_email(
    to_email: str,
    otp: str,
    purpose_text: str,
) -> None:
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

    send_email(
        to_email=to_email,
        subject=subject,
        text_content=text_content,
        html_content=html_content,
    )


def send_attendance_email(
    to_email: str,
    student_name: str,
    subject_name: str,
    attendance_date: Any,
    attendance_time: Any,
    status: str,
) -> None:
    if isinstance(attendance_time, datetime):
        if attendance_time.tzinfo is None:
            attendance_time = attendance_time.replace(tzinfo=timezone.utc)
        attendance_time = attendance_time.astimezone(IST).strftime("%I:%M %p")

    if isinstance(attendance_date, datetime):
        if attendance_date.tzinfo is None:
            attendance_date = attendance_date.replace(tzinfo=timezone.utc)
        attendance_date = attendance_date.astimezone(IST).strftime("%d-%m-%Y")
    elif isinstance(attendance_date, date):
        attendance_date = attendance_date.strftime("%d-%m-%Y")

    status_text = status.upper()

    subject = (
        f"AttendAI Attendance - {subject_name} - "
        f"{status_text}"
    )

    text_content = f"""
Hello {student_name},

Your attendance has been recorded.

Subject: {subject_name}
Date: {attendance_date}
Time: {attendance_time}
Status: {status_text}

Regards,
AttendAI Attendance Management System
""".strip()

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6;">
        <h2>AttendAI Attendance Confirmation</h2>

        <p>Hello <strong>{student_name}</strong>,</p>

        <p>Your attendance has been recorded.</p>

        <table cellpadding="8" cellspacing="0" border="1"
               style="border-collapse: collapse;">
            <tr>
                <td><strong>Subject</strong></td>
                <td>{subject_name}</td>
            </tr>
            <tr>
                <td><strong>Date</strong></td>
                <td>{attendance_date}</td>
            </tr>
            <tr>
                <td><strong>Time</strong></td>
                <td>{attendance_time}</td>
            </tr>
            <tr>
                <td><strong>Status</strong></td>
                <td>{status_text}</td>
            </tr>
        </table>

        <br>

        <p style="color: #666;">
            AttendAI Attendance Management System
        </p>
    </body>
    </html>
    """

    send_email(
        to_email=to_email,
        subject=subject,
        text_content=text_content,
        html_content=html_content,
    )