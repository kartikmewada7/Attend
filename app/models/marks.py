from datetime import datetime
from decimal import Decimal
from sqlalchemy import DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

class MSTMark(Base):
    __tablename__ = "mst_marks"
    __table_args__ = (UniqueConstraint("student_id", "subject_id", "exam_name", name="uq_mst_student_subject_exam_name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="cascade"), nullable=False, index=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id", ondelete="restrict"), nullable=False, index=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id", ondelete="restrict"), nullable=False, index=True)
    exam_name: Mapped[str] = mapped_column(String(100), nullable=False)
    marks: Mapped[Decimal] = mapped_column(Numeric(6,2), nullable=False)
    max_marks: Mapped[Decimal] = mapped_column(Numeric(6,2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    @property
    def exam(self): return self.exam_name
