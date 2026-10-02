from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.deps import require_role, current_user
from app.models import Assignment, AssignmentSubmission, Student, Subject, Section, TeacherSubjectSection

router=APIRouter(prefix="/api/assignments",tags=["Assignments"])
UPLOAD_DIR=Path("uploads/assignments"); UPLOAD_DIR.mkdir(parents=True,exist_ok=True); MAX_FILE=35*1024*1024

def allowed(db,teacher_id,subject_id,section_id): return db.scalar(select(TeacherSubjectSection.id).where(TeacherSubjectSection.teacher_id==teacher_id,TeacherSubjectSection.subject_id==subject_id,TeacherSubjectSection.section_id==section_id)) is not None

@router.get("/teacher")
def teacher_assignments(user=Depends(require_role("teacher")),db:Session=Depends(get_db)):
    rows=db.scalars(select(Assignment).where(Assignment.teacher_id==user["id"],Assignment.is_active.is_(True)).order_by(Assignment.due_at.desc())).all()
    return [{"id":a.id,"subject_id":a.subject_id,"section_id":a.section_id,"title":a.title,"description":a.description,"file_name":a.file_name,"due_date":a.due_at,"created_at":a.created_at} for a in rows]

@router.post("")
async def create_assignment(subject_id:int=Form(...),section_id:int=Form(...),title:str=Form(...),description:str|None=Form(None),due_date:str=Form(...),file:UploadFile|None=File(None),user=Depends(require_role("teacher")),db:Session=Depends(get_db)):
    if not allowed(db,user["id"],subject_id,section_id): raise HTTPException(403,"Subject/section not assigned")
    try: due=datetime.fromisoformat(due_date)
    except ValueError: raise HTTPException(400,"due_date must be ISO datetime")
    path=None; filename=None
    if file:
        data=await file.read()
        if len(data)>MAX_FILE: raise HTTPException(400,"Assignment file must be 35 MB or less")
        ext=Path(file.filename or "").suffix.lower()
        if ext not in {".pdf",".doc",".docx"}: raise HTTPException(400,"Only PDF, DOC and DOCX files are allowed")
        filename=file.filename; safe=f"assignment_{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}{ext}"; path=str(UPLOAD_DIR/safe); Path(path).write_bytes(data)
    a=Assignment(teacher_id=user["id"],subject_id=subject_id,section_id=section_id,title=title.strip(),description=description,file_path=path,file_name=filename,due_at=due); db.add(a); db.commit(); db.refresh(a)
    return {"id":a.id,"subject_id":a.subject_id,"section_id":a.section_id,"title":a.title,"file_name":a.file_name,"due_date":a.due_at}

@router.get("/student")
def student_assignments(user=Depends(require_role("student")),db:Session=Depends(get_db)):
    s=db.get(Student,user["id"])
    rows=db.execute(select(Assignment,Subject.name,Subject.code,AssignmentSubmission.status,AssignmentSubmission.submitted_at).join(Subject,Subject.id==Assignment.subject_id).outerjoin(AssignmentSubmission,(AssignmentSubmission.assignment_id==Assignment.id)&(AssignmentSubmission.student_id==s.id)).where(Assignment.section_id==s.current_section_id,Assignment.is_active.is_(True)).order_by(Assignment.due_at)).all()
    out=[]
    for a,name,code,status,submitted_at in rows:
        out.append({"id":a.id,"subject_id":a.subject_id,"subject":name,"code":code,"title":a.title,"description":a.description,"file_name":a.file_name,"due_date":a.due_at,"status":status or ("overdue" if a.due_at<datetime.utcnow() else "pending"),"submitted_at":submitted_at})
    return out

@router.get("/{assignment_id}/file")
def assignment_file(assignment_id:int,user=Depends(current_user),db:Session=Depends(get_db)):
    from fastapi.responses import FileResponse
    a=db.get(Assignment,assignment_id)
    if not a or not a.file_path or not Path(a.file_path).exists(): raise HTTPException(404,"Assignment file not found")
    return FileResponse(a.file_path,filename=a.file_name or "assignment")

@router.get("/teacher/{assignment_id}/submissions")
def assignment_submissions(assignment_id:int,user=Depends(require_role("teacher")),db:Session=Depends(get_db)):
    a=db.get(Assignment,assignment_id)
    if not a or a.teacher_id!=user["id"]: raise HTTPException(404,"Assignment not found")
    students=db.scalars(select(Student).where(Student.current_section_id==a.section_id,Student.is_active.is_(True)).order_by(Student.name)).all(); out=[]
    for s in students:
        row=db.scalar(select(AssignmentSubmission).where(AssignmentSubmission.assignment_id==assignment_id,AssignmentSubmission.student_id==s.id)); out.append({"student_id":s.id,"name":s.name,"roll_number":s.enrollment_no,"status":row.status if row else "NOT_SUBMITTED","submitted_at":row.submitted_at if row else None})
    return out

@router.patch("/{assignment_id}/student/{student_id}/status")
def update_submission_status(assignment_id:int,student_id:int,status:str,user=Depends(require_role("teacher")),db:Session=Depends(get_db)):
    if status not in {"PENDING_REVIEW","SUBMITTED","REJECTED"}: raise HTTPException(400,"Invalid assignment status")
    a=db.get(Assignment,assignment_id)
    if not a or a.teacher_id!=user["id"]: raise HTTPException(404,"Assignment not found")
    s=db.get(Student,student_id)
    if not s or s.current_section_id!=a.section_id: raise HTTPException(400,"Student is not in assignment section")
    row=db.scalar(select(AssignmentSubmission).where(AssignmentSubmission.assignment_id==assignment_id,AssignmentSubmission.student_id==student_id))
    if not row: row=AssignmentSubmission(assignment_id=assignment_id,student_id=student_id); db.add(row)
    row.status=status; row.checked_by=user["id"]; row.checked_at=datetime.utcnow(); db.commit(); return {"message":"Assignment status updated","status":row.status}
