from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

class TeacherSubjectSection(Base):
    __tablename__ = "teacher_subject_sections"
    __table_args__ = (UniqueConstraint("teacher_id", "subject_id", "section_id", name="uq_teacher_subject_section"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id", ondelete="cascade"), nullable=False, index=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id", ondelete="cascade"), nullable=False)
    section_id: Mapped[int] = mapped_column(ForeignKey("sections.id", ondelete="cascade"), nullable=False, index=True)
