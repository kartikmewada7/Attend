from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database import get_db
from app.deps import require_role
from app.models import (
    Attendance,
    AttendanceSession,
    AttendanceSessionPhoto,
    Section,
    SemesterSubject,
    Student,
    StudentFaceEmbedding,
    Subject,
    TeacherSubjectSection,
)
from app.routes.attendance import send_attendance_confirmation
from app.services.luxand import recognize_all
from app.services.storage import upload_bytes

router = APIRouter(prefix="/api/face", tags=["Face Recognition Attendance"])

MAX_FACES_PER_PHOTO = 40
MAX_PHOTO_BYTES = 5 * 1024 * 1024
MAX_SESSION_PHOTOS = 5
MAX_SESSION_BYTES = 35 * 1024 * 1024


def utcnow():
    return datetime.now(timezone.utc)


def authorized_teacher_section(
    db: Session,
    teacher_id: int,
    subject_id: int,
    section_id: int,
):
    mapping = db.scalar(
        select(TeacherSubjectSection).where(
            TeacherSubjectSection.teacher_id == teacher_id,
            TeacherSubjectSection.subject_id == subject_id,
            TeacherSubjectSection.section_id == section_id,
        )
    )
    if not mapping:
        raise HTTPException(
            403,
            "Subject and section are not assigned to this teacher",
        )

    section = db.get(Section, section_id)
    if not section:
        raise HTTPException(404, "Section not found")

    subject_in_semester = db.scalar(
        select(SemesterSubject.id).where(
            SemesterSubject.subject_id == subject_id,
            SemesterSubject.semester_id == section.semester_id,
        )
    )
    if not subject_in_semester:
        raise HTTPException(
            400,
            "Selected subject does not belong to this semester",
        )

    return mapping


def create_session(
    db: Session,
    teacher_id: int,
    subject_id: int,
    section_id: int,
):
    session = AttendanceSession(
        teacher_id=teacher_id,
        subject_id=subject_id,
        section_id=section_id,
        status="OPEN",
        started_at=utcnow(),
    )
    db.add(session)
    db.flush()
    return session


def load_luxand_faces(db: Session, section_id: int):
    rows = db.execute(
        select(Student, StudentFaceEmbedding)
        .join(
            StudentFaceEmbedding,
            StudentFaceEmbedding.student_id == Student.id,
        )
        .where(
            Student.current_section_id == section_id,
            Student.is_active.is_(True),
            StudentFaceEmbedding.is_active.is_(True),
            StudentFaceEmbedding.luxand_person_id.is_not(None),
        )
        .order_by(Student.roll_no)
    ).all()

    students_by_luxand_id: dict[str, Student] = {}
    for student, face in rows:
        students_by_luxand_id[str(face.luxand_person_id)] = student

    return students_by_luxand_id


async def read_image_upload(upload: UploadFile) -> bytes:
    if not upload.content_type or not upload.content_type.startswith("image/"):
        raise HTTPException(400, "Only image files are allowed")

    data = await upload.read()

    if not data:
        raise HTTPException(400, "Empty image file")

    if len(data) > MAX_PHOTO_BYTES:
        raise HTTPException(
            400,
            "Each attendance image must be 5 MB or less",
        )

    return data


async def recognize_photo(
    data: bytes,
    filename: str,
    students_by_luxand_id: dict[str, Student],
):
    try:
        luxand_faces = await recognize_all(data, filename)
    except Exception as exc:
        raise HTTPException(
            502,
            f"Luxand recognition service error: {exc}",
        ) from exc

    if len(luxand_faces) > MAX_FACES_PER_PHOTO:
        raise HTTPException(
            400,
            f"Too many faces in one photo. Maximum supported is {MAX_FACES_PER_PHOTO}.",
        )

    results = []

    for item in luxand_faces:
        person_id = str(item["luxand_person_id"])
        student = students_by_luxand_id.get(person_id)

        result = {
            "recognized": bool(student),
            "luxand_person_id": person_id,
            "name": item.get("name"),
            "confidence": item.get("confidence"),
        }

        if student:
            result.update(
                {
                    "student_id": student.id,
                    "name": student.name,
                    "enrollment_no": student.enrollment_no,
                    "roll_no": student.roll_no,
                }
            )

        results.append(result)

    return results


