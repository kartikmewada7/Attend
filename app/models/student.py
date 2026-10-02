from datetime import date, datetime
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, SmallInteger, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

class Student(Base):
    __tablename__ = "students"
    id: Mapped[int] = mapped_column(primary_key=True)
    enrollment_no: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    roll_no: Mapped[int] = mapped_column(nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), unique=True)
    phone: Mapped[str | None] = mapped_column(String(30))
    dob: Mapped[date] = mapped_column(Date, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id", ondelete="restrict"), nullable=False, index=True)
    current_semester_id: Mapped[int] = mapped_column(ForeignKey("semesters.id", ondelete="restrict"), nullable=False, index=True)
    current_section_id: Mapped[int] = mapped_column(ForeignKey("sections.id", ondelete="restrict"), nullable=False, index=True)
    admission_year: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    batch_digit: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    @property
    def roll_number(self): return self.enrollment_no
    @property
    def course(self): return None
    @property
    def face_registered(self): return False

class StudentAcademicHistory(Base):
    __tablename__ = "student_academic_history"
    __table_args__ = (UniqueConstraint("student_id", "semester_id", name="uq_student_semester_history"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="cascade"), nullable=False, index=True)
    semester_id: Mapped[int] = mapped_column(ForeignKey("semesters.id", ondelete="restrict"), nullable=False)
    section_id: Mapped[int] = mapped_column(ForeignKey("sections.id", ondelete="restrict"), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
