from datetime import datetime
from sqlalchemy import ARRAY, Boolean, DateTime, ForeignKey, Float, String
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

class StudentFaceEmbedding(Base):
    __tablename__ = "student_face_embeddings"
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="cascade"), nullable=False, index=True)
    embedding: Mapped[list[float]] = mapped_column(ARRAY(Float), nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), default="SFace", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
