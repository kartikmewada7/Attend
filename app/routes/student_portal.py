import logging
from pathlib import Path
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select, func, case, and_
from sqlalchemy.orm import Session
from app.cache import cache
from app.core.config import settings
from app.database import get_db
from app.deps import require_role
from app.models import Student, Department, Semester, Section, Subject, SemesterSubject, Attendance, AttendanceSession, StudentFaceEmbedding
from app.services.face_recognition import register_embedding
from app.services.luxand import add_face, enroll_person, verification_passed, verify_person

logger = logging.getLogger("uvicorn")
router = APIRouter(prefix="/api/student", tags=["Student Portal"])
UPLOAD_DIR = Path("uploads/faces")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def student_section(db, s):
    d = db.get(Department, s.department_id)
    sem = db.get(Semester, s.current_semester_id)
    sec = db.get(Section, s.current_section_id)
    return d, sem, sec


@router.get("/me")
def me(user=Depends(require_role("student")), db: Session = Depends(get_db)):
    cache_key = f"student_profile:{user['id']}"
    cached_data = cache.get(cache_key)
    if cached_data is not None:
        return cached_data
    s = db.get(Student, user["id"])
    if not s:
        raise HTTPException(404, "Student not found")
    d, sem, sec = student_section(db, s)
    face = db.scalar(
        select(StudentFaceEmbedding.id).where(
            StudentFaceEmbedding.student_id == s.id,
            StudentFaceEmbedding.is_active.is_(True),
        )
    ) is not None
    result = {
        "id": s.id, "name": s.name, "roll_number": s.enrollment_no,
        "enrollment_no": s.enrollment_no, "email": s.email,
        "department": d.name if d else None,
        "year": (sem.semester_number + 1) // 2 if sem else None,
        "semester": sem.semester_number if sem else None,
        "section": sec.section_code if sec else None,
        "admission_year": s.admission_year, "batch_digit": s.batch_digit,
        "face_registered": face,
    }
    cache.set(cache_key, result, ttl=180)
    return result


@router.post("/me/face")
async def register_face(
    file: UploadFile = File(...),
    user=Depends(require_role("student")),
    db: Session = Depends(get_db),
):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(400, "Please capture or upload a valid photo")

    data = await file.read()
    if not data:
        raise HTTPException(400, "Empty image received")
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(400, "Image must be under 5 MB")

    s = db.get(Student, user["id"])
    if not s:
        raise HTTPException(404, "Student not found")

    active_face = db.scalar(
        select(StudentFaceEmbedding)
        .where(
            StudentFaceEmbedding.student_id == s.id,
            StudentFaceEmbedding.is_active.is_(True),
        )
        .order_by(StudentFaceEmbedding.id.desc())
    )

    # 1. Attempt local embedding extraction (YuNet + SFace)
    local_embedding = None
    try:
        emb_list, _, _ = register_embedding(data)
        local_embedding = emb_list
    except Exception as emb_exc:
        logger.info("Local face extraction: %s", emb_exc)

    # 2. Attempt Luxand Cloud enrollment / verification
    luxand_person_id = None
    luxand_success = False
    luxand_err = None

    if settings.LUXAND_API_TOKEN.strip():
        try:
            if active_face and active_face.luxand_person_id:
                verification = await verify_person(
                    active_face.luxand_person_id,
                    data,
                    file.filename or "verify.jpg",
                )
                if not verification_passed(verification):
                    raise HTTPException(
                        400,
                        "Face verification failed. The captured face does not match your registered face.",
                    )

                await add_face(
                    active_face.luxand_person_id,
                    data,
                    file.filename or "face.jpg",
                )
                luxand_person_id = active_face.luxand_person_id
                luxand_success = True
            else:
                luxand_person_id = await enroll_person(
                    f"{s.enrollment_no} | {s.name}",
                    data,
                    file.filename or "face.jpg",
                )
                luxand_success = True
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning("Luxand face service note: %s", exc)
            luxand_err = str(exc)

    # 3. Ensure at least one face model succeeded
    if not luxand_success and not local_embedding:
        raise HTTPException(
            400,
            f"Face could not be detected. Look directly at the camera with clear lighting. ({luxand_err or 'No face detected'})",
        )

    # 4. Save to database
    try:
        model_name = "Luxand.cloud" if luxand_success else "AttendAI (YuNet+SFace)"
        if active_face:
            if luxand_person_id:
                active_face.luxand_person_id = luxand_person_id
            if local_embedding:
                active_face.embedding = local_embedding
            active_face.model_name = model_name
            active_face.is_active = True
        else:
            new_face = StudentFaceEmbedding(
                student_id=s.id,
                embedding=local_embedding,
                model_name=model_name,
                luxand_person_id=luxand_person_id,
                is_active=True,
            )
            db.add(new_face)
            db.flush()
            active_face = new_face

        db.query(StudentFaceEmbedding).filter(
            StudentFaceEmbedding.student_id == s.id,
            StudentFaceEmbedding.id != active_face.id,
        ).update({"is_active": False})

        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(500, f"Database error saving face record: {exc}") from exc

    cache.delete(f"student_profile:{s.id}")
    cache.delete_pattern("students:*")
    cache.delete_pattern("section_students:*")
    cache.delete_pattern("face_embeddings:*")

    msg = (
        "Face registered successfully with Luxand Cloud."
        if luxand_success
        else "Face registered successfully with AttendAI Face Engine. (Note: Luxand free trial can be activated in dashboard)."
    )

    return {
        "message": msg,
        "face_registered": True,
        "provider": model_name,
        "luxand_active": luxand_success,
    }


