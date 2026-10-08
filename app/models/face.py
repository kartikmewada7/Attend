from datetime import datetime
from sqlalchemy import ARRAY, Boolean, DateTime, ForeignKey, Float, String
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

class StudentFaceEmbedding(Base):
    __tablename__ = "student_face_embeddings"
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="cascade"), nullable=False, index=True)
    # Kept for backward compatibility with the old local SFace pipeline.
    # Luxand.cloud is now the active recognition provider.
    embedding: Mapped[list[float] | None] = mapped_column(ARRAY(Float), nullable=True)
    model_name: Mapped[str] = mapped_column(String(100), default="Luxand.cloud", nullable=False)
    luxand_person_id: Mapped[str | None] = mapped_column(String(255), unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
