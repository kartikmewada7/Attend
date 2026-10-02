from pydantic import BaseModel, EmailStr

class TeacherProfileUpdate(BaseModel):
    name: str | None = None
    email: EmailStr | None = None
    department: str | None = None
    password: str | None = None
