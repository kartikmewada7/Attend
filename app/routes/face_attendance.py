from datetime import datetime, timezone

import numpy as np
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.core.config import settings
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
from app.services.storage import upload_bytes
from app.services.face_recognition import (
    FACE_TOLERANCE,
    best_match,
    decode_image,
    detect_face_locations,
    embedding_from_db,
    extract_encodings,
)

router = APIRouter(prefix="/api/face", tags=["Face Recognition Attendance"])

MAX_FACES_PER_PHOTO = 40
MAX_PHOTO_BYTES = 5 * 1024 * 1024
MAX_SESSION_PHOTOS = 5
MAX_SESSION_BYTES = 35 * 1024 * 1024


def utcnow():
    return datetime.now(timezone.utc)


def authorized_teacher_section(db: Session, teacher_id: int, subject_id: int, section_id: int):
    mapping = db.scalar(
        select(TeacherSubjectSection).where(
            TeacherSubjectSection.teacher_id == teacher_id,
            TeacherSubjectSection.subject_id == subject_id,
            TeacherSubjectSection.section_id == section_id,
        )
    )
    if not mapping:
        raise HTTPException(403, "Subject and section are not assigned to this teacher")

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
        raise HTTPException(400, "Selected subject does not belong to this semester")

    return mapping


def create_session(db: Session, teacher_id: int, subject_id: int, section_id: int):
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


def load_known_faces(db: Session, section_id: int):
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
        )
        .order_by(Student.roll_no)
    ).all()

    students_by_id = {}
    embeddings = []
    for student, face in rows:
        try:
            vector = embedding_from_db(face.embedding)
        except ValueError:
            continue
        students_by_id[student.id] = student
        embeddings.append((student.id, vector))

    return students_by_id, embeddings


def recognize_photo(image, locations, encodings, students_by_id, known_embeddings, already_marked):
    results = []

    for location, encoding in zip(locations, encodings):
        student_id, distance, matched = best_match(known_embeddings, encoding)
        top, right, bottom, left = location

        item = {
            "recognized": False,
            "distance": round(distance, 4) if distance is not None else None,
            "tolerance": FACE_TOLERANCE,
            "bbox": [left, top, max(0, right - left), max(0, bottom - top)],
        }

        if matched and student_id in students_by_id:
            student = students_by_id[student_id]
            item.update(
                {
                    "recognized": True,
                    "student_id": student.id,
                    "name": student.name,
                    "enrollment_no": student.enrollment_no,
                    "roll_no": student.roll_no,
                }
            )

            if student.id in already_marked:
                item["attendance"] = "already_marked"
            else:
                item["attendance"] = "marked"
                already_marked.add(student.id)

        results.append(item)

    return results


def mark_new_attendance_rows(db: Session, session_id: int, results):
    student_ids = {
        int(item["student_id"])
        for item in results
        if item.get("recognized") and item.get("attendance") == "marked"
    }
    for student_id in student_ids:
        db.add(
            Attendance(
                session_id=session_id,
                student_id=student_id,
                status="PRESENT",
                source="FACE",
                recognition_confidence=None,
                marked_at=utcnow(),
            )
        )


async def read_image_upload(upload: UploadFile) -> bytes:
    if not upload.content_type or not upload.content_type.startswith("image/"):
        raise HTTPException(400, "Only image files are allowed")
    data = await upload.read()
    if not data:
        raise HTTPException(400, "Empty image file")
    if len(data) > MAX_PHOTO_BYTES:
        raise HTTPException(400, "Each attendance image must be 5 MB or less")
    return data


def recognize_single_photo(data, students_by_id, known_embeddings, already_marked):
    try:
        image = decode_image(data)
        locations = detect_face_locations(image)
        if len(locations) > MAX_FACES_PER_PHOTO:
            raise HTTPException(400, f"Too many faces in one photo. Maximum supported is {MAX_FACES_PER_PHOTO}.")
        encodings = extract_encodings(image, locations)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, f"Face recognition model error: {exc}") from exc

    if len(encodings) != len(locations):
        raise HTTPException(500, "Face encoding failed for one or more detected faces")

    results = recognize_photo(
        image,
        locations,
        encodings,
        students_by_id,
        known_embeddings,
        already_marked,
    )
    return image, locations, results


