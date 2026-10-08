from datetime import date, datetime
import json
import os
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Header

from pydantic import BaseModel

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from sqlalchemy.orm import Session

from app.cache import cache

from app.database import get_db

from app.deps import require_role

from app.models import (

    Subject,

    Student,

    Department,

    Semester,

    Section,

    SemesterSubject,

    TeacherSubjectSection,

    AttendanceSession,

    Attendance,

    StudentFaceEmbedding,

    AttendanceEmailLog,

)

from app.services.academic import (

    get_or_create_department,

    get_semester,

    get_section,

)

from app.services.email import send_attendance_email

router = APIRouter(prefix="/api/attendance", tags=["Attendance"])

class MarkAttendance(BaseModel):

    student_id: int

    subject_id: int

    attendance_date: date

    status: str = "present"

    section_id: int | None = None

class BulkAttendance(BaseModel):

    subject_id: int

    attendance_date: date

    records: list[dict]

    section_id: int | None = None

def teacher_subjects(db, teacher_id):

    return db.execute(

        select(Subject, Section, Semester, Department)

        .join(

            TeacherSubjectSection,

            TeacherSubjectSection.subject_id == Subject.id,

        )

        .join(

            Section,

            Section.id == TeacherSubjectSection.section_id,

        )

        .join(

            Semester,

            Semester.id == Section.semester_id,

        )

        .join(

            Department,

            Department.id == Section.department_id,

        )

        .where(

            TeacherSubjectSection.teacher_id == teacher_id

        )

        .order_by(

            Subject.name,

            Section.section_code,

        )

    ).all()

def ensure_session(

    db,

    teacher_id,

    subject_id,

    section_id,

    attendance_date,

):

    start = datetime.combine(

        attendance_date,

        datetime.min.time(),

    )

    end = datetime.combine(

        attendance_date,

        datetime.max.time(),

    )

    s = db.scalar(

        select(AttendanceSession)

        .where(

            AttendanceSession.teacher_id == teacher_id,

            AttendanceSession.subject_id == subject_id,

            AttendanceSession.section_id == section_id,

            AttendanceSession.started_at >= start,

            AttendanceSession.started_at <= end,

        )

        .order_by(AttendanceSession.id.desc())

    )

    if not s:

        s = AttendanceSession(

            teacher_id=teacher_id,

            subject_id=subject_id,

            section_id=section_id,

            status="CLOSED",

            started_at=datetime.utcnow(),

            ended_at=datetime.utcnow(),

        )

        db.add(s)

        db.flush()

    return s

def authorized(db, teacher_id, subject_id, section_id):

    return (

        db.scalar(

            select(TeacherSubjectSection).where(

                TeacherSubjectSection.teacher_id == teacher_id,

                TeacherSubjectSection.subject_id == subject_id,

                TeacherSubjectSection.section_id == section_id,

            )

        )

        is not None

    )

def send_attendance_confirmation(

    db,

    attendance,

    student,

    subject,

):

    """

    Send one attendance confirmation email and record

    the result in attendance_email_logs.

    If the student has no email, nothing is sent.

    If the same attendance already has a SENT log,

    the email is not sent again.

    """

    if not student.email:

        return

    # Reuse an existing log for this attendance record. This prevents a
    # duplicate-key error if a previous attempt created a PENDING/FAILED log.
    existing_log = db.scalar(
        select(AttendanceEmailLog).where(
            AttendanceEmailLog.attendance_id == attendance.id,
            AttendanceEmailLog.email_type == "ATTENDANCE",
        )
    )

    if existing_log:
        if existing_log.status == "SENT":
            return
        log = existing_log
        log.email_address = student.email
        log.status = "PENDING"
        log.error_message = None
    else:
        log = AttendanceEmailLog(
            student_id=student.id,
            attendance_id=attendance.id,
            email_type="ATTENDANCE",
            reference_date=attendance.marked_at.date(),
            email_address=student.email,
            status="PENDING",
        )
        db.add(log)

    db.flush()

    try:

        send_attendance_email(

            to_email=student.email,

            student_name=student.name,

            subject_name=subject.name,

            attendance_date=attendance.marked_at.strftime(

                "%d-%m-%Y"

            ),

            attendance_time=attendance.marked_at.strftime(

                "%I:%M %p"

            ),

            status=attendance.status,

        )

        log.status = "SENT"

        log.sent_at = datetime.utcnow()

        log.error_message = None

    except Exception as exc:

        log.status = "FAILED"

        log.error_message = str(exc)

        # Attendance should still be saved even if email fails.

        # Do not raise the email error here.

@router.get("/subjects")

def list_subjects(

    user=Depends(require_role("teacher")),

    db: Session = Depends(get_db),

):

    cache_key = f"teacher_subjects:{user['id']}"

    cached_data = cache.get(cache_key)

    if cached_data is not None:

        return cached_data

    rows = teacher_subjects(db, user["id"])

    result = [

        {

            "id": s.id,

            "name": s.name,

            "code": s.code,

            "department": d.name,

            "year": (sem.semester_number + 1) // 2,

            "semester": sem.semester_number,

            "section": sec.section_code,

            "section_id": sec.id,

        }

        for s, sec, sem, d in rows

    ]

    cache.set(

        cache_key,

        result,

        ttl=180,

    )

    return result

@router.post("/subjects")

def create_subject(

    name: str,

    code: str,

    department: str = "CSE",

    year: int | None = None,

    semester: int = 1,

    section: str | None = None,

    user=Depends(require_role("teacher")),

    db: Session = Depends(get_db),

):

    name, code = name.strip(), code.strip().upper()

    if db.scalar(

        select(Subject).where(Subject.code == code)

    ):

        raise HTTPException(

            409,

            "Subject code already exists",

        )

    dep = get_or_create_department(

        db,

        department,

    )

    sem = get_semester(

        db,

        semester,

    )

    s = Subject(

        name=name,

        code=code,

    )

    db.add(s)

    db.flush()

    db.add(

        SemesterSubject(

            semester_id=sem.id,

            subject_id=s.id,

        )

    )

    db.flush()

    sections = db.scalars(

        select(Section).where(

            Section.department_id == dep.id,

            Section.semester_id == sem.id,

        )

    ).all()

    if section:

        sections = [

            get_section(

                db,

                dep.id,

                sem.id,

                section,

            )

        ]

    if not sections:

        sections = [

            get_section(

                db,

                dep.id,

                sem.id,

                section or "S1",

            )

        ]

    for sec in sections:

        exists = db.scalar(

            select(TeacherSubjectSection).where(

                TeacherSubjectSection.teacher_id == user["id"],

                TeacherSubjectSection.subject_id == s.id,

                TeacherSubjectSection.section_id == sec.id,

            )

        )

        if not exists:

            db.add(

                TeacherSubjectSection(

                    teacher_id=user["id"],

                    subject_id=s.id,

                    section_id=sec.id,

                )

            )

    db.commit()

    cache.delete_pattern(

        "teacher_subjects:*"

    )

    cache.delete_pattern(

        "student_subjects:*"

    )

    return {

        "id": s.id,

        "name": s.name,

        "code": s.code,

        "semester": sem.semester_number,

        "department": dep.name,

    }

@router.get("/students")

def subject_students(

    subject_id: int,

    section_id: int | None = None,

    user=Depends(require_role("teacher")),

    db: Session = Depends(get_db),

):

    if section_id is None:

        section_id = db.scalar(

            select(

                TeacherSubjectSection.section_id

            ).where(

                TeacherSubjectSection.teacher_id == user["id"],

                TeacherSubjectSection.subject_id == subject_id,

            )

        )

    if not section_id or not authorized(

        db,

        user["id"],

        subject_id,

        section_id,

    ):

        raise HTTPException(

            403,

            "Subject/section not assigned to teacher",

        )

    cache_key = f"section_students:{section_id}"

    cached_data = cache.get(cache_key)

    if cached_data is not None:

        return cached_data

    rows = db.scalars(

        select(Student)

        .where(

            Student.current_section_id == section_id,

            Student.is_active.is_(True),

        )

        .order_by(Student.name)

    ).all()

    face_ids = set(

        db.scalars(

            select(

                StudentFaceEmbedding.student_id

            ).where(

                StudentFaceEmbedding.is_active.is_(True)

            )

        ).all()

    )

    result = [

        {

            "id": s.id,

            "name": s.name,

            "roll_number": s.enrollment_no,

            "enrollment_no": s.enrollment_no,

            "face_registered": s.id in face_ids,

        }

        for s in rows

    ]

    cache.set(

        cache_key,

        result,

        ttl=120,

    )

    return result

@router.get("/records")

