from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.database import get_db
from app.deps import require_role
from app.core.security import hash_password
from app.models import Student, Department, Semester, Section, StudentAcademicHistory, StudentFaceEmbedding, Attendance, AssignmentSubmission
from app.services.academic import get_or_create_department, get_semester, get_section, DEPT_CODES
from app.schemas.student import StudentCreate, StudentOut

router=APIRouter(prefix="/api/students",tags=["students"])

def out(db,s):
    d=db.get(Department,s.department_id); sem=db.get(Semester,s.current_semester_id); sec=db.get(Section,s.current_section_id)
    face=db.scalar(select(StudentFaceEmbedding.id).where(StudentFaceEmbedding.student_id==s.id,StudentFaceEmbedding.is_active.is_(True))) is not None
    return {"id":s.id,"name":s.name,"roll_number":s.enrollment_no,"enrollment_no":s.enrollment_no,"email":s.email,"course":None,"dob":s.dob,"department":d.name if d else None,"year":(sem.semester_number+1)//2 if sem else None,"semester":sem.semester_number if sem else None,"section":sec.section_code if sec else None,"admission_year":s.admission_year,"batch_digit":s.batch_digit,"face_registered":face,"created_at":s.created_at}

def next_roll(db,department_id,admission_year,batch_digit):
    max_roll=db.scalar(select(func.max(Student.roll_no)).where(Student.department_id==department_id,Student.admission_year==admission_year,Student.batch_digit==batch_digit)) or 0
    return int(max_roll)+1

def enrollment(dept,year,digit,roll):
    return f"{dept.college_code}{dept.code}{year%100:02d}{digit}{roll:03d}"

@router.get("",response_model=list[StudentOut])
def list_students(db:Session=Depends(get_db),teacher=Depends(require_role("teacher"))):
    return [out(db,s) for s in db.scalars(select(Student).where(Student.is_active.is_(True)).order_by(Student.name)).all()]

@router.post("",response_model=StudentOut,status_code=201)
def create_student(payload:StudentCreate,db:Session=Depends(get_db),teacher=Depends(require_role("teacher"))):
    dep=get_or_create_department(db,payload.department or "CSE")
    sem_no=payload.semester or 1
    sem=get_semester(db,sem_no)
    sec_code=(payload.section or "S1").strip()
    sec=get_section(db,dep.id,sem.id,sec_code)
    admission_year=payload.admission_year or payload.dob.year
    digit=int(getattr(payload,"batch_digit",1) or 1)
    roll=int(payload.roll_number[-3:]) if payload.roll_number and payload.roll_number[-3:].isdigit() else next_roll(db,dep.id,admission_year,digit)
    enroll=payload.roll_number.strip() if payload.roll_number and len(payload.roll_number)>10 else enrollment(dep,admission_year,digit,roll)
    student=Student(enrollment_no=enroll,roll_no=roll,name=payload.name.strip(),email=payload.email,dob=payload.dob,password_hash=hash_password(payload.dob.strftime("%d%m%Y")),department_id=dep.id,current_semester_id=sem.id,current_section_id=sec.id,admission_year=admission_year,batch_digit=digit,is_active=True)
    db.add(student)
    try:
        db.flush(); db.add(StudentAcademicHistory(student_id=student.id,semester_id=sem.id,section_id=sec.id)); db.commit(); db.refresh(student)
    except IntegrityError:
        db.rollback(); raise HTTPException(409,"Enrollment number or email already exists")
    return out(db,student)

@router.post("/bulk",status_code=201)
def bulk_create_students(names:str,semester:int,section:str,department:str="CSE",batch_digit:int=1,admission_year:int|None=None,db:Session=Depends(get_db),teacher=Depends(require_role("teacher"))):
    dep=get_or_create_department(db,department); sem=get_semester(db,semester); sec=get_section(db,dep.id,sem.id,section); year=admission_year or datetime.utcnow().year
    clean=sorted([x.strip() for x in names.splitlines() if x.strip()],key=str.casefold); start=next_roll(db,dep.id,year,batch_digit); created=[]
    for i,name in enumerate(clean,start):
        s=Student(enrollment_no=enrollment(dep,year,batch_digit,i),roll_no=i,name=name,email=None,dob=datetime(year,1,1).date(),password_hash=hash_password("0101"+str(year)),department_id=dep.id,current_semester_id=sem.id,current_section_id=sec.id,admission_year=year,batch_digit=batch_digit,is_active=True)
        db.add(s); db.flush(); db.add(StudentAcademicHistory(student_id=s.id,semester_id=sem.id,section_id=sec.id)); created.append({"id":s.id,"name":name,"roll_no":i,"enrollment_no":s.enrollment_no})
    db.commit(); return {"count":len(created),"students":created}

@router.delete("/{student_id}")
def delete_student(student_id:int,db:Session=Depends(get_db),teacher=Depends(require_role("teacher"))):
    s=db.get(Student,student_id)
    if not s: raise HTTPException(404,"Student not found")
    s.is_active=False; db.commit(); return {"message":"Student deactivated successfully"}