def add_attendance_rows(
    db: Session,
    session_id: int,
    recognized_results: list[dict],
    already_marked: set[int],
):
    created: list[Attendance] = []

    for item in recognized_results:
        if not item.get("recognized"):
            continue

        student_id = int(item["student_id"])

        if student_id in already_marked:
            item["attendance"] = "already_marked"
            continue

        attendance = Attendance(
            session_id=session_id,
            student_id=student_id,
            status="PRESENT",
            source="FACE_LUXAND",
            recognition_confidence=item.get("confidence"),
            marked_at=utcnow(),
        )
        db.add(attendance)
        already_marked.add(student_id)
        item["attendance"] = "marked"
        created.append(attendance)

    return created


async def process_attendance(
    *,
    subject_id: int,
    section_id: int,
    files: list[UploadFile],
    user,
    db: Session,
):
    authorized_teacher_section(
        db,
        user["id"],
        subject_id,
        section_id,
    )

    if not files:
        raise HTTPException(400, "At least one camera photo is required")

    if len(files) > MAX_SESSION_PHOTOS:
        raise HTTPException(
            400,
            "Maximum 5 photos per attendance session",
        )

    students_by_luxand_id = load_luxand_faces(db, section_id)

    if not students_by_luxand_id:
        raise HTTPException(
            400,
            "No students in this section have registered their face with Luxand yet",
        )

    subject = db.get(Subject, subject_id)
    if not subject:
        raise HTTPException(404, "Subject not found")

    session = create_session(
        db,
        user["id"],
        subject_id,
        section_id,
    )

    already_marked: set[int] = set()
    total_bytes = 0
    combined: list[dict] = []
    total_faces = 0

    try:
        for index, upload in enumerate(files, start=1):
            data = await read_image_upload(upload)
            total_bytes += len(data)

            if total_bytes > MAX_SESSION_BYTES:
                raise HTTPException(
                    400,
                    "Total attendance photos must be 35 MB or less",
                )

            results = await recognize_photo(
                data,
                upload.filename or f"attendance-{index}.jpg",
                students_by_luxand_id,
            )

            total_faces += len(results)
            combined.extend(results)

            storage_path = upload_bytes(
                settings.SUPABASE_ATTENDANCE_BUCKET,
                f"session-{session.id}/photo-{index}-{upload.filename or 'attendance.jpg'}",
                data,
                upload.content_type or "image/jpeg",
            )

            db.add(
                AttendanceSessionPhoto(
                    session_id=session.id,
                    photo_index=index,
                    file_name=upload.filename,
                    storage_path=storage_path,
                    file_size_bytes=len(data),
                    captured_at=utcnow(),
                )
            )

        attendance_rows = add_attendance_rows(
            db,
            session.id,
            combined,
            already_marked,
        )

        # IDs are required by the attendance email log.
        db.flush()

        for attendance in attendance_rows:
            student = db.get(Student, attendance.student_id)
            if student:
                send_attendance_confirmation(
                    db,
                    attendance,
                    student,
                    subject,
                )

        session.status = "CLOSED"
        session.ended_at = utcnow()
        db.commit()

    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise

    # One result per recognized student, keeping the highest confidence.
    unique: dict[int, dict] = {}

    for item in combined:
        if not item.get("recognized"):
            continue

        student_id = int(item["student_id"])
        current = unique.get(student_id)

        if current is None:
            unique[student_id] = item
            continue

        current_conf = current.get("confidence")
        new_conf = item.get("confidence")

        if (
            new_conf is not None
            and (current_conf is None or new_conf > current_conf)
        ):
            unique[student_id] = item

    return {
        "session_id": session.id,
        "subject_id": subject_id,
        "section_id": section_id,
        "photos": len(files),
        "total_faces_detected": total_faces,
        "recognized": list(unique.values()),
        "faces": combined,
        "provider": "Luxand.cloud",
    }


@router.post("/recognize")
async def recognize_and_mark(
    subject_id: int,
    section_id: int,
    file: UploadFile = File(...),
    user=Depends(require_role("teacher")),
    db: Session = Depends(get_db),
):
    return await process_attendance(
        subject_id=subject_id,
        section_id=section_id,
        files=[file],
        user=user,
        db=db,
    )


@router.post("/recognize-batch")
async def recognize_batch(
    subject_id: int,
    section_id: int,
    files: list[UploadFile] = File(...),
    user=Depends(require_role("teacher")),
    db: Session = Depends(get_db),
):
    return await process_attendance(
        subject_id=subject_id,
        section_id=section_id,
        files=files,
        user=user,
        db=db,
    )