def get_records(

    subject_id: int,

    attendance_date: date,

    section_id: int | None = None,

    user=Depends(require_role("teacher")),

    db: Session = Depends(get_db),

):

    if section_id is None:

        section_id = db.scalar(

            select(

                TeacherSubjectSection.section_id

            ).where(

                TeacherSubjectSection.teacher_id == user["id"],

                TeacherSubjectSection.subject_id == subject_id,

            )

        )

    if not section_id or not authorized(

        db,

        user["id"],

        subject_id,

        section_id,

    ):

        raise HTTPException(

            403,

            "Subject/section not assigned",

        )

    s = ensure_session(

        db,

        user["id"],

        subject_id,

        section_id,

        attendance_date,

    )

    db.commit()

    rows = db.scalars(

        select(Attendance)

        .where(

            Attendance.session_id == s.id

        )

    ).all()

    return [

        {

            "student_id": r.student_id,

            "status": r.status.lower(),

        }

        for r in rows

    ]

@router.post("/mark")

def mark(

    payload: MarkAttendance,

    user=Depends(require_role("teacher")),

    db: Session = Depends(get_db),

):

    if payload.status not in {

        "present",

        "absent",

    }:

        raise HTTPException(

            400,

            "Invalid attendance status",

        )

    section_id = (

        payload.section_id

        or db.scalar(

            select(

                TeacherSubjectSection.section_id

            ).where(

                TeacherSubjectSection.teacher_id == user["id"],

                TeacherSubjectSection.subject_id == payload.subject_id,

            )

        )

    )

    if not section_id or not authorized(

        db,

        user["id"],

        payload.subject_id,

        section_id,

    ):

        raise HTTPException(

            403,

            "Subject/section not assigned",

        )

    student = db.get(

        Student,

        payload.student_id,

    )

    if (

        not student

        or student.current_section_id != section_id

    ):

        raise HTTPException(

            404,

            "Student not found in selected section",

        )

    subject = db.get(

        Subject,

        payload.subject_id,

    )

    if not subject:

        raise HTTPException(

            404,

            "Subject not found",

        )

    sess = ensure_session(

        db,

        user["id"],

        payload.subject_id,

        section_id,

        payload.attendance_date,

    )

    row = db.scalar(

        select(Attendance).where(

            Attendance.session_id == sess.id,

            Attendance.student_id == student.id,

        )

    )

    if row:

        row.status = payload.status.upper()

        row.source = "MANUAL"

        row.marked_at = datetime.utcnow()

        attendance_record = row

    else:

        attendance_record = Attendance(

            session_id=sess.id,

            student_id=student.id,

            status=payload.status.upper(),

            source="MANUAL",

        )

        db.add(attendance_record)

        db.flush()

    send_attendance_confirmation(

        db=db,

        attendance=attendance_record,

        student=student,

        subject=subject,

    )

    db.commit()

    cache.delete_pattern(

        f"student_attendance:{student.id}"

    )

    cache.delete_pattern(

        "attendance_history:*"

    )

    return {

        "message": "Attendance saved"

    }

@router.post("/bulk")

def bulk_mark(

    payload: BulkAttendance,

    user=Depends(require_role("teacher")),

    db: Session = Depends(get_db),

):

    section_id = (

        payload.section_id

        or db.scalar(

            select(

                TeacherSubjectSection.section_id

            ).where(

                TeacherSubjectSection.teacher_id == user["id"],

                TeacherSubjectSection.subject_id == payload.subject_id,

            )

        )

    )

    if not section_id or not authorized(

        db,

        user["id"],

        payload.subject_id,

        section_id,

    ):

        raise HTTPException(

            403,

            "Subject/section not assigned",

        )

    subject = db.get(

        Subject,

        payload.subject_id,

    )

    if not subject:

        raise HTTPException(

            404,

            "Subject not found",

        )

    sess = ensure_session(

        db,

        user["id"],

        payload.subject_id,

        section_id,

        payload.attendance_date,

    )

    count = 0

    email_results = []

    for item in payload.records:

        sid = int(

            item.get("student_id")

        )

        status = str(

            item.get(

                "status",

                "absent",

            )

        ).lower()

        if status not in {

            "present",

            "absent",

        }:

            raise HTTPException(

                400,

                "Invalid attendance status",

            )

        student = db.get(

            Student,

            sid,

        )

        if (

            not student

            or student.current_section_id != section_id

        ):

            continue

        row = db.scalar(

            select(Attendance).where(

                Attendance.session_id == sess.id,

                Attendance.student_id == sid,

            )

        )

        if row:

            row.status = status.upper()

            row.source = "MANUAL"

            row.marked_at = datetime.utcnow()

            attendance_record = row

        else:

            attendance_record = Attendance(

                session_id=sess.id,

                student_id=sid,

                status=status.upper(),

                source="MANUAL",

            )

            db.add(attendance_record)

            db.flush()

        if student.email:

            try:

                send_attendance_confirmation(

                    db=db,

                    attendance=attendance_record,

                    student=student,

                    subject=subject,

                )

                email_results.append(

                    {

                        "student_id": student.id,

                        "status": "processed",

                    }

                )

            except Exception as exc:

                email_results.append(

                    {

                        "student_id": student.id,

                        "status": "failed",

                        "error": str(exc),

                    }

                )

        else:

            email_results.append(

                {

                    "student_id": student.id,

                    "status": "no_email",

                }

            )

        count += 1

    db.commit()

    cache.delete_pattern(

        "student_attendance:*"

    )

    cache.delete_pattern(

        "attendance_history:*"

    )

    return {

        "message": "Attendance saved",

        "count": count,

        "emails": email_results,

    }

