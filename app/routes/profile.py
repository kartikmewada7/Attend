from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.deps import require_role
from app.models import Teacher, Department
from app.schemas.profile import TeacherProfileUpdate
from app.core.security import hash_password
from app.services.academic import get_or_create_department

router=APIRouter(prefix="/api/teacher",tags=["Teacher Profile"])

def profile(db,t):
    d=db.get(Department,t.department_id)
    return {"id":t.id,"name":t.name,"email":t.email,"role":"Teacher","department":d.name if d else None}

@router.get("/me")
def get_profile(user=Depends(require_role("teacher")),db:Session=Depends(get_db)):
    t=db.get(Teacher,user["id"])
    if not t: raise HTTPException(404,"Teacher not found")
    return profile(db,t)

@router.put("/me")
def update_profile(payload:TeacherProfileUpdate,user=Depends(require_role("teacher")),db:Session=Depends(get_db)):
    t=db.get(Teacher,user["id"])
    if not t: raise HTTPException(404,"Teacher not found")
    data=payload.model_dump(exclude_unset=True)
    if "email" in data:
        email=str(data.pop("email")).lower()
        if not email.endswith(".org"): raise HTTPException(400,"Teacher email must end with .org")
        if db.scalar(select(Teacher).where(Teacher.email==email,Teacher.id!=t.id)): raise HTTPException(409,"Email already in use")
        t.email=email
    if "password" in data:
        pw=data.pop("password")
        if pw and len(pw)<6: raise HTTPException(400,"Password must be at least 6 characters")
        if pw: t.password_hash=hash_password(pw)
    if "department" in data and data["department"]:
        t.department_id=get_or_create_department(db,data.pop("department")).id
    db.commit(); db.refresh(t); return profile(db,t)
