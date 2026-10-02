import secrets
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Teacher, Student, Department
from app.schemas.auth import TeacherRegisterRequest, TeacherVerifyRequest, TeacherOTPRequest, TeacherOTPVerify, StudentLogin, StudentResetRequest, StudentResetVerify, TokenOut
from app.core.security import hash_password, verify_password, create_access_token
from app.services.otp import issue_otp, verify_otp, normalize_email
from app.services.academic import get_or_create_department

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

def require_org(email: str):
    if not normalize_email(email).endswith(".org"): raise HTTPException(400, "Teacher email must end with .org")

def teacher_user(t, department=None):
    return {"id": t.id, "name": t.name, "email": t.email, "role": "Teacher", "department": department}

def student_user(s, department=None, semester=None, section=None, face_registered=False):
    return {"id": s.id, "name": s.name, "roll_number": s.enrollment_no, "enrollment_no": s.enrollment_no, "email": s.email, "role": "Student", "department": department, "semester": semester, "section": section, "face_registered": face_registered}

def teacher_context(db, t):
    d = db.get(Department, t.department_id) if t.department_id else None
    return teacher_user(t, d.name if d else None)

def student_context(db, s):
    d = db.get(Department, s.department_id); sem = __import__('app.models', fromlist=['Semester']).Semester
    sec = __import__('app.models', fromlist=['Section']).Section
    semester = db.get(sem, s.current_semester_id); section = db.get(sec, s.current_section_id)
    face = db.execute(__import__('sqlalchemy', fromlist=['select']).select(__import__('app.models', fromlist=['StudentFaceEmbedding']).StudentFaceEmbedding.id).where(__import__('app.models', fromlist=['StudentFaceEmbedding']).StudentFaceEmbedding.student_id==s.id, __import__('app.models', fromlist=['StudentFaceEmbedding']).StudentFaceEmbedding.is_active.is_(True))).first() is not None
    return student_user(s, d.name if d else None, semester.semester_number if semester else None, section.section_code if section else None, face)

@router.post("/teacher/register/request-otp")
def teacher_register_request(payload: TeacherRegisterRequest, db: Session = Depends(get_db)):
    require_org(payload.email); email=normalize_email(str(payload.email))
    if not payload.name.strip(): raise HTTPException(400,"Name is required")

    teacher = db.scalar(select(Teacher).where(Teacher.email == email))

    if teacher and teacher.is_verified and teacher.is_active:
        raise HTTPException(409,"Teacher email already registered. Use login OTP.")

    dep = get_or_create_department(db, payload.department or "CSE")

    # Reuse an unverified teacher row so an interrupted registration can
    # simply request a fresh registration OTP.
    if teacher and not teacher.is_verified:
        teacher.name = payload.name.strip()
        teacher.department_id = dep.id
        teacher.is_active = True
        db.commit()
    else:
        teacher = Teacher(
            name=payload.name.strip(),
            email=email,
            password_hash=hash_password(f"pending-{email}"),
            department_id=dep.id,
            is_verified=False,
            is_active=True,
        )
        db.add(teacher)
        db.commit()

    try:
        issue_otp(db,email,"teacher_register","teacher registration")
    except ValueError as e:
        raise HTTPException(429,str(e))
    except Exception:
        raise HTTPException(503,"Unable to send OTP")

    return {"message":"OTP sent to your .org email"}

@router.post("/teacher/register/verify", response_model=TokenOut, status_code=201)
def teacher_register_verify(payload: TeacherVerifyRequest, db: Session = Depends(get_db)):
    require_org(payload.email); email=normalize_email(str(payload.email))
    teacher=db.scalar(select(Teacher).where(Teacher.email==email))
    if not teacher: raise HTTPException(404,"Registration request not found. Request OTP again.")
    if teacher.is_verified: raise HTTPException(409,"Teacher email already registered")
    if not verify_otp(db,email,"teacher_register",payload.otp): raise HTTPException(400,"Invalid or expired OTP")
    teacher.is_verified=True; teacher.name=payload.name.strip(); db.commit(); db.refresh(teacher)
    return {"access_token":create_access_token(teacher.id,"teacher"),"user":teacher_context(db,teacher)}

@router.post("/teacher/login/request-otp")
def teacher_login_request(payload: TeacherOTPRequest, db: Session = Depends(get_db)):
    require_org(payload.email); email=normalize_email(str(payload.email)); teacher=db.scalar(select(Teacher).where(Teacher.email==email,Teacher.is_verified.is_(True),Teacher.is_active.is_(True)))
    if not teacher: raise HTTPException(404,"Teacher account not found. Register first.")
    try: issue_otp(db,email,"teacher_login","teacher login")
    except ValueError as e: raise HTTPException(429,str(e))
    except RuntimeError as e: raise HTTPException(503,str(e))
    return {"message":"Login OTP sent"}

@router.post("/teacher/login/verify", response_model=TokenOut)
def teacher_login_verify(payload: TeacherOTPVerify, db: Session = Depends(get_db)):
    email=normalize_email(str(payload.email)); require_org(email)
    if not verify_otp(db,email,"teacher_login",payload.otp): raise HTTPException(400,"Invalid or expired OTP")
    teacher=db.scalar(select(Teacher).where(Teacher.email==email,Teacher.is_verified.is_(True),Teacher.is_active.is_(True)))
    if not teacher: raise HTTPException(404,"Teacher account not found")
    return {"access_token":create_access_token(teacher.id,"teacher"),"user":teacher_context(db,teacher)}

@router.post("/student/login", response_model=TokenOut)
def student_login(payload: StudentLogin, db: Session = Depends(get_db)):
    from app.models import Student
    student=db.scalar(select(Student).where(Student.enrollment_no==payload.roll_number.strip(),Student.is_active.is_(True)))
    if not student or not verify_password(payload.password,student.password_hash): raise HTTPException(401,"Invalid enrollment number or password")
    return {"access_token":create_access_token(student.id,"student"),"user":student_context(db,student)}

@router.post("/student/reset/request-otp")
def student_reset_request(payload: StudentResetRequest, db: Session = Depends(get_db)):
    # Student OTP reset is not yet wired to a student OTP table in Stage 5.
    raise HTTPException(501,"Student password reset will be enabled with student OTP/email workflow in the next stage")

@router.post("/student/reset/verify")
def student_reset_verify(payload: StudentResetVerify, db: Session = Depends(get_db)):
    raise HTTPException(501,"Student password reset will be enabled with student OTP/email workflow in the next stage")
