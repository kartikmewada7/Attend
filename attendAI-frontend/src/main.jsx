import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import "./styles.css";

const API = (() => {
  const configured = (import.meta.env.VITE_API_BASE_URL || "").trim();

  if (configured) {
    const base = configured.replace(/\/+$/, "");
    return base.endsWith("/api") ? base : `${base}/api`;
  }

  // When running inside the Docker image the SPA is served from the
  // same origin as the API, so we can use the current origin directly.
  // Only fall back to http://host:8000 for local Vite dev-server mode.
  if (window.location.port === "5173" || window.location.port === "5174") {
    const host = window.location.hostname || "127.0.0.1";
    return `http://${host}:8000/api`;
  }

  return `${window.location.origin}/api`;
})();

async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  const token = localStorage.getItem("attendai_token");
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (!(options.body instanceof FormData) && options.body !== undefined) {
    headers.set("Content-Type", "application/json");
  }
  const res = await fetch(`${API}${path}`, { ...options, headers });
  const type = res.headers.get("content-type") || "";
  const data = type.includes("application/json") ? await res.json() : await res.text();
  if (!res.ok) {
    const msg = data?.detail || data?.message || data || `Request failed (${res.status})`;
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return data;
}

function saveAuth(data) {
  localStorage.setItem("attendai_token", data.access_token);
  localStorage.setItem("attendai_user", JSON.stringify(data.user));
}
function getUser() {
  try { return JSON.parse(localStorage.getItem("attendai_user") || "null"); } catch { return null; }
}
function logout() {
  localStorage.removeItem("attendai_token");
  localStorage.removeItem("attendai_user");
  window.location.href = "/login";
}

