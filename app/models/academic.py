from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, SmallInteger, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

class Department(Base):
    __tablename__ = "departments"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    college_code: Mapped[str] = mapped_column(String(20), default="0808", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

class AcademicYear(Base):
    __tablename__ = "academic_years"
    id: Mapped[int] = mapped_column(primary_key=True)
    year_number: Mapped[int] = mapped_column(SmallInteger, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(50), nullable=False)

class Semester(Base):
    __tablename__ = "semesters"
    id: Mapped[int] = mapped_column(primary_key=True)
    year_id: Mapped[int] = mapped_column(ForeignKey("academic_years.id", ondelete="restrict"), nullable=False)
    semester_number: Mapped[int] = mapped_column(SmallInteger, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(50), nullable=False)

class Section(Base):
    __tablename__ = "sections"
    __table_args__ = (UniqueConstraint("department_id", "semester_id", "section_code", name="uq_section_department_semester_code"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id", ondelete="restrict"), nullable=False, index=True)
    semester_id: Mapped[int] = mapped_column(ForeignKey("semesters.id", ondelete="restrict"), nullable=False, index=True)
    section_code: Mapped[str] = mapped_column(String(30), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

class SemesterSubject(Base):
    __tablename__ = "semester_subjects"
    __table_args__ = (UniqueConstraint("semester_id", "subject_id", name="uq_semester_subject"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    semester_id: Mapped[int] = mapped_column(ForeignKey("semesters.id", ondelete="cascade"), nullable=False, index=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id", ondelete="cascade"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