@router.post("/recognize")
async def recognize_and_mark(
    subject_id: int,
    section_id: int,
    file: UploadFile = File(...),
    user=Depends(require_role("teacher")),
    db: Session = Depends(get_db),
):
    authorized_teacher_section(db, user["id"], subject_id, section_id)
    data = await read_image_upload(file)

    students_by_id, known_embeddings = load_known_faces(db, section_id)
    if not known_embeddings:
        raise HTTPException(400, "No registered student faces found in this section")

    session = create_session(db, user["id"], subject_id, section_id)
    already_marked: set[int] = set()

    try:
        image, locations, results = recognize_single_photo(
            data, students_by_id, known_embeddings, already_marked
        )
        for item in results:
            if item.get("recognized"):
                item["recognition_confidence"] = round(
                    max(0.0, 1.0 - float(item["distance"])), 4
                )

        mark_new_attendance_rows(db, session.id, results)
        storage_path = upload_bytes(
            settings.SUPABASE_ATTENDANCE_BUCKET,
            f"session-{session.id}/photo-1-{file.filename or 'attendance.jpg'}",
            data,
            file.content_type or "image/jpeg",
        )
        db.add(
            AttendanceSessionPhoto(
                session_id=session.id,
                photo_index=1,
                file_name=file.filename,
                storage_path=storage_path,
                file_size_bytes=len(data),
                captured_at=utcnow(),
            )
        )
        session.status = "CLOSED"
        session.ended_at = utcnow()
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        "session_id": session.id,
        "subject_id": subject_id,
        "section_id": section_id,
        "photos": 1,
        "faces_detected": len(locations),
        "recognized": [x for x in results if x.get("recognized")],
        "faces": results,
    }


@router.post("/recognize-batch")
async def recognize_batch(
    subject_id: int,
    section_id: int,
    files: list[UploadFile] = File(...),
    user=Depends(require_role("teacher")),
    db: Session = Depends(get_db),
):
    authorized_teacher_section(db, user["id"], subject_id, section_id)

    if not files:
        raise HTTPException(400, "At least one image is required")
    if len(files) > MAX_SESSION_PHOTOS:
        raise HTTPException(400, "Maximum 5 photos per attendance session")

    students_by_id, known_embeddings = load_known_faces(db, section_id)
    if not known_embeddings:
        raise HTTPException(400, "No registered student faces found in this section")

    session = create_session(db, user["id"], subject_id, section_id)
    already_marked: set[int] = set()
    total_bytes = 0
    combined = []
    total_faces = 0

    try:
        for index, upload in enumerate(files, start=1):
            data = await read_image_upload(upload)
            total_bytes += len(data)
            if total_bytes > MAX_SESSION_BYTES:
                raise HTTPException(400, "Total attendance photos must be 35 MB or less")

            image, locations, results = recognize_single_photo(
                data, students_by_id, known_embeddings, already_marked
            )
            total_faces += len(locations)
            combined.extend(results)

            for item in results:
                if item.get("recognized"):
                    item["recognition_confidence"] = round(
                        max(0.0, 1.0 - float(item["distance"])), 4
                    )

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

        mark_new_attendance_rows(db, session.id, combined)
        session.status = "CLOSED"
        session.ended_at = utcnow()
        db.commit()
    except Exception:
        db.rollback()
        raise

    # One result per recognized student, preserving first/best occurrence.
    unique = {}
    for item in combined:
        if item.get("recognized"):
            sid = item["student_id"]
            if sid not in unique or (
                item.get("distance") is not None
                and item["distance"] < unique[sid].get("distance", 999)
            ):
                unique[sid] = item

    return {
        "session_id": session.id,
        "subject_id": subject_id,
        "section_id": section_id,
        "photos": len(files),
        "total_faces_detected": total_faces,
        "recognized": list(unique.values()),
        "faces": combined,
    }