function App() {
  const [scale, setScale] = useState(() => Number(localStorage.getItem("attendai_scale") || 1));
  useEffect(() => {
    document.documentElement.style.setProperty("--ui-scale", scale);
    localStorage.setItem("attendai_scale", String(scale));
  }, [scale]);

  return (
    <div className="app-shell">
      <TopBar scale={scale} setScale={setScale} />
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/teacher/*" element={<Protected role="Teacher"><TeacherApp /></Protected>} />
        <Route path="/student/*" element={<Protected role="Student"><StudentApp /></Protected>} />
        <Route path="*" element={<Navigate to={getUser() ? (getUser().role === "Teacher" ? "/teacher" : "/student") : "/login"} replace />} />
      </Routes>
    </div>
  );
}

function TopBar({ scale, setScale }) {
  return (
    <header className="topbar">
      <div className="brand">
        <div className="brand-mark">AI</div>
        <div>
          <strong>AttendAI</strong>
          <span>Smart Attendance Management</span>
        </div>
      </div>
      <div className="zoom-tools" aria-label="UI zoom">
        <button onClick={() => setScale(Math.max(.85, +(scale - .05).toFixed(2)))} title="Decrease text size">A−</button>
        <span>{Math.round(scale * 100)}%</span>
        <button onClick={() => setScale(Math.min(1.35, +(scale + .05).toFixed(2)))} title="Increase text size">A+</button>
        <button className="reset-zoom" onClick={() => setScale(1)} title="Reset UI size">Reset</button>
      </div>
    </header>
  );
}

function Protected({ role, children }) {
  const user = getUser();
  if (!user) return <Navigate to="/login" replace />;
  if (user.role !== role) return <Navigate to={user.role === "Teacher" ? "/teacher" : "/student"} replace />;
  return children;
}

function Login() {
  const nav = useNavigate();
  const [role, setRole] = useState("teacher");
  const [email, setEmail] = useState("");
  const [otp, setOtp] = useState("");
  const [roll, setRoll] = useState("");
  const [password, setPassword] = useState("");
  const [sent, setSent] = useState(false);
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState("");

  async function sendTeacherOtp() {
    setLoading(true); setMsg("");
    try {
      await api("/auth/teacher/login/request-otp", { method: "POST", body: JSON.stringify({ email }) });
      setSent(true); setMsg("OTP sent to your .org email.");
    } catch (e) {
      setMsg(e?.message || "Backend se connection nahi ho raha. Check that FastAPI is running on port 8000.");
    } finally { setLoading(false); }
  }
  async function teacherLogin() {
    setLoading(true); setMsg("");
    try {
      const data = await api("/auth/teacher/login/verify", { method: "POST", body: JSON.stringify({ email, otp }) });
      saveAuth(data); nav("/teacher");
    } catch (e) { setMsg(e.message); } finally { setLoading(false); }
  }
  async function studentLogin() {
    setLoading(true); setMsg("");
    try {
      const data = await api("/auth/student/login", { method: "POST", body: JSON.stringify({ roll_number: roll, password }) });
      saveAuth(data); nav("/student");
    } catch (e) { setMsg(e.message); } finally { setLoading(false); }
  }

  return (
    <main className="auth-page">
      <section className="auth-card">
        <div className="hero-icon">✓</div>
        <h1>Welcome to AttendAI</h1>
        <p className="muted">Simple attendance, assignments, MST marks and face recognition.</p>
        <div className="segmented">
          <button className={role === "teacher" ? "active" : ""} onClick={() => {setRole("teacher"); setSent(false); setMsg("");}}>Teacher</button>
          <button className={role === "student" ? "active" : ""} onClick={() => {setRole("student"); setSent(false); setMsg("");}}>Student</button>
        </div>

        {role === "teacher" ? (
          <>
            <label>Teacher .org Email</label>
            <input value={email} onChange={e => setEmail(e.target.value)} placeholder="teacher@college.org" type="email" />
            {!sent ? (
              <button className="primary wide" disabled={loading || !email} onClick={sendTeacherOtp}>{loading ? "Sending..." : "Send Login OTP"}</button>
            ) : (
              <>
                <label>OTP</label>
                <input value={otp} onChange={e => setOtp(e.target.value)} placeholder="6 digit OTP" inputMode="numeric" />
                <button className="primary wide" disabled={loading || !otp} onClick={teacherLogin}>{loading ? "Checking..." : "Login"}</button>
                <button className="link-btn" onClick={sendTeacherOtp}>Resend OTP</button>
              </>
            )}
            <p className="hint admin-note">Teacher accounts are created by the administrator. Use your registered .org email to receive a login OTP.</p>
          </>
        ) : (
          <>
            <label>Enrollment / Roll Number</label>
            <input value={roll} onChange={e => setRoll(e.target.value)} placeholder="0808cl241093" />
            <label>Password</label>
            <input value={password} onChange={e => setPassword(e.target.value)} placeholder="DOB: DDMMYYYY" type="password" />
            <button className="primary wide" disabled={loading || !roll || !password} onClick={studentLogin}>{loading ? "Logging in..." : "Student Login"}</button>
            <p className="hint">Default student password is DOB in DDMMYYYY.</p>
          </>
        )}
        {msg && <Alert text={msg} />}
      </section>
    </main>
  );
}

function Layout({ user, title, children, links }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="workspace">
      <aside className={open ? "sidebar open" : "sidebar"}>
        <div className="side-user">
          <div className="avatar">{(user?.name || "?").slice(0,1).toUpperCase()}</div>
          <div><strong>{user?.name}</strong><span>{user?.role}</span></div>
        </div>
        <nav>
          {links.map(l => <a key={l.href} href={l.href} onClick={() => setOpen(false)}>{l.icon} {l.label}</a>)}
        </nav>
        <button className="logout" onClick={logout}>Logout</button>
      </aside>
      {open && <button className="overlay" onClick={() => setOpen(false)} aria-label="Close menu" />}
      <main className="main-content">
        <div className="mobile-head">
          <button className="menu-btn" onClick={() => setOpen(true)}>☰</button>
          <div><strong>{title}</strong><span>{user?.department || "AttendAI"}</span></div>
        </div>
        <div className="page-title">
          <div><h1>{title}</h1><p>Manage your attendance work from one simple screen.</p></div>
          <div className="status-dot">● Online</div>
        </div>
        {children}
      </main>
    </div>
  );
}

function TeacherApp() {
  const user = getUser();
  return (
    <Layout user={user} title="Teacher Dashboard" links={[
      {href:"/teacher",label:"Dashboard",icon:"⌂"},
      {href:"/teacher/students",label:"Students",icon:"👥"},
      {href:"/teacher/subjects",label:"Subjects",icon:"📚"},
      {href:"/teacher/attendance",label:"Attendance",icon:"✓"},
      {href:"/teacher/face",label:"Face Attendance",icon:"📷"},
      {href:"/teacher/assignments",label:"Assignments",icon:"📝"},
      {href:"/teacher/marks",label:"MST Marks",icon:"🎯"},
      {href:"/teacher/profile",label:"Profile",icon:"⚙"}
    ]}>
      <Routes>
        <Route index element={<TeacherHome />} />
        <Route path="students" element={<StudentsPage />} />
        <Route path="subjects" element={<SubjectsPage />} />
        <Route path="attendance" element={<ManualAttendance />} />
        <Route path="face" element={<FaceAttendance />} />
        <Route path="assignments" element={<TeacherAssignments />} />
        <Route path="marks" element={<TeacherMarks />} />
        <Route path="profile" element={<Profile />} />
        <Route path="*" element={<TeacherHome />} />
      </Routes>
    </Layout>
  );
}

function TeacherHome() {
  return <section className="grid-cards">
    <QuickCard icon="👥" title="Students" text="Add students, import a whole batch and manage records." to="/teacher/students" />
    <QuickCard icon="📚" title="Subjects" text="Assign a subject to your semester section." to="/teacher/subjects" />
    <QuickCard icon="✓" title="Attendance" text="Mark attendance manually or use face recognition." to="/teacher/attendance" />
    <QuickCard icon="📝" title="Assignments" text="Create assignments and check submission status." to="/teacher/assignments" />
    <QuickCard icon="🎯" title="MST Marks" text="Enter marks for the selected subject." to="/teacher/marks" />
    <QuickCard icon="⚙" title="Profile" text="Update your teacher profile." to="/teacher/profile" />
  </section>;
}

function QuickCard({icon,title,text,to}) {
  return <a className="quick-card" href={to}><div className="big-icon">{icon}</div><div><h3>{title}</h3><p>{text}</p></div><span>→</span></a>;
}

function StudentsPage() {
  const [students,setStudents]=useState([]); const [form,setForm]=useState({name:"",email:"",dob:"",department:"CSE",semester:1,section:"S1",admission_year:new Date().getFullYear(),batch_digit:1});
  const [bulk,setBulk]=useState(""); const [bulkInfo,setBulkInfo]=useState({semester:1,section:"S1",department:"CSE",batch_digit:1,admission_year:new Date().getFullYear()}); const [msg,setMsg]=useState("");
  const load=()=>api("/students").then(setStudents).catch(e=>setMsg(e.message));
  useEffect(load,[]);
  async function add(){try{await api("/students",{method:"POST",body:JSON.stringify({...form,semester:Number(form.semester),admission_year:Number(form.admission_year),batch_digit:Number(form.batch_digit)})});setMsg("Student added. Default password is DOB.");setForm({...form,name:"",email:"",dob:""});load();}catch(e){setMsg(e.message)}}
  async function bulkAdd(){try{const qs=new URLSearchParams({semester:bulkInfo.semester,section:bulkInfo.section,department:bulkInfo.department,batch_digit:bulkInfo.batch_digit,admission_year:bulkInfo.admission_year}); const body=new URLSearchParams({names:bulk}); const d=await api(`/students/bulk?${qs}`,{method:"POST",body});setMsg(`${d.count} students imported and sorted A-Z.`);setBulk("");load();}catch(e){setMsg(e.message)}}
  async function del(id){if(!confirm("Deactivate this student?"))return;try{await api(`/students/${id}`,{method:"DELETE"});load();}catch(e){setMsg(e.message)}}
  return <PageSection title="Students" subtitle="Add one student or paste many names at once.">
    {msg&&<Alert text={msg}/>}
    <div className="two-col">
      <Card title="Add Student">
        <div className="form-grid">
          <Field label="Name"><input value={form.name} onChange={e=>setForm({...form,name:e.target.value})}/></Field>
          <Field label="Email"><input value={form.email||""} onChange={e=>setForm({...form,email:e.target.value})} type="email"/></Field>
          <Field label="DOB"><input value={form.dob} onChange={e=>setForm({...form,dob:e.target.value})} type="date"/></Field>
          <Field label="Department"><input value={form.department} onChange={e=>setForm({...form,department:e.target.value})}/></Field>
          <Field label="Semester"><input value={form.semester} onChange={e=>setForm({...form,semester:e.target.value})} type="number" min="1" max="8"/></Field>
          <Field label="Section"><input value={form.section} onChange={e=>setForm({...form,section:e.target.value})}/></Field>
          <Field label="Admission Year"><input value={form.admission_year} onChange={e=>setForm({...form,admission_year:e.target.value})} type="number"/></Field>
          <Field label="Batch Digit (0-9)"><input value={form.batch_digit} onChange={e=>setForm({...form,batch_digit:e.target.value})} type="number" min="0" max="9"/></Field>
        </div>
        <button className="primary" onClick={add}>Add Student</button>
      </Card>
      <Card title="Bulk Import">
        <p className="hint">Paste one student name per line. Names are sorted A-Z and roll numbers are assigned automatically.</p>
        <textarea rows="8" value={bulk} onChange={e=>setBulk(e.target.value)} placeholder={"Aarav Sharma\nAnanya Patel\n..."} />
        <div className="form-grid compact">
          <Field label="Semester"><input type="number" min="1" max="8" value={bulkInfo.semester} onChange={e=>setBulkInfo({...bulkInfo,semester:e.target.value})}/></Field>
          <Field label="Section"><input value={bulkInfo.section} onChange={e=>setBulkInfo({...bulkInfo,section:e.target.value})}/></Field>
          <Field label="Department"><input value={bulkInfo.department} onChange={e=>setBulkInfo({...bulkInfo,department:e.target.value})}/></Field>
          <Field label="Batch Digit"><input type="number" min="0" max="9" value={bulkInfo.batch_digit} onChange={e=>setBulkInfo({...bulkInfo,batch_digit:e.target.value})}/></Field>
        </div>
        <button className="secondary" onClick={bulkAdd}>Import Batch</button>
      </Card>
    </div>
    <Card title={`Student List (${students.length})`}>
      <DataTable headers={["Name","Enrollment","Semester","Section","Face","Action"]} rows={students.map(s=>[
        s.name,s.enrollment_no,s.semester||"-",s.section||"-",s.face_registered?"✓ Registered":"Not registered",
        <button className="danger small" onClick={()=>del(s.id)}>Delete</button>
      ])}/>
    </Card>
  </PageSection>;
}

function SubjectsPage() {
  const [form,setForm]=useState({name:"",code:"",department:"CSE",semester:1,section:"S1"}); const [list,setList]=useState([]); const [msg,setMsg]=useState("");
  async function load(){try{setList(await api("/attendance/subjects"))}catch(e){setMsg(e.message)}}
  useEffect(()=>{load()},[]);
  async function add(){try{await api(`/attendance/subjects?${new URLSearchParams({name:form.name,code:form.code,department:form.department,semester:form.semester,section:form.section})}`,{method:"POST"});setMsg("Subject created and assigned.");setForm({...form,name:"",code:""});load()}catch(e){setMsg(e.message)}}
  return <PageSection title="Subjects" subtitle="Create a subject and assign it to your semester + section.">
    {msg&&<Alert text={msg}/>}
    <Card title="Add Subject">
      <div className="form-grid">
        <Field label="Subject Name"><input value={form.name} onChange={e=>setForm({...form,name:e.target.value})}/></Field>
        <Field label="Subject Code"><input value={form.code} onChange={e=>setForm({...form,code:e.target.value})}/></Field>
        <Field label="Department"><input value={form.department} onChange={e=>setForm({...form,department:e.target.value})}/></Field>
        <Field label="Semester"><input type="number" min="1" max="8" value={form.semester} onChange={e=>setForm({...form,semester:e.target.value})}/></Field>
        <Field label="Section"><input value={form.section} onChange={e=>setForm({...form,section:e.target.value})}/></Field>
      </div>
      <button className="primary" onClick={add}>Create & Assign</button>
    </Card>
    <Card title="My Assigned Subjects">
      <DataTable headers={["Subject","Code","Semester","Section"]} rows={list.map(x=>[x.name,x.code,x.semester,x.section])}/>
    </Card>
  </PageSection>;
}

function ManualAttendance() {
  const [subs,setSubs]=useState([]),[selected,setSelected]=useState(""),[date,setDate]=useState(new Date().toISOString().slice(0,10)),[students,setStudents]=useState([]),[states,setStates]=useState({}),[msg,setMsg]=useState("");
  useEffect(()=>{api("/attendance/subjects").then(setSubs).catch(e=>setMsg(e.message))},[]);
  async function load(){if(!selected)return;const s=subs.find(x=>String(x.id)===String(selected));if(!s)return;try{const st=await api(`/attendance/students?subject_id=${s.id}&section_id=${s.section_id}`);const rec=await api(`/attendance/records?subject_id=${s.id}&section_id=${s.section_id}&attendance_date=${date}`);const map={};st.forEach(x=>map[x.id]=rec.find(r=>r.student_id===x.id)?.status==="present");setStudents(st);setStates(map)}catch(e){setMsg(e.message)}}
  useEffect(()=>{load()},[selected,date]);
  async function save(){try{const s=subs.find(x=>String(x.id)===String(selected));const records=students.map(x=>({student_id:x.id,status:states[x.id]?"present":"absent"}));const d=await api("/attendance/bulk",{method:"POST",body:JSON.stringify({subject_id:s.id,section_id:s.section_id,attendance_date:date,records})});setMsg(`${d.count} attendance records saved.`)}catch(e){setMsg(e.message)}}
  return <PageSection title="Manual Attendance" subtitle="Select subject, section and date, then mark Present.">
    {msg&&<Alert text={msg}/>}
    <Toolbar>
      <select value={selected} onChange={e=>setSelected(e.target.value)}><option value="">Select subject + section</option>{subs.map(s=><option value={s.id} key={`${s.id}-${s.section_id}`}>{s.name} — {s.section} (Sem {s.semester})</option>)}</select>
      <input type="date" value={date} onChange={e=>setDate(e.target.value)}/>
      <button className="primary" disabled={!students.length} onClick={save}>Save Attendance</button>
    </Toolbar>
    <Card title={`Students (${students.length})`}>
      <DataTable headers={["Name","Enrollment","Present"]} rows={students.map(s=>[
        s.name,s.enrollment_no,<label className="switch"><input type="checkbox" checked={!!states[s.id]} onChange={e=>setStates({...states,[s.id]:e.target.checked})}/><span></span></label>
      ])}/>
    </Card>
  </PageSection>;
}

function CameraCapture({
  facingMode = "environment",
  maxPhotos = 1,
  onCapture,
  capturedCount = 0,
  disabled = false,
}) {
  const videoRef = useRef(null);
  const streamRef = useRef(null);

  const [cameraOpen, setCameraOpen] = useState(false);
  const [cameraError, setCameraError] = useState("");
  const [cameraStatus, setCameraStatus] = useState("Camera closed");
  const [starting, setStarting] = useState(false);

  async function getMediaStream() {
    // 1. Try high-definition with desired facingMode
    try {
      return await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: {
          facingMode: { ideal: facingMode },
          width: { ideal: 1280 },
          height: { ideal: 720 },
        },
      });
    } catch (e1) {
      console.warn("High-res getUserMedia failed, trying facingMode:", e1);
    }

    // 2. Try simple facingMode
    try {
      return await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: { facingMode: { ideal: facingMode } },
      });
    } catch (e2) {
      console.warn("FacingMode getUserMedia failed, trying basic video:", e2);
    }

    // 3. Fallback to any available video camera
    return await navigator.mediaDevices.getUserMedia({
      audio: false,
      video: true,
    });
  }

  async function startCamera() {
    if (starting) return;

    setCameraError("");
    setStarting(true);
    setCameraStatus("Starting camera...");

    try {
      if (!navigator.mediaDevices?.getUserMedia) {
        throw new Error(
          "Camera API not available in this browser. Please open over HTTPS."
        );
      }

      // Stop previous stream
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((t) => t.stop());
        streamRef.current = null;
      }

      const stream = await getMediaStream();
      const tracks = stream.getVideoTracks();

      if (!tracks.length) {
        throw new Error("No video track received from camera.");
      }

      const track = tracks[0];
      track.enabled = true;
      streamRef.current = stream;

      const video = videoRef.current;
      if (!video) {
        throw new Error("Video element is not available in DOM.");
      }

      video.srcObject = stream;
      video.muted = true;
      video.defaultMuted = true;
      video.playsInline = true;
      video.setAttribute("playsinline", "true");
      video.setAttribute("webkit-playsinline", "true");
      video.setAttribute("muted", "true");

      setCameraOpen(true);
      setCameraStatus("Camera active");

      const playVideo = async () => {
        try {
          await video.play();
          setCameraStatus("Camera is live");
        } catch (playErr) {
          console.warn("Autoplay was prevented or delayed:", playErr);
          setCameraStatus("Camera ready. Click Capture to take photo.");
        }
      };

      if (video.readyState >= 2) {
        playVideo();
      } else {
        video.onloadedmetadata = () => playVideo();
        video.oncanplay = () => playVideo();
      }

      track.onended = () => {
        setCameraOpen(false);
        setCameraStatus("Camera stopped");
      };
    } catch (error) {
      console.error("Camera error:", error);

      if (streamRef.current) {
        streamRef.current.getTracks().forEach((t) => t.stop());
        streamRef.current = null;
      }

      setCameraOpen(false);

      if (error?.name === "NotAllowedError") {
        setCameraError(
          "Camera permission blocked. Please allow camera in browser address bar settings."
        );
      } else if (error?.name === "NotFoundError") {
        setCameraError("No camera device found on this system.");
      } else if (error?.name === "NotReadableError") {
        setCameraError(
          "Camera is being used by another application. Please close other camera apps and retry."
        );
      } else {
        setCameraError(
          error?.message || "Failed to start camera."
        );
      }
      setCameraStatus("Camera failed");
    } finally {
      setStarting(false);
    }
  }

  function stopCamera() {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }

    const video = videoRef.current;
    if (video) {
      video.pause();
      video.srcObject = null;
    }

    setCameraOpen(false);
    setCameraStatus("Camera closed");
    setCameraError("");
  }

  function capturePhoto() {
    const video = videoRef.current;
    if (!video) {
      setCameraError("Video element is not available.");
      return;
    }

    const width = video.videoWidth || 640;
    const height = video.videoHeight || 480;

    if (capturedCount >= maxPhotos) return;

    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;

    const ctx = canvas.getContext("2d");
    if (!ctx) {
      setCameraError("Could not create photo canvas.");
      return;
    }

    // Mirror horizontal if user-facing camera
    if (facingMode === "user") {
      ctx.translate(canvas.width, 0);
      ctx.scale(-1, 1);
    }

    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

    canvas.toBlob(
      (blob) => {
        if (!blob) {
          setCameraError("Failed to encode photo.");
          return;
        }

        const file = new File(
          [blob],
          `face-${Date.now()}.jpg`,
          { type: "image/jpeg" }
        );
        onCapture(file);
      },
      "image/jpeg",
      0.92
    );
  }

  useEffect(() => {
    return () => {
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((t) => t.stop());
        streamRef.current = null;
      }
    };
  }, []);

  return (
    <div className="camera-box">
      <div
        style={{
          width: "100%",
          maxWidth: "800px",
          margin: "0 auto",
          background: "#0b1728",
          borderRadius: "14px",
          overflow: "hidden",
          position: "relative",
          minHeight: "340px",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <video
          ref={videoRef}
          autoPlay
          muted
          playsInline
          style={{
            width: "100%",
            height: "auto",
            maxHeight: "480px",
            display: cameraOpen ? "block" : "none",
            objectFit: "contain",
            transform: facingMode === "user" ? "scaleX(-1)" : "none",
          }}
        />

        {!cameraOpen && (
          <div
            style={{
              padding: "40px 20px",
              textAlign: "center",
              color: "#94a3b8",
            }}
          >
            <div style={{ fontSize: "40px", marginBottom: "8px" }}>📷</div>
            <p style={{ margin: 0, fontSize: "16px", color: "#f8fafc" }}>
              Live Camera Preview
            </p>
            <p style={{ margin: "4px 0 0", fontSize: "13px" }}>
              Click "Open Live Camera" or "Upload Photo" below
            </p>
          </div>
        )}
      </div>

      <div
        style={{
          marginTop: "14px",
          display: "flex",
          gap: "10px",
          alignItems: "center",
          flexWrap: "wrap",
        }}
      >
        {!cameraOpen ? (
          <button
            type="button"
            className="primary"
            disabled={disabled || starting}
            onClick={startCamera}
          >
            {starting ? "Starting Camera..." : "📷 Open Live Camera"}
          </button>
        ) : (
          <>
            <button
              type="button"
              className="primary"
              disabled={disabled || capturedCount >= maxPhotos}
              onClick={capturePhoto}
            >
              📸 Capture Photo
            </button>
            <button
              type="button"
              className="link-btn"
              onClick={stopCamera}
            >
              Close Camera
            </button>
          </>
        )}

        <label
          className="link-btn"
          style={{
            cursor: "pointer",
            display: "inline-flex",
            alignItems: "center",
            gap: "4px",
            border: "1px solid #cbd5e1",
            padding: "8px 14px",
            borderRadius: "6px",
          }}
        >
          📁 {maxPhotos > 1 ? "Upload Photos" : "Choose Photo from Device"}
          <input
            type="file"
            accept="image/*"
            multiple={maxPhotos > 1}
            capture={facingMode === "user" ? "user" : "environment"}
            style={{ display: "none" }}
            onChange={(e) => {
              const files = Array.from(e.target.files || []);
              files.slice(0, maxPhotos - capturedCount).forEach(onCapture);
              e.target.value = "";
            }}
            disabled={disabled || capturedCount >= maxPhotos}
          />
        </label>
      </div>

      <p className="hint" style={{ marginTop: "8px" }}>
        {cameraStatus} · Captured: {capturedCount} / {maxPhotos}
      </p>

      {cameraError && <Alert text={cameraError} />}
    </div>
  );
}

function FaceAttendance() {
  const [subs,setSubs]=useState([]),[selected,setSelected]=useState(""),[files,setFiles]=useState([]),[msg,setMsg]=useState(""),[result,setResult]=useState(null),[loading,setLoading]=useState(false);

  useEffect(()=>{api("/attendance/subjects").then(setSubs).catch(e=>setMsg(e.message))},[]);

  async function run(){
    if(!selected||!files.length)return;
    const s=subs.find(x=>String(x.id)===String(selected)); if(!s)return;
    const fd=new FormData(); files.forEach(f=>fd.append("files",f));
    setLoading(true); setMsg(""); setResult(null);
    try{
      const d=await api(`/face/recognize-batch?subject_id=${s.id}&section_id=${s.section_id}`,{method:"POST",body:fd});
      setResult(d);
      setMsg(d.message || `Done. ${d.recognized?.length||0} students recognized and marked present.`);
    }catch(e){setMsg(e.message)}finally{setLoading(false)}
  }

  return <PageSection title="Face Attendance" subtitle="Use live camera or upload classroom photos. Facial recognition identifies registered students.">
    {msg&&<Alert text={msg}/>}
    <Card title="1. Select Subject + Section">
      <select value={selected} onChange={e=>{setSelected(e.target.value);setFiles([]);setResult(null);setMsg("")}}>
        <option value="">Select subject + section</option>
        {subs.map(s=><option value={s.id} key={`${s.id}-${s.section_id}`}>{s.name} — {s.section} (Sem {s.semester})</option>)}
      </select>
    </Card>
    <Card title="2. Classroom Photos (Camera or Upload)">
      <CameraCapture facingMode="environment" maxPhotos={5} capturedCount={files.length}
        onCapture={file=>{if(files.length<5)setFiles(prev=>[...prev,file])}}
        disabled={!selected||loading}/>
      {files.length>0&&<div style={{marginTop:12}}>
        <p className="hint">Selected classroom photos ({files.length}/5):</p>
        <div className="toolbar" style={{display:"flex", gap:8, flexWrap:"wrap"}}>
          {files.map((file,index)=>
            <button type="button" className="link-btn" key={`${file.name}-${index}`}
              onClick={()=>setFiles(current=>current.filter((_,i)=>i!==index))} disabled={loading}
              style={{background:"#f1f5f9", padding:"6px 12px", borderRadius:6}}>
              📷 Photo {index+1} ✕
            </button>)}
        </div>
      </div>}
      <p className="hint">Maximum 5 photos, 5 MB each. Wide angles with good lighting recommended.</p>
      <button className="primary" disabled={!selected||!files.length||loading} onClick={run}>
        {loading?"Recognizing faces...":"Start Face Attendance"}
      </button>
    </Card>
    {result&&<Card title="Recognition Result">
      <div className="stats-row">
        <Stat value={result.recognized?.length||0} label="Recognized"/>
        <Stat value={result.total_faces_detected||0} label="Faces detected"/>
        <Stat value={result.photos||0} label="Photos"/>
      </div>
      <DataTable headers={["Student","Enrollment","Confidence","Attendance"]}
        rows={(result.recognized||[]).map(x=>[
          x.name,x.enrollment_no,
          x.confidence!=null?`${(Number(x.confidence)*100).toFixed(1)}%`:"-",
          x.attendance||"marked"
        ])}/>
    </Card>}
  </PageSection>;
}

function TeacherAssignments() {
  const [subs,setSubs]=useState([]),[list,setList]=useState([]),[form,setForm]=useState({subject_id:"",section_id:"",title:"",description:"",due_date:""}),[file,setFile]=useState(null),[msg,setMsg]=useState("");
  async function load(){try{setSubs(await api("/attendance/subjects"));setList(await api("/assignments/teacher"))}catch(e){setMsg(e.message)}}
  useEffect(()=>{load()},[]);
  async function create(){try{const fd=new FormData();fd.append("subject_id",form.subject_id);fd.append("section_id",form.section_id);fd.append("title",form.title);fd.append("description",form.description);fd.append("due_date",form.due_date);if(file)fd.append("file",file);await api("/assignments",{method:"POST",body:fd});setMsg("Assignment created.");setForm({...form,title:"",description:"",due_date:""});setFile(null);load()}catch(e){setMsg(e.message)}}
  return <PageSection title="Assignments" subtitle="Create PDF/DOC/DOCX assignments with a due date.">
    {msg&&<Alert text={msg}/>}
    <Card title="Create Assignment">
      <div className="form-grid">
        <Field label="Subject"><select value={form.subject_id} onChange={e=>{const s=subs.find(x=>String(x.id)===e.target.value);setForm({...form,subject_id:e.target.value,section_id:s?.section_id||""})}}><option value="">Select</option>{subs.map(s=><option key={`${s.id}-${s.section_id}`} value={s.id}>{s.name} — {s.section}</option>)}</select></Field>
        <Field label="Section"><input value={form.section_id} readOnly/></Field>
        <Field label="Title"><input value={form.title} onChange={e=>setForm({...form,title:e.target.value})}/></Field>
        <Field label="Due Date"><input type="datetime-local" value={form.due_date} onChange={e=>setForm({...form,due_date:e.target.value})}/></Field>
      </div>
      <Field label="Description"><textarea rows="4" value={form.description} onChange={e=>setForm({...form,description:e.target.value})}/></Field>
      <Field label="File (optional)"><input type="file" accept=".pdf,.doc,.docx" onChange={e=>setFile(e.target.files?.[0]||null)}/></Field>
      <button className="primary" onClick={create}>Create Assignment</button>
    </Card>
    <Card title="Created Assignments"><DataTable headers={["Title","Due","File"]} rows={list.map(x=>[x.title,new Date(x.due_date).toLocaleString(),x.file_name||"—"])}/></Card>
  </PageSection>;
}

function TeacherMarks() {
  const [subs,setSubs]=useState([]),[selected,setSelected]=useState(""),[exam,setExam]=useState("MST-1"),[max,setMax]=useState(30),[students,setStudents]=useState([]),[marks,setMarks]=useState({}),[msg,setMsg]=useState("");
  useEffect(()=>{api("/attendance/subjects").then(setSubs).catch(e=>setMsg(e.message))},[]);
  async function load(){const s=subs.find(x=>String(x.id)===String(selected));if(!s)return;try{const st=await api(`/attendance/students?subject_id=${s.id}&section_id=${s.section_id}`);const old=await api(`/marks/teacher/${s.id}?exam=${encodeURIComponent(exam)}`);const map={};old.forEach(x=>map[x.student_id]=x.marks);st.forEach(x=>{if(map[x.id]===undefined)map[x.id]="";});setStudents(st);setMarks(map)}catch(e){setMsg(e.message)}}
  useEffect(()=>{load()},[selected,exam]);
  async function save(){const s=subs.find(x=>String(x.id)===String(selected));try{const records=students.map(x=>({student_id:x.id,marks:Number(marks[x.id]||0)}));await api("/marks/bulk",{method:"POST",body:JSON.stringify({subject_id:s.id,exam,max_marks:Number(max),records})});setMsg("MST marks saved.")}catch(e){setMsg(e.message)}}
  return <PageSection title="MST Marks" subtitle="Enter subject-wise marks for your class.">
    {msg&&<Alert text={msg}/>}
    <Toolbar><select value={selected} onChange={e=>setSelected(e.target.value)}><option value="">Select subject</option>{subs.map(s=><option value={s.id} key={`${s.id}-${s.section_id}`}>{s.name} — {s.section}</option>)}</select><input value={exam} onChange={e=>setExam(e.target.value)} placeholder="MST-1"/><input type="number" value={max} onChange={e=>setMax(e.target.value)} placeholder="Max marks"/><button className="primary" disabled={!students.length} onClick={save}>Save Marks</button></Toolbar>
    <Card title="Marks"><DataTable headers={["Name","Enrollment","Marks"]} rows={students.map(s=>[s.name,s.enrollment_no,<input className="mini-input" type="number" min="0" max={max} value={marks[s.id]??""} onChange={e=>setMarks({...marks,[s.id]:e.target.value})}/>])}/></Card>
  </PageSection>;
}

function Profile() {
  const [data,setData]=useState(null),[form,setForm]=useState({}),[msg,setMsg]=useState("");
  useEffect(()=>{api("/teacher/me").then(x=>{setData(x);setForm(x)}).catch(e=>setMsg(e.message))},[]);
  async function save(){try{const d=await api("/teacher/me",{method:"PUT",body:JSON.stringify({name:form.name,email:form.email,department:form.department})});setData(d);setMsg("Profile updated.")}catch(e){setMsg(e.message)}}
  return <PageSection title="Profile" subtitle="Update your teacher information.">{msg&&<Alert text={msg}/>}<Card title="Teacher Profile">{data&&<div className="form-grid"><Field label="Name"><input value={form.name||""} onChange={e=>setForm({...form,name:e.target.value})}/></Field><Field label=".org Email"><input value={form.email||""} onChange={e=>setForm({...form,email:e.target.value})}/></Field><Field label="Department"><input value={form.department||""} onChange={e=>setForm({...form,department:e.target.value})}/></Field></div>}<button className="primary" onClick={save}>Save Profile</button></Card></PageSection>;
}

function StudentApp() {
  const user=getUser();
  return <Layout user={user} title="Student Dashboard" links={[
    {href:"/student",label:"Dashboard",icon:"⌂"},
    {href:"/student/attendance",label:"Attendance",icon:"✓"},
    {href:"/student/face",label:"Face Registration",icon:"📷"},
    {href:"/student/assignments",label:"Assignments",icon:"📝"},
    {href:"/student/marks",label:"MST Marks",icon:"🎯"}
  ]}>
    <Routes>
      <Route index element={<StudentHome />} />
      <Route path="attendance" element={<StudentAttendance />} />
      <Route path="face" element={<StudentFace />} />
      <Route path="assignments" element={<StudentAssignments />} />
      <Route path="marks" element={<StudentMarks />} />
      <Route path="*" element={<StudentHome />} />
    </Routes>
  </Layout>;
}

function StudentHome() {
  const [me,setMe]=useState(null); useEffect(()=>{api("/student/me").then(setMe)},[]);
  return <PageSection title="Student Dashboard" subtitle="Your academic information at a glance.">
    <div className="profile-banner"><div className="avatar large">{(me?.name||"?").slice(0,1)}</div><div><h2>{me?.name||"Loading..."}</h2><p>{me?.enrollment_no||""}</p><p>{me?.department||""} · Semester {me?.semester||"-"} · Section {me?.section||"-"}</p></div></div>
    <div className="grid-cards">
      <QuickCard icon="✓" title="Attendance" text="See subject-wise attendance percentage." to="/student/attendance"/>
      <QuickCard icon="📷" title="Face Registration" text={me?.face_registered?"Face is registered. You can update it.":"Register your face using camera/photo."} to="/student/face"/>
      <QuickCard icon="📝" title="Assignments" text="See pending and due assignments." to="/student/assignments"/>
      <QuickCard icon="🎯" title="MST Marks" text="See subject-wise MST marks." to="/student/marks"/>
    </div>
  </PageSection>;
}

function StudentAttendance() {
  const [data,setData]=useState([]),[msg,setMsg]=useState(""); useEffect(()=>{api("/student/me/attendance").then(setData).catch(e=>setMsg(e.message))},[]);
  return <PageSection title="My Attendance" subtitle="Present classes and percentage for each subject.">{msg&&<Alert text={msg}/>}<Card title="Subject-wise Attendance"><DataTable headers={["Subject","Code","Present","Total","Percentage"]} rows={data.map(x=>[x.subject,x.code,x.present,x.total,<strong>{x.percentage}%</strong>])}/></Card></PageSection>;
}
function StudentFace() {
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [msg, setMsg] = useState("");
  const [isSuccess, setIsSuccess] = useState(false);
  const [loading, setLoading] = useState(false);
  const [profile, setProfile] = useState(null);
  const me = getUser();

  function loadProfile() {
    api("/student/me")
      .then((data) => setProfile(data))
      .catch((e) => console.warn("Failed to load student profile:", e));
  }

  useEffect(() => {
    loadProfile();
  }, []);

  function onCaptured(captured) {
    setFile(captured);
    if (preview) URL.revokeObjectURL(preview);
    setPreview(URL.createObjectURL(captured));
    setMsg("");
    setIsSuccess(false);
  }

  function clearPhoto() {
    if (preview) URL.revokeObjectURL(preview);
    setFile(null);
    setPreview(null);
    setMsg("");
    setIsSuccess(false);
  }

  async function register() {
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    setLoading(true);
    setMsg("");
    setIsSuccess(false);

    try {
      const d = await api("/student/me/face", { method: "POST", body: fd });
      setMsg(d.message || "Face registered successfully.");
      setIsSuccess(true);
      loadProfile();
    } catch (e) {
      setMsg(e.message || "Failed to register face.");
      setIsSuccess(false);
    } finally {
      setLoading(false);
    }
  }

  return (
    <PageSection
      title="Face Registration"
      subtitle="Use the live camera or upload a clear photo. Face recognition connects with Luxand Cloud & AttendAI Engine."
    >
      {profile && (
        <div
          style={{
            marginBottom: "16px",
            padding: "12px 18px",
            background: profile.face_registered ? "#ecfdf5" : "#fffbeb",
            border: `1px solid ${profile.face_registered ? "#a7f3d0" : "#fde68a"}`,
            borderRadius: "10px",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            flexWrap: "wrap",
            gap: "10px",
          }}
        >
          <div>
            <strong style={{ color: profile.face_registered ? "#065f46" : "#92400e", fontSize: "15px" }}>
              {profile.face_registered ? "✓ Face is REGISTERED & ACTIVE" : "⚠️ Face is NOT registered yet"}
            </strong>
            <p style={{ margin: "2px 0 0", fontSize: "13px", color: "#64748b" }}>
              {profile.face_registered
                ? "Your face is saved in the attendance database. You can submit a new photo anytime to update it."
                : "Please capture your face or upload a clear photo to register."}
            </p>
          </div>
          <span
            style={{
              fontSize: "12px",
              fontWeight: 700,
              padding: "4px 12px",
              borderRadius: "20px",
              background: profile.face_registered ? "#10b981" : "#f59e0b",
              color: "#fff",
            }}
          >
            {profile.face_registered ? "Active" : "Not Registered"}
          </span>
        </div>
      )}

      {msg && !preview && <Alert text={msg} />}

      <Card title="Register / Update Face">
        <CameraCapture
          facingMode="user"
          maxPhotos={1}
          capturedCount={file ? 1 : 0}
          onCapture={onCaptured}
          disabled={loading}
        />

        {preview && (
          <div
            style={{
              marginTop: "16px",
              padding: "16px",
              background: "#f1f5f9",
              borderRadius: "12px",
              textAlign: "center",
            }}
          >
            <p className="hint" style={{ fontWeight: 600, color: "#1e293b", marginBottom: "10px" }}>
              Captured Face Preview for {me?.name || "Student"}:
            </p>
            <img
              src={preview}
              alt="Face preview"
              style={{
                width: "180px",
                height: "180px",
                objectFit: "cover",
                borderRadius: "12px",
                border: `3px solid ${isSuccess ? "#10b981" : "#3b82f6"}`,
                display: "inline-block",
                boxShadow: "0 4px 6px -1px rgba(0, 0, 0, 0.1)",
              }}
            />

            {msg && (
              <div
                style={{
                  margin: "14px auto 6px",
                  maxWidth: "460px",
                  padding: "10px 16px",
                  borderRadius: "8px",
                  background: isSuccess ? "#ecfdf5" : "#fef2f2",
                  border: `1px solid ${isSuccess ? "#10b981" : "#ef4444"}`,
                  color: isSuccess ? "#065f46" : "#991b1b",
                  fontSize: "14px",
                  fontWeight: 600,
                  textAlign: "center",
                }}
              >
                {isSuccess ? "✓ " : "✕ "} {msg}
              </div>
            )}

            <div
              style={{
                display: "flex",
                gap: "12px",
                justifyContent: "center",
                marginTop: "14px",
              }}
            >
              <button
                type="button"
                className="primary"
                disabled={loading}
                onClick={register}
              >
                {loading ? "Registering Face..." : isSuccess ? "✓ Face Saved (Click to Re-submit)" : "✓ Submit & Register Face"}
              </button>
              <button
                type="button"
                className="link-btn"
                disabled={loading}
                onClick={clearPhoto}
              >
                ✕ Retake / Change Photo
              </button>
            </div>
          </div>
        )}

        <p className="hint" style={{ marginTop: "12px" }}>
          Keep your full face centered, look directly at the camera with good lighting. Supported formats: JPG, PNG (Max 5 MB).
        </p>
      </Card>
    </PageSection>
  );
}

function StudentAssignments() {
  const [list,setList]=useState([]),[msg,setMsg]=useState(""); useEffect(()=>{api("/assignments/student").then(setList).catch(e=>setMsg(e.message))},[]);
  return <PageSection title="My Assignments" subtitle="Pending, overdue and submitted assignments.">{msg&&<Alert text={msg}/>}<Card title={`Assignments (${list.length})`}><DataTable headers={["Subject","Title","Due","Status"]} rows={list.map(x=>[x.subject,x.title,new Date(x.due_date).toLocaleString(),<span className={`pill ${String(x.status).toLowerCase()}`}>{x.status}</span>])}/></Card></PageSection>;
}
function StudentMarks() {
  const [list,setList]=useState([]),[msg,setMsg]=useState(""); useEffect(()=>{api("/marks/student").then(setList).catch(e=>setMsg(e.message))},[]);
  return <PageSection title="My MST Marks" subtitle="Your subject-wise exam marks.">{msg&&<Alert text={msg}/>}<Card title={`Marks (${list.length})`}><DataTable headers={["Subject","Code","Exam","Marks"]} rows={list.map(x=>[x.subject,x.code,x.exam,`${x.marks} / ${x.max_marks}`])}/></Card></PageSection>;
}

function PageSection({title,subtitle,children}) { return <section><div className="section-head"><div><h2>{title}</h2><p>{subtitle}</p></div></div>{children}</section>; }
function Card({title,children}) { return <div className="card"><div className="card-head"><h3>{title}</h3></div>{children}</div>; }
function Field({label,children}) { return <label className="field"><span>{label}</span>{children}</label>; }
function Alert({text}) { return <div className="alert">{text}</div>; }
function Toolbar({children}) { return <div className="toolbar">{children}</div>; }
function Stat({value,label}) { return <div className="stat"><strong>{value}</strong><span>{label}</span></div>; }
function DataTable({headers,rows}) {
  if (!rows.length) return <div className="empty">No records found.</div>;
  return <div className="table-wrap"><table><thead><tr>{headers.map(h=><th key={h}>{h}</th>)}</tr></thead><tbody>{rows.map((r,i)=><tr key={i}>{r.map((c,j)=><td key={j}>{c}</td>)}</tr>)}</tbody></table></div>;
}

createRoot(document.getElementById("root")).render(<BrowserRouter><App /></BrowserRouter>);
