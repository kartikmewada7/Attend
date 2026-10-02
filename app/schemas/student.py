from datetime import datetime, date
from pydantic import BaseModel, ConfigDict, EmailStr, field_validator

class StudentBase(BaseModel):
    name: str
    roll_number: str | None = None
    email: EmailStr | None = None
    course: str | None = None
    dob: date
    department: str | None = None
    year: int | None = None
    semester: int | None = None
    section: str | None = None
    admission_year: int | None = None
    batch_digit: int | None = 1

    @field_validator("roll_number")
    @classmethod
    def normalize_roll(cls, v):
        if v is None: return v
        v=v.strip()
        return v or None

class StudentCreate(StudentBase):
    pass

class StudentOut(BaseModel):
    id: int
    name: str
    roll_number: str
    email: EmailStr | None
    course: str | None
    dob: date | None
    department: str | None
    year: int | None
    semester: int | None
    section: str | None
    admission_year: int | None
    face_registered: bool
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
