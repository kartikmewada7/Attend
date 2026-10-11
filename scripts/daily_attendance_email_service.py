"""Standalone daily attendance summary mailer. Run via cron at 19:00 Asia/Kolkata.

From repository root:
    python -m scripts.daily_attendance_email_service

Uses the existing database models and Brevo email service. Does not modify API routes.
"""
import logging
from datetime import date, datetime, timezone
from html import escape
from zoneinfo import ZoneInfo

from sqlalchemy import inspect, select, text

from app.database import SessionLocal, engine
from app.models import Attendance, AttendanceSession, AttendanceEmailLog, Student, Subject
from app.services.email import send_email

IST = ZoneInfo("Asia/Kolkata")
logger = logging.getLogger("daily_attendance_email_service")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def _email_html(name: str, summary_date: date, rows: list[dict], recipient_is_parent: bool) -> tuple[str, str]:
    greeting = f"Parent/Guardian of {name}" if recipient_is_parent else name
    overall_present = sum(r["present"] for r in rows)
    overall_conducted = sum(r["conducted"] for r in rows)
    overall_pct = overall_present / overall_conducted * 100 if overall_conducted else 0
    body_rows = "".join(
        "<tr>"
        f"<td>{escape(r['subject'])}</td><td>{r['present']}</td>"
        f"<td>{r['conducted']}</td><td>{r['percentage']:.2f}%</td>"
        "</tr>"
        for r in rows
    )
    html = f"""<!doctype html><html><body style="font-family:Arial,sans-serif;line-height:1.5">
    <h2>AttendAI — Daily Attendance Summary</h2><p>Hello <b>{escape(greeting)}</b>,</p>
    <p>Attendance summary for <b>{summary_date.strftime('%d-%m-%Y')}</b>:</p>
    <table cellpadding="8" cellspacing="0" border="1" style="border-collapse:collapse;width:100%">
    <thead><tr><th>Subject</th><th>Present</th><th>Conducted</th><th>Attendance %</th></tr></thead>
    <tbody>{body_rows}</tbody></table>
    <p><b>Overall:</b> {overall_present}/{overall_conducted} ({overall_pct:.2f}%)</p>
    <p>Regards,<br>AttendAI</p></body></html>"""
    plain = (f"AttendAI Daily Attendance Summary\nHello {greeting}\n"
             f"Date: {summary_date.strftime('%d-%m-%Y')}\n" +
             "\n".join(f"{r['subject']}: {r['present']}/{r['conducted']} ({r['percentage']:.2f}%)" for r in rows) +
             f"\nOverall: {overall_present}/{overall_conducted} ({overall_pct:.2f}%)")
    return plain, html


def _get_parent_email(student_id: int, student_columns: set[str]) -> str | None:
    # This project ZIP's Student model does not define parent_email. If the deployed
    # database has a parent_email column, read it without requiring an ORM model change.
    if "parent_email" not in student_columns:
        return None
    with engine.connect() as conn:
        value = conn.execute(text("SELECT parent_email FROM students WHERE id = :id"), {"id": student_id}).scalar_one_or_none()
    return value.strip() if isinstance(value, str) and value.strip() else None


def _already_sent(db, student_id: int, email_type: str, run_date: date, email_address: str) -> bool:
    return db.scalar(select(AttendanceEmailLog.id).where(
        AttendanceEmailLog.student_id == student_id,
        AttendanceEmailLog.email_type == email_type,
        AttendanceEmailLog.reference_date == run_date,
        AttendanceEmailLog.email_address == email_address,
        AttendanceEmailLog.status == "SENT",
    ).limit(1)) is not None