@router.get("/me/attendance")
def my_attendance(user=Depends(require_role("student")), db: Session = Depends(get_db)):
    cache_key = f"student_attendance:{user['id']}"
    cached_data = cache.get(cache_key)
    if cached_data is not None:
        return cached_data
    s = db.get(Student, user["id"])
    if not s:
        return []
    rows = db.execute(
        select(
            Subject.id, Subject.name, Subject.code,
            func.count(Attendance.id).label("total"),
            func.sum(case((Attendance.status == "PRESENT", 1), else_=0)).label("present"),
        )
        .join(SemesterSubject, SemesterSubject.subject_id == Subject.id)
        .join(Semester, Semester.id == SemesterSubject.semester_id)
        .outerjoin(AttendanceSession, and_(AttendanceSession.subject_id == Subject.id, AttendanceSession.status == "CLOSED"))
        .outerjoin(Attendance, and_(Attendance.session_id == AttendanceSession.id, Attendance.student_id == user["id"]))
        .where(Semester.id == s.current_semester_id)
        .group_by(Subject.id, Subject.name, Subject.code)
        .order_by(Subject.name)
    ).all()
    result = [
        {
            "subject_id": r.id, "subject": r.name, "code": r.code,
            "present": int(r.present or 0), "total": int(r.total or 0),
            "percentage": round((int(r.present or 0) / int(r.total or 1)) * 100, 1) if r.total else 0,
        }
        for r in rows
    ]
    cache.set(cache_key, result, ttl=60)
    return result


@router.get("/subjects")
def subjects(user=Depends(require_role("student")), db: Session = Depends(get_db)):
    s = db.get(Student, user["id"])
    if not s:
        return []
    sem = db.get(Semester, s.current_semester_id)
    if not sem:
        return []
    cache_key = f"student_subjects:{sem.id}"
    cached_data = cache.get(cache_key)
    if cached_data is not None:
        return cached_data
    rows = db.execute(
        select(Subject).join(SemesterSubject, SemesterSubject.subject_id == Subject.id)
        .where(SemesterSubject.semester_id == sem.id).order_by(Subject.name)
    ).scalars().all()
    result = [{"id": x.id, "name": x.name, "code": x.code, "semester": sem.semester_number} for x in rows]
    cache.set(cache_key, result, ttl=300)
    return result