@router.get("/history")

def history(

    user=Depends(require_role("teacher")),

    db: Session = Depends(get_db),

):

    cache_key = f"attendance_history:{user['id']}"

    cached_data = cache.get(cache_key)

    if cached_data is not None:

        return cached_data

    rows = db.execute(

        select(

            Attendance.id,

            AttendanceSession.started_at,

            Attendance.marked_at,

            Attendance.status,

            Student.name,

            Student.enrollment_no,

            Subject.name.label("subject"),

            Subject.code,

        )

        .join(

            AttendanceSession,

            AttendanceSession.id == Attendance.session_id,

        )

        .join(

            Student,

            Student.id == Attendance.student_id,

        )

        .join(

            Subject,

            Subject.id == AttendanceSession.subject_id,

        )

        .where(

            AttendanceSession.teacher_id == user["id"]

        )

        .order_by(

            AttendanceSession.started_at.desc(),

            Subject.name,

            Student.name,

        )

    ).all()

    result = [

        {

            "id": r.id,

            "date": r.started_at.date(),

            "marked_at": r.marked_at,

            "status": r.status.lower(),

            "student_name": r.name,

            "roll_number": r.enrollment_no,

            "subject": r.subject,

            "code": r.code,

        }

        for r in rows

    ]

    cache.set(

        cache_key,

        result,

        ttl=60,

    )

    return result


# -----------------------------------------------------------------------------
# End-of-day attendance summary
# Render Cron should call this endpoint once every day (for example 7:00 PM IST).
# Set CRON_SECRET in Render and send it as X-Cron-Secret.
# -----------------------------------------------------------------------------

def _send_daily_summary_email(
    to_email: str,
    student_name: str,
    summary_date: str,
    subject_rows: list[dict],
    overall_present: int,
    overall_conducted: int,
) -> None:
    api_key = os.getenv("BREVO_API_KEY")
    from_email = os.getenv("BREVO_FROM_EMAIL")
    from_name = os.getenv("BREVO_FROM_NAME", "AttendAI")

    if not api_key or not from_email:
        raise RuntimeError("BREVO_API_KEY or BREVO_FROM_EMAIL is not configured")

    overall_pct = (
        (overall_present / overall_conducted) * 100
        if overall_conducted
        else 0
    )

    rows_html = "".join(
        f"""
        <tr>
          <td style='padding:8px;border:1px solid #ddd'>{r['subject']}</td>
          <td style='padding:8px;border:1px solid #ddd;text-align:center'>{r['present']}</td>
          <td style='padding:8px;border:1px solid #ddd;text-align:center'>{r['conducted']}</td>
          <td style='padding:8px;border:1px solid #ddd;text-align:center'>{r['percentage']:.2f}%</td>
        </tr>
        """
        for r in subject_rows
    )

    html = f"""
    <div style='font-family:Arial,sans-serif;max-width:700px;margin:auto'>
      <h2>AttendAI - Daily Attendance Summary</h2>
      <p>Hello <b>{student_name}</b>,</p>
      <p>Your attendance summary for <b>{summary_date}</b> is below.</p>
      <table style='border-collapse:collapse;width:100%'>
        <thead>
          <tr>
            <th style='padding:8px;border:1px solid #ddd;text-align:left'>Subject</th>
            <th style='padding:8px;border:1px solid #ddd'>Present</th>
            <th style='padding:8px;border:1px solid #ddd'>Conducted</th>
            <th style='padding:8px;border:1px solid #ddd'>Attendance %</th>
          </tr>
        </thead>
        <tbody>{rows_html}</tbody>
      </table>
      <p style='margin-top:18px'>
        <b>Overall Attendance:</b> {overall_present}/{overall_conducted}
        ({overall_pct:.2f}%)
      </p>
      <p>Regards,<br>AttendAI</p>
    </div>
    """

    payload = {
        "sender": {"name": from_name, "email": from_email},
        "to": [{"email": to_email, "name": student_name}],
        "subject": f"AttendAI Daily Attendance - {summary_date}",
        "htmlContent": html,
    }

    req = Request(
        "https://api.brevo.com/v3/smtp/email",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "accept": "application/json",
            "api-key": api_key,
            "content-type": "application/json",
        },
        method="POST",
    )
    with urlopen(req, timeout=20) as response:
        if response.status >= 400:
            raise RuntimeError(f"Brevo returned HTTP {response.status}")