def _send_one(db, student: Student, recipient: str, email_type: str, run_date: date, rows: list[dict], is_parent: bool) -> bool:
    if _already_sent(db, student.id, email_type, run_date, recipient):
        logger.info("Already sent; skipping student_id=%s type=%s recipient=%s", student.id, email_type, recipient)
        return False
    log = AttendanceEmailLog(
        student_id=student.id, attendance_id=None, email_type=email_type,
        reference_date=run_date, email_address=recipient, status="PENDING",
    )
    db.add(log)
    db.commit()
    try:
        plain, html = _email_html(student.name, run_date, rows, is_parent)
        send_email(
            to_email=recipient,
            subject=f"AttendAI Daily Attendance - {run_date.strftime('%d-%m-%Y')}",
            text_content=plain,
            html_content=html,
        )
        log.status = "SENT"
        log.sent_at = datetime.now(timezone.utc)
        log.error_message = None
        db.commit()
        logger.info("Mail accepted by Brevo: student_id=%s type=%s recipient=%s", student.id, email_type, recipient)
        return True
    except Exception as exc:
        db.rollback()
        log.status = "FAILED"
        log.error_message = str(exc)
        try:
            db.commit()
        except Exception:
            db.rollback()
        logger.error("Failed sending email: student_id=%s type=%s error=%s", student.id, email_type, exc)
        return False


def run_daily_summary(run_date: date | None = None) -> dict:
    if run_date is None:
        run_date = datetime.now(IST).date()

    db = SessionLocal()
    try:
        students = db.scalars(
            select(Student).where(Student.is_active.is_(True))
        ).all()

        attendance_rows = db.execute(
            select(Attendance, AttendanceSession, Subject, Student)
            .join(AttendanceSession, AttendanceSession.id == Attendance.session_id)
            .join(Subject, Subject.id == AttendanceSession.subject_id)
            .join(Student, Student.id == Attendance.student_id)
            .where(Student.is_active.is_(True))
        ).all()

        by_student = {}
        for attendance, session, subject, student in attendance_rows:
            marked = attendance.marked_at
            if marked.tzinfo is None:
                marked = marked.replace(tzinfo=timezone.utc)
            local_date = marked.astimezone(IST).date()
            if local_date > run_date:
                continue

            student_data = by_student.setdefault(student.id, {})
            subject_data = student_data.setdefault(subject.id, {
                "subject": subject.name,
                "sessions": set(),
                "present": 0,
            })
            subject_data["sessions"].add(session.id)
            if attendance.status.upper() == "PRESENT":
                subject_data["present"] += 1

        sent = 0
        skipped = 0
        failed = 0

        student_columns = {col.name for col in inspect(Student).columns}

        for student in students:
            data = by_student.get(student.id, {})
            if not data:
                skipped += 1
                continue

            rows = []
            for item in sorted(data.values(), key=lambda x: x["subject"].lower()):
                conducted = len(item["sessions"])
                present = item["present"]
                rows.append({
                    "subject": item["subject"],
                    "present": present,
                    "conducted": conducted,
                    "percentage": (present / conducted * 100) if conducted else 0,
                })

            student_email = (student.email or "").strip()
            parent_email = getattr(student, "parent_email", None) or _get_parent_email(student.id, student_columns)
            parent_email = parent_email.strip() if parent_email else None

            # Send to student
            if student_email:
                ok = _send_one(db, student, student_email, "DAILY_SUMMARY", run_date, rows, is_parent=False)
                if ok:
                    sent += 1
                elif _already_sent(db, student.id, "DAILY_SUMMARY", run_date, student_email):
                    skipped += 1
                else:
                    failed += 1

            # Send to parent
            if parent_email and parent_email.lower() != student_email.lower():
                ok_p = _send_one(db, student, parent_email, "DAILY_SUMMARY", run_date, rows, is_parent=True)
                if ok_p:
                    sent += 1
                elif _already_sent(db, student.id, "DAILY_SUMMARY", run_date, parent_email):
                    skipped += 1
                else:
                    failed += 1

        logger.info("Daily summary completed: date=%s sent=%s skipped=%s failed=%s", run_date, sent, skipped, failed)
        return {"date": run_date.isoformat(), "sent": sent, "skipped": skipped, "failed": failed}

    finally:
        db.close()


if __name__ == "__main__":
    run_daily_summary()