from datetime import datetime
import csv
from io import BytesIO, TextIOWrapper
from fastapi import File, UploadFile, APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.deps import require_role
from app.models import MSTMark, Student, Subject, TeacherSubjectSection

router=APIRouter(prefix="/api/marks",tags=["MST Marks"])
class MarkItem(BaseModel): student_id:int; marks:float
class BulkMarks(BaseModel): subject_id:int; exam:str="MST-1"; max_marks:float=30; records:list[MarkItem]

def own_subject(db,subject_id,teacher_id):
    if not db.scalar(select(TeacherSubjectSection.id).where(TeacherSubjectSection.teacher_id==teacher_id,TeacherSubjectSection.subject_id==subject_id)): raise HTTPException(403,"Subject is not assigned to teacher")

def save(db,teacher_id,subject_id,student_id,exam,marks,max_marks):
    if marks<0 or marks>max_marks: raise HTTPException(400,"Marks must be within max marks")
    row=db.scalar(select(MSTMark).where(MSTMark.student_id==student_id,MSTMark.subject_id==subject_id,MSTMark.exam_name==exam))
    if row: row.marks=marks; row.max_marks=max_marks; row.teacher_id=teacher_id; row.updated_at=datetime.utcnow()
    else: db.add(MSTMark(student_id=student_id,subject_id=subject_id,teacher_id=teacher_id,exam_name=exam,marks=marks,max_marks=max_marks))

@router.get("/teacher/{subject_id}")
def teacher_marks(subject_id:int,exam:str="MST-1",user=Depends(require_role("teacher")),db:Session=Depends(get_db)):
    own_subject(db,subject_id,user["id"]); rows=db.execute(select(MSTMark,Student.name,Student.enrollment_no).join(Student,Student.id==MSTMark.student_id).where(MSTMark.subject_id==subject_id,MSTMark.exam_name==exam).order_by(Student.name)).all()
    return [{"student_id":m.student_id,"name":name,"roll_number":roll,"marks":float(m.marks),"max_marks":float(m.max_marks),"exam":m.exam_name} for m,name,roll in rows]

@router.post("/bulk")
def save_marks(payload:BulkMarks,user=Depends(require_role("teacher")),db:Session=Depends(get_db)):
    own_subject(db,payload.subject_id,user["id"])
    for item in payload.records: save(db,user["id"],payload.subject_id,item.student_id,payload.exam,item.marks,payload.max_marks)
    db.commit(); return {"message":"MST marks saved","count":len(payload.records)}

@router.get("/student")
def student_marks(user=Depends(require_role("student")),db:Session=Depends(get_db)):
    rows=db.execute(select(MSTMark,Subject.name,Subject.code).join(Subject,Subject.id==MSTMark.subject_id).join(Student,Student.id==MSTMark.student_id).where(MSTMark.student_id==user["id"]).order_by(Subject.name,MSTMark.exam_name)).all()
    return [{"subject":name,"code":code,"exam":m.exam_name,"marks":float(m.marks),"max_marks":float(m.max_marks)} for m,name,code in rows]

@router.post("/upload")
async def upload_marks(subject_id:int,exam:str="MST-1",max_marks:float=30,file:UploadFile=File(...),user=Depends(require_role("teacher")),db:Session=Depends(get_db)):
    own_subject(db,subject_id,user["id"])
    if not (file.filename or "").lower().endswith(".csv"): raise HTTPException(400,"Upload a CSV file with roll_number,marks columns")
    raw=await file.read()
    try: rows=list(csv.DictReader(TextIOWrapper(BytesIO(raw),encoding="utf-8-sig")))
    except Exception as e: raise HTTPException(400,f"Invalid CSV: {e}")
    count=0
    for row in rows:
        roll=(row.get("roll_number") or row.get("enrollment") or "").strip()
        if not roll: continue
        try: value=float(row.get("marks",0))
        except ValueError: raise HTTPException(400,f"Invalid marks for {roll}")
        student=db.scalar(select(Student).where(Student.enrollment_no==roll))
        if not student: continue
        save(db,user["id"],subject_id,student.id,exam,value,max_marks); count+=1
    db.commit(); return {"message":"MST CSV uploaded","count":count}
