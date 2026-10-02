from app.models.academic import Department, AcademicYear, Semester, Section, SemesterSubject
from app.models.subject import Subject
from app.models.teacher import Teacher
from app.models.otp import TeacherOTP
from app.models.teacher_subject_section import TeacherSubjectSection
from app.models.student import Student, StudentAcademicHistory
from app.models.face import StudentFaceEmbedding
from app.models.attendance import AttendanceSession, AttendanceSessionPhoto, Attendance
from app.models.email_log import AttendanceEmailLog
from app.models.assignment import Assignment, AssignmentSubmission
from app.models.marks import MSTMark

__all__ = [
    "Department", "AcademicYear", "Semester", "Section", "SemesterSubject", "Subject",
    "Teacher", "TeacherOTP", "TeacherSubjectSection",
    "Student", "StudentAcademicHistory", "StudentFaceEmbedding",
    "AttendanceSession", "AttendanceSessionPhoto", "Attendance",
    "AttendanceEmailLog", "Assignment", "AssignmentSubmission", "MSTMark",
]
