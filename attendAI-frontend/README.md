# AttendAI Frontend

Simple, responsive React frontend for the supplied AttendAI FastAPI backend.

## Run

```powershell
npm install
npm run dev
```

Open:
- PC: http://localhost:5173
- Phone on same Wi-Fi: http://YOUR-PC-IP:5173

Create `.env` from `.env.example` and set `VITE_API_BASE_URL`.

## Features

### Teacher
- `.org` OTP registration/login
- Dashboard
- Student add/delete
- Bulk student import
- Subject + section assignment
- Manual attendance
- Face attendance with up to 5 photos
- Assignments
- Assignment submission status
- MST marks
- Profile

### Student
- Enrollment + DOB login
- Face registration using camera/file picker
- Subject-wise attendance
- Assignments
- MST marks

## Responsive / zoom

The UI is mobile-first and works with browser zoom. It also includes built-in A-/A+ controls for a comfortable UI scale. The browser's normal pinch zoom is not disabled.

## Backend contract

This frontend is built against the uploaded Stage 6 FastAPI backend routes:
- `/api/auth/*`
- `/api/students/*`
- `/api/teacher/me`
- `/api/attendance/*`
- `/api/face/*`
- `/api/assignments/*`
- `/api/marks/*`
- `/api/student/*`
- `/api/health`

It does not create or modify the Supabase schema.


## Teacher registration security
Public teacher registration has been removed from the frontend.
- Teachers can only use the login OTP screen.
- Teacher accounts are expected to be created/managed by the administrator in the database/admin workflow.
- The frontend does not expose a teacher registration route or button.
- Student login and all teacher/student features remain available.
