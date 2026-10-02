from datetime import date, datetime
from sqlalchemy import Date, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

class AttendanceEmailLog(Base):
    __tablename__ = "attendance_email_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="cascade"), nullable=False, index=True)
    attendance_id: Mapped[int | None] = mapped_column(ForeignKey("attendance.id", ondelete="cascade"))
    email_type: Mapped[str] = mapped_column(String(30), nullable=False)
    reference_date: Mapped[date] = mapped_column(Date, default=date.today, nullable=False)
    email_address: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="PENDING", nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
