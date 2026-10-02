from datetime import date, datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, and_, func
from sqlalchemy.orm import Session
from app.cache import cache
from app.database import get_db
from app.deps import require_role
from app.models import Subject, Student, Department, Semester, Section, SemesterSubject, TeacherSubjectSection, AttendanceSession, Attendance, StudentFaceEmbedding
from app.services.academic import get_or_create_department, get_semester, get_section

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
        .join(TeacherSubjectSection, TeacherSubjectSection.subject_id == Subject.id)
        .join(Section, Section.id == TeacherSubjectSection.section_id)
        .join(Semester, Semester.id == Section.semester_id)
        .join(Department, Department.id == Section.department_id)
        .where(TeacherSubjectSection.teacher_id == teacher_id)
        .order_by(Subject.name, Section.section_code)
    ).all()


def ensure_session(db, teacher_id, subject_id, section_id, attendance_date):
    start = datetime.combine(attendance_date, datetime.min.time())
    end = datetime.combine(attendance_date, datetime.max.time())
    s = db.scalar(
        select(AttendanceSession).where(
            AttendanceSession.teacher_id == teacher_id,
            AttendanceSession.subject_id == subject_id,
            AttendanceSession.section_id == section_id,
            AttendanceSession.started_at >= start,
            AttendanceSession.started_at <= end,
        ).order_by(AttendanceSession.id.desc())
    )
    if not s:
        s = AttendanceSession(
            teacher_id=teacher_id, subject_id=subject_id, section_id=section_id,
            status="CLOSED", started_at=datetime.utcnow(), ended_at=datetime.utcnow(),
        )
        db.add(s)
        db.flush()
    return s


def authorized(db, teacher_id, subject_id, section_id):
    return db.scalar(
        select(TeacherSubjectSection).where(
            TeacherSubjectSection.teacher_id == teacher_id,
            TeacherSubjectSection.subject_id == subject_id,
            TeacherSubjectSection.section_id == section_id,
        )
    ) is not None


@router.get("/subjects")
def list_subjects(user=Depends(require_role("teacher")), db: Session = Depends(get_db)):
    cache_key = f"teacher_subjects:{user['id']}"
    cached_data = cache.get(cache_key)
    if cached_data is not None:
        return cached_data
    rows = teacher_subjects(db, user["id"])
    result = [
        {
            "id": s.id, "name": s.name, "code": s.code, "department": d.name,
            "year": (sem.semester_number + 1) // 2, "semester": sem.semester_number,
            "section": sec.section_code, "section_id": sec.id,
        }
        for s, sec, sem, d in rows
    ]
    cache.set(cache_key, result, ttl=180)
    return result


@router.post("/subjects")
def create_subject(name: str, code: str, department: str = "CSE", year: int | None = None, semester: int = 1, section: str | None = None, user=Depends(require_role("teacher")), db: Session = Depends(get_db)):
    name, code = name.strip(), code.strip().upper()
    if db.scalar(select(Subject).where(Subject.code == code)):
        raise HTTPException(409, "Subject code already exists")
    dep = get_or_create_department(db, department)
    sem = get_semester(db, semester)
    s = Subject(name=name, code=code)
    db.add(s)
    db.flush()
    db.add(SemesterSubject(semester_id=sem.id, subject_id=s.id))
    db.flush()
    sections = db.scalars(select(Section).where(Section.department_id == dep.id, Section.semester_id == sem.id)).all()
    if section:
        sections = [get_section(db, dep.id, sem.id, section)]
    if not sections:
        sections = [get_section(db, dep.id, sem.id, section or "S1")]
    for sec in sections:
        exists = db.scalar(
            select(TeacherSubjectSection).where(
                TeacherSubjectSection.teacher_id == user["id"],
                TeacherSubjectSection.subject_id == s.id,
                TeacherSubjectSection.section_id == sec.id,
            )
        )
        if not exists:
            db.add(TeacherSubjectSection(teacher_id=user["id"], subject_id=s.id, section_id=sec.id))
    db.commit()
    cache.delete_pattern("teacher_subjects:*")
    cache.delete_pattern("student_subjects:*")
    return {"id": s.id, "name": s.name, "code": s.code, "semester": sem.semester_number, "department": dep.name}


@router.get("/students")
def subject_students(subject_id: int, section_id: int | None = None, user=Depends(require_role("teacher")), db: Session = Depends(get_db)):
    if section_id is None:
        section_id = db.scalar(select(TeacherSubjectSection.section_id).where(TeacherSubjectSection.teacher_id == user["id"], TeacherSubjectSection.subject_id == subject_id))
    if not section_id or not authorized(db, user["id"], subject_id, section_id):
        raise HTTPException(403, "Subject/section not assigned to teacher")
    cache_key = f"section_students:{section_id}"
    cached_data = cache.get(cache_key)
    if cached_data is not None:
        return cached_data
    rows = db.scalars(select(Student).where(Student.current_section_id == section_id, Student.is_active.is_(True)).order_by(Student.name)).all()
    face_ids = set(db.scalars(select(StudentFaceEmbedding.student_id).where(StudentFaceEmbedding.is_active.is_(True))).all())
    result = [{"id": s.id, "name": s.name, "roll_number": s.enrollment_no, "enrollment_no": s.enrollment_no, "face_registered": s.id in face_ids} for s in rows]
    cache.set(cache_key, result, ttl=120)
    return result


