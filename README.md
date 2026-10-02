# AttendAI — Supabase + FastAPI Backend

FastAPI backend for the attendance project using the Supabase PostgreSQL schema created in Stages 1–3.

## Database

The backend maps to these tables:

- departments
- academic_years
- semesters
- sections
- subjects
- semester_subjects
- teachers
- teacher_otps
- teacher_subject_sections
- students
- student_academic_history
- student_face_embeddings
- attendance_sessions
- attendance_session_photos
- attendance
- attendance_email_logs
- assignments
- assignment_submissions
- mst_marks

The backend does **not** run `Base.metadata.create_all()` because the schema is managed in Supabase SQL.

## Face recognition

This version implements the reference algorithm supplied for the project with `face_recognition`:

1. Student registration image → exactly one face required.
2. 128-D face encoding is stored in `student_face_embeddings.embedding` (`real[]`).
3. Teacher attendance image/group photo → all faces are detected.
4. Detection uses the `cnn` model by default.
5. A 1.5x second detection pass is used when few faces are found, improving small classroom-face recall.
6. Each detected face is encoded.
7. `face_recognition.face_distance()` finds the nearest enrolled student.
8. Matching uses tolerance `0.50`, matching the supplied reference implementation.
9. The same student is marked only once in an attendance session.
10. Database uniqueness `(session_id, student_id)` provides a second duplicate safeguard.

## Important performance note

`model="cnn"` is substantially heavier than `hog`. CPU-only laptops can take longer on classroom group photos. If the CNN detector cannot be installed or is too slow, set `FACE_MODEL=hog` as a fallback. For the requested implementation, the default remains `cnn`.

## Supabase Storage

The database remains managed by Supabase SQL. Attendance photos can also be uploaded to the private `attendance-photos` bucket through the FastAPI backend. Set `SUPABASE_STORAGE_ENABLED=true`, `SUPABASE_URL`, and the Supabase **service-role key** in `.env`. Never expose the service-role key in the React frontend.

## Installation

From the backend folder:

```powershell
& ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt
```

On Windows, `face_recognition` depends on dlib. If dlib installation fails under the current Python version, use a supported Python environment (Python 3.11 is generally the safer Windows choice for this stack) and recreate the virtual environment rather than changing the application code.

## Run

Keep the existing `.env` file. Do not commit it.

```powershell
& ".\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Face endpoints

### Student face registration

```text
POST /api/student/me/face
```

Requires a logged-in student and exactly one clear face.

### Single-photo attendance

```text
POST /api/face/recognize?subject_id=1&section_id=1
```

### Up to 5-photo attendance session

```text
POST /api/face/recognize-batch?subject_id=1&section_id=1
```

Maximums:

- 5 photos/session
- 35 MB/session
- 5 MB/photo
- 40 detected faces/photo

The selected subject must belong to the selected semester, and the teacher must have the exact teacher + subject + section assignment in `teacher_subject_sections`.
