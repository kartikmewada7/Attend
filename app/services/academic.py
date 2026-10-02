from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import Department, Semester, Section

DEPT_CODES = {
    "CSE(AIML)": "al", "CSE": "cs", "CLOUD": "cl", "CLOUD COMPUTING": "cl",
    "FORENSIC": "ft", "CLOUD COMPUTING": "cl"
}

def get_or_create_department(db: Session, name: str):
    name = (name or "CSE").strip()
    dep = db.scalar(select(Department).where(Department.name.ilike(name)))
    if dep: return dep
    code = DEPT_CODES.get(name.upper(), name[:2].lower())[:20]
    existing = db.scalar(select(Department).where(Department.code == code))
    if existing: return existing
    dep = Department(name=name, code=code, college_code="0808")
    db.add(dep); db.flush()
    return dep

def get_semester(db: Session, semester_number: int):
    sem = db.scalar(select(Semester).where(Semester.semester_number == semester_number))
    if not sem: raise ValueError(f"Semester {semester_number} not found")
    return sem

def get_section(db: Session, department_id: int, semester_id: int, section_code: str):
    sec = db.scalar(select(Section).where(Section.department_id == department_id, Section.semester_id == semester_id, Section.section_code == section_code.strip()))
    if not sec:
        sec = Section(department_id=department_id, semester_id=semester_id, section_code=section_code.strip())
        db.add(sec); db.flush()
    return sec