@router.get("/records")
def get_records(subject_id: int, attendance_date: date, section_id: int | None = None, user=Depends(require_role("teacher")), db: Session = Depends(get_db)):
    if section_id is None:
        section_id = db.scalar(select(TeacherSubjectSection.section_id).where(TeacherSubjectSection.teacher_id == user["id"], TeacherSubjectSection.subject_id == subject_id))
    if not section_id or not authorized(db, user["id"], subject_id, section_id):
        raise HTTPException(403, "Subject/section not assigned")
    s = ensure_session(db, user["id"], subject_id, section_id, attendance_date)
    db.commit()
    rows = db.scalars(select(Attendance).where(Attendance.session_id == s.id)).all()
    return [{"student_id": r.student_id, "status": r.status.lower()} for r in rows]


@router.post("/mark")
def mark(payload: MarkAttendance, user=Depends(require_role("teacher")), db: Session = Depends(get_db)):
    if payload.status not in {"present", "absent"}:
        raise HTTPException(400, "Invalid attendance status")
    section_id = payload.section_id or db.scalar(select(TeacherSubjectSection.section_id).where(TeacherSubjectSection.teacher_id == user["id"], TeacherSubjectSection.subject_id == payload.subject_id))
    if not section_id or not authorized(db, user["id"], payload.subject_id, section_id):
        raise HTTPException(403, "Subject/section not assigned")
    student = db.get(Student, payload.student_id)
    if not student or student.current_section_id != section_id:
        raise HTTPException(404, "Student not found in selected section")
    sess = ensure_session(db, user["id"], payload.subject_id, section_id, payload.attendance_date)
    row = db.scalar(select(Attendance).where(Attendance.session_id == sess.id, Attendance.student_id == student.id))
    if row:
        row.status = payload.status.upper()
        row.source = "MANUAL"
        row.marked_at = datetime.utcnow()
    else:
        db.add(Attendance(session_id=sess.id, student_id=student.id, status=payload.status.upper(), source="MANUAL"))
    db.commit()
    cache.delete_pattern(f"student_attendance:{student.id}")
    cache.delete_pattern("attendance_history:*")
    return {"message": "Attendance saved"}


@router.post("/bulk")
def bulk_mark(payload: BulkAttendance, user=Depends(require_role("teacher")), db: Session = Depends(get_db)):
    section_id = payload.section_id or db.scalar(select(TeacherSubjectSection.section_id).where(TeacherSubjectSection.teacher_id == user["id"], TeacherSubjectSection.subject_id == payload.subject_id))
    if not section_id or not authorized(db, user["id"], payload.subject_id, section_id):
        raise HTTPException(403, "Subject/section not assigned")
    sess = ensure_session(db, user["id"], payload.subject_id, section_id, payload.attendance_date)
    count = 0
    for item in payload.records:
        sid = int(item.get("student_id"))
        status = str(item.get("status", "absent")).lower()
        if status not in {"present", "absent"}:
            raise HTTPException(400, "Invalid attendance status")
        student = db.get(Student, sid)
        if not student or student.current_section_id != section_id:
            continue
        row = db.scalar(select(Attendance).where(Attendance.session_id == sess.id, Attendance.student_id == sid))
        if row:
            row.status = status.upper()
            row.source = "MANUAL"
            row.marked_at = datetime.utcnow()
        else:
            db.add(Attendance(session_id=sess.id, student_id=sid, status=status.upper(), source="MANUAL"))
        count += 1
    db.commit()
    cache.delete_pattern("student_attendance:*")
    cache.delete_pattern("attendance_history:*")
    return {"message": "Attendance saved", "count": count}


@router.get("/history")
def history(user=Depends(require_role("teacher")), db: Session = Depends(get_db)):
    cache_key = f"attendance_history:{user['id']}"
    cached_data = cache.get(cache_key)
    if cached_data is not None:
        return cached_data
    rows = db.execute(
        select(Attendance.id, AttendanceSession.started_at, Attendance.marked_at, Attendance.status, Student.name, Student.enrollment_no, Subject.name.label("subject"), Subject.code)
        .join(AttendanceSession, AttendanceSession.id == Attendance.session_id)
        .join(Student, Student.id == Attendance.student_id)
        .join(Subject, Subject.id == AttendanceSession.subject_id)
        .where(AttendanceSession.teacher_id == user["id"])
        .order_by(AttendanceSession.started_at.desc(), Subject.name, Student.name)
    ).all()
    result = [
        {
            "id": r.id, "date": r.started_at.date(), "marked_at": r.marked_at,
            "status": r.status.lower(), "student_name": r.name,
            "roll_number": r.enrollment_no, "subject": r.subject, "code": r.code,
        }
        for r in rows
    ]
    cache.set(cache_key, result, ttl=60)
    return result
