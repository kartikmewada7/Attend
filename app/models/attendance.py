from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, SmallInteger, String, BigInteger, Float, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

class AttendanceSession(Base):
    __tablename__ = "attendance_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id", ondelete="restrict"), nullable=False, index=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id", ondelete="restrict"), nullable=False, index=True)
    section_id: Mapped[int] = mapped_column(ForeignKey("sections.id", ondelete="restrict"), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="OPEN", nullable=False)

class AttendanceSessionPhoto(Base):
    __tablename__ = "attendance_session_photos"
    __table_args__ = (UniqueConstraint("session_id", "photo_index", name="uq_attendance_photo_index"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("attendance_sessions.id", ondelete="cascade"), nullable=False, index=True)
    photo_index: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    file_name: Mapped[str | None] = mapped_column(String(255))
    storage_path: Mapped[str | None] = mapped_column(String(1000))
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

class Attendance(Base):
    __tablename__ = "attendance"
    __table_args__ = (UniqueConstraint("session_id", "student_id", name="uq_attendance_session_student"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("attendance_sessions.id", ondelete="cascade"), nullable=False, index=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="restrict"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default="PRESENT", nullable=False)
    marked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    recognition_confidence: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(30), default="FACE", nullable=False)
