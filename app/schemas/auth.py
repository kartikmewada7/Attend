from pydantic import BaseModel, EmailStr, field_validator

class TeacherRegisterRequest(BaseModel):
    name: str
    email: EmailStr
    department: str | None = None

class TeacherVerifyRequest(BaseModel):
    name: str
    email: EmailStr
    department: str | None = None
    otp: str

class TeacherOTPRequest(BaseModel):
    email: EmailStr

class TeacherOTPVerify(BaseModel):
    email: EmailStr
    otp: str

class StudentLogin(BaseModel):
    roll_number: str
    password: str

class StudentResetRequest(BaseModel):
    roll_number: str
    email: EmailStr

class StudentResetVerify(BaseModel):
    roll_number: str
    email: EmailStr
    otp: str
    new_password: str

class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict
