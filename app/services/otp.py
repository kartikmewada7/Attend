import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password, verify_password
from app.models import Teacher, TeacherOTP
from app.services.email import send_otp_email


def normalize_email(email: str) -> str:
    return email.strip().lower()


def _teacher(db: Session, email: str):
    return db.scalar(select(Teacher).where(Teacher.email == normalize_email(email)))


def issue_otp(db: Session, email: str, purpose: str, purpose_text: str) -> None:
    email = normalize_email(email)
    teacher = _teacher(db, email)
    if not teacher:
        raise ValueError("Teacher account not found")

    now = datetime.now(timezone.utc)
    recent = db.scalar(
        select(TeacherOTP)
        .where(
            TeacherOTP.teacher_id == teacher.id,
            TeacherOTP.purpose == purpose,
            TeacherOTP.created_at >= now - timedelta(seconds=settings.OTP_RESEND_SECONDS),
            TeacherOTP.verified_at.is_(None),
        )
        .order_by(TeacherOTP.created_at.desc())
    )
    if recent:
        wait = settings.OTP_RESEND_SECONDS - int((now - recent.created_at).total_seconds())
        raise ValueError(f"Please wait {max(wait, 1)} seconds before requesting another OTP")

    otp = f"{secrets.randbelow(1_000_000):06d}"
    row = TeacherOTP(
        teacher_id=teacher.id,
        otp_hash=hash_password(otp),
        purpose=purpose,
        expires_at=now + timedelta(minutes=settings.OTP_EXPIRE_MINUTES),
    )
    db.add(row)
    db.commit()

    try:
        send_otp_email(email, otp, purpose_text)
    except Exception:
        db.delete(row)
        db.commit()
        raise


def verify_otp(db: Session, email: str, purpose: str, otp: str) -> bool:
    teacher = _teacher(db, email)
    if not teacher:
        return False

    now = datetime.now(timezone.utc)
    row = db.scalar(
        select(TeacherOTP)
        .where(
            TeacherOTP.teacher_id == teacher.id,
            TeacherOTP.purpose == purpose,
            TeacherOTP.verified_at.is_(None),
        )
        .order_by(TeacherOTP.created_at.desc())
    )
    if not row or row.expires_at <= now:
        return False

    entered = str(otp).strip()
    if len(entered) != 6 or not entered.isdigit():
        return False
    if not verify_password(entered, row.otp_hash):
        return False

    row.verified_at = now
    db.commit()
    return True