def _send_daily_summaries_for_date(db: Session, summary_date: date) -> dict:
    """Send one summary email per student for the requested IST date."""
    ist = ZoneInfo("Asia/Kolkata")

    students = db.scalars(
        select(Student).where(
            Student.is_active.is_(True),
            Student.email.is_not(None),
        )
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
            marked = marked.replace(tzinfo=ZoneInfo("UTC"))
        local_date = marked.astimezone(ist).date()
        if local_date > summary_date:
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

    for student in students:
        # Do not send empty summaries to students who had no attendance records.
        data = by_student.get(student.id, {})
        if not data:
            skipped += 1
            continue

        # Prevent duplicate daily summary emails.
        # Use PostgreSQL ON CONFLICT DO NOTHING so a retry/concurrent cron
        # execution can never crash the whole endpoint with UniqueViolation.
        existing = db.scalar(
            select(AttendanceEmailLog).where(
                AttendanceEmailLog.student_id == student.id,
                AttendanceEmailLog.email_type == "DAILY_SUMMARY",
                AttendanceEmailLog.reference_date == summary_date,
            )
        )

        if existing and existing.status == "SENT":
            skipped += 1
            continue

        rows = []
        overall_present = 0
        overall_conducted = 0
        for item in sorted(data.values(), key=lambda x: x["subject"].lower()):
            conducted = len(item["sessions"])
            present = item["present"]
            rows.append({
                "subject": item["subject"],
                "present": present,
                "conducted": conducted,
                "percentage": (present / conducted * 100) if conducted else 0,
            })
            overall_present += present
            overall_conducted += conducted

        if existing:
            log = existing
            log.email_address = student.email
            log.status = "PENDING"
            log.error_message = None
        else:
            stmt = (
                pg_insert(AttendanceEmailLog)
                .values(
                    student_id=student.id,
                    attendance_id=None,
                    email_type="DAILY_SUMMARY",
                    reference_date=summary_date,
                    email_address=student.email,
                    status="PENDING",
                )
                .on_conflict_do_nothing(
                    index_elements=[
                        "student_id",
                        "email_type",
                        "reference_date",
                    ]
                )
            )
            db.execute(stmt)
            db.flush()

            # The row may have been inserted by this request or already
            # existed from another/repeated cron execution.
            log = db.scalar(
                select(AttendanceEmailLog).where(
                    AttendanceEmailLog.student_id == student.id,
                    AttendanceEmailLog.email_type == "DAILY_SUMMARY",
                    AttendanceEmailLog.reference_date == summary_date,
                )
            )
            if log is None:
                failed += 1
                continue

            if log.status == "SENT":
                skipped += 1
                continue

            log.email_address = student.email
            log.status = "PENDING"
            log.error_message = None

        db.flush()

        try:
            _send_daily_summary_email(
                to_email=student.email,
                student_name=student.name,
                summary_date=summary_date.strftime("%d-%m-%Y"),
                subject_rows=rows,
                overall_present=overall_present,
                overall_conducted=overall_conducted,
            )
            log.status = "SENT"
            log.sent_at = datetime.utcnow()
            log.error_message = None
            sent += 1
        except (HTTPError, URLError, Exception) as exc:
            log.status = "FAILED"
            log.error_message = str(exc)
            failed += 1

    db.commit()
    return {"date": summary_date.isoformat(), "sent": sent, "skipped": skipped, "failed": failed}


@router.post("/daily-summary")
def daily_summary(
    x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret"),
    db: Session = Depends(get_db),
):
    """Cron endpoint: send the daily attendance summary for today in IST."""
    configured_secret = os.getenv("CRON_SECRET")
    if not configured_secret:
        raise HTTPException(503, "CRON_SECRET is not configured")
    if x_cron_secret != configured_secret:
        raise HTTPException(401, "Invalid cron secret")

    today_ist = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    return _send_daily_summaries_for_date(db, today_ist)
