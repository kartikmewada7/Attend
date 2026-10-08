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

  const host = window.location.hostname || "127.0.0.1";
  return `http://${host}:8000/api`;
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

  const [open, setOpen] = useState(false);
  const [cameraError, setCameraError] = useState("");
  const [starting, setStarting] = useState(false);

  async function openCamera() {
    if (starting) return;

    setCameraError("");
    setStarting(true);

    try {
      if (!navigator.mediaDevices?.getUserMedia) {
        throw new Error(
          "Camera API available nahi hai. HTTPS page par camera open karo."
        );
      }

      // Stop any previous stream.
      streamRef.current?.getTracks().forEach((track) => track.stop());
      streamRef.current = null;

      const stream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: {
          facingMode: {
            ideal: facingMode,
          },
          width: {
            ideal: 1280,
            min: 640,
          },
          height: {
            ideal: 720,
            min: 480,
          },
        },
      });

      streamRef.current = stream;

      const video = videoRef.current;

      if (!video) {
        throw new Error("Camera video element ready nahi hai.");
      }

      video.srcObject = stream;
      video.muted = true;
      video.playsInline = true;
      video.autoplay = true;

      // Wait until browser has metadata/video dimensions.
      await new Promise((resolve, reject) => {
        const timeout = setTimeout(() => {
          reject(new Error("Camera video start hone mein timeout ho gaya."));
        }, 10000);

        const ready = () => {
          clearTimeout(timeout);
          video.removeEventListener("loadedmetadata", ready);
          resolve();
        };

        video.addEventListener("loadedmetadata", ready);

        if (video.readyState >= 1) {
          ready();
        }
      });

      await video.play();

      setOpen(true);
    } catch (error) {
      console.error("Camera error:", error);

      streamRef.current?.getTracks().forEach((track) => track.stop());
      streamRef.current = null;

      let message =
        "Camera open nahi ho paaya. Camera permission allow karke dobara try karo.";

      if (error?.name === "NotAllowedError") {
        message =
          "Camera permission blocked hai. Browser/site settings mein Camera → Allow karo, phir page reload karo.";
      } else if (error?.name === "NotFoundError") {
        message = "Is device par camera nahi mila.";
      } else if (error?.name === "NotReadableError") {
        message =
          "Camera kisi doosre application/browser tab mein use ho raha hai. Use close karke dobara try karo.";
      } else if (error?.name === "OverconstrainedError") {
        message =
          "Camera resolution/facing-mode supported nahi hai. Dobara camera open karo.";
      } else if (error?.message) {
        message = error.message;
      }

      setCameraError(message);
      setOpen(false);
    } finally {
      setStarting(false);
    }
  }

  function closeCamera() {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;

    if (videoRef.current) {
      videoRef.current.pause();
      videoRef.current.srcObject = null;
    }

    setOpen(false);
  }

  function capturePhoto() {
    const video = videoRef.current;

    if (!video) return;

    if (!video.videoWidth || !video.videoHeight) {
      setCameraError(
        "Camera frame abhi ready nahi hai. 1–2 second wait karke dobara Capture Photo dabao."
      );
      return;
    }

    if (capturedCount >= maxPhotos) return;

    const canvas = document.createElement("canvas");

    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;

    const context = canvas.getContext("2d");

    if (!context) {
      setCameraError("Photo capture nahi ho paaya.");
      return;
    }

    context.drawImage(
      video,
      0,
      0,
      canvas.width,
      canvas.height
    );

    canvas.toBlob(
      (blob) => {
        if (!blob) {
          setCameraError("Photo create nahi ho paaya.");
          return;
        }

        const file = new File(
          [blob],
          `camera-${Date.now()}.jpg`,
          {
            type: "image/jpeg",
          }
        );

        onCapture(file);
      },
      "image/jpeg",
      0.9
    );
  }

  useEffect(() => {
    return () => {
      streamRef.current?.getTracks().forEach((track) => track.stop());
    };
  }, []);

  return (
    <div className="camera-box">

      {!open ? (
        <button
          type="button"
          className="primary"
          disabled={disabled || starting}
          onClick={openCamera}
        >
          {starting
            ? "Opening Camera..."
            : "📷 Open Live Camera"}
        </button>
      ) : (
        <>
          <div
            style={{
              width: "100%",
              maxWidth: 720,
              margin: "0 auto",
              borderRadius: 14,
              overflow: "hidden",
              background: "#0b1728",
            }}
          >
            <video
              ref={videoRef}
              autoPlay
              playsInline
              muted
              style={{
                width: "100%",
                display: "block",
                aspectRatio: "16 / 9",
                objectFit: "cover",
                background: "#0b1728",
              }}
            />
          </div>

          <div
            className="toolbar"
            style={{ marginTop: 12 }}
          >
            <button
              type="button"
              className="primary"
              disabled={
                disabled ||
                capturedCount >= maxPhotos
              }
              onClick={capturePhoto}
            >
              📸 Capture Photo
            </button>

            <button
              type="button"
              className="link-btn"
              onClick={closeCamera}
            >
              Close Camera
            </button>
          </div>
        </>
      )}

      <p className="hint">
        Captured: {capturedCount} / {maxPhotos}
      </p>

      {cameraError && (
        <Alert text={cameraError} />
      )}
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
      setResult(d); setMsg(`Done. ${d.recognized?.length||0} students recognized by Luxand.`);
    }catch(e){setMsg(e.message)}finally{setLoading(false)}
  }

  return <PageSection title="Face Attendance" subtitle="Use the live camera to capture classroom photos. Luxand.cloud identifies registered students.">
    {msg&&<Alert text={msg}/>}
    <Card title="1. Select Subject + Section">
      <select value={selected} onChange={e=>{setSelected(e.target.value);setFiles([]);setResult(null);setMsg("")}}>
        <option value="">Select subject + section</option>
        {subs.map(s=><option value={s.id} key={`${s.id}-${s.section_id}`}>{s.name} — {s.section} (Sem {s.semester})</option>)}
      </select>
    </Card>
    <Card title="2. Live Camera">
      <CameraCapture facingMode="environment" maxPhotos={5} capturedCount={files.length}
        onCapture={file=>{if(files.length<5)setFiles(prev=>[...prev,file])}}
        disabled={!selected||loading}/>
      {files.length>0&&<div style={{marginTop:12}}>
        <p className="hint">Captured classroom photos:</p>
        <div className="toolbar">{files.map((file,index)=>
          <button type="button" className="link-btn" key={`${file.name}-${index}`}
            onClick={()=>setFiles(current=>current.filter((_,i)=>i!==index))} disabled={loading}>
            Photo {index+1} ×
          </button>)}
        </div>
      </div>}
      <p className="hint">Maximum 5 photos, 5 MB each, 35 MB total.</p>
      <button className="primary" disabled={!selected||!files.length||loading} onClick={run}>
        {loading?"Recognizing with Luxand...":"Start Face Attendance"}
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
  const [file,setFile]=useState(null),[msg,setMsg]=useState(""),[loading,setLoading]=useState(false);
  const me=getUser();

  async function register(){
    if(!file)return;
    const fd=new FormData(); fd.append("file",file);
    setLoading(true); setMsg("");
    try{
      const d=await api("/student/me/face",{method:"POST",body:fd});
      setMsg(d.verification_used
        ?"Face verified and updated successfully with Luxand."
        :"Face registered successfully with Luxand.");
      setFile(null);
    }catch(e){setMsg(e.message)}finally{setLoading(false)}
  }

  return <PageSection title="Face Registration" subtitle="Use the live front camera. Re-registration is verified against your existing Luxand face.">
    {msg&&<Alert text={msg}/>}
    <Card title="Register / Update Face">
      <CameraCapture facingMode="user" maxPhotos={1} capturedCount={file?1:0}
        onCapture={captured=>{setFile(captured);setMsg("")}} disabled={loading}/>
      {file&&<div style={{marginTop:12}}>
        <p className="hint">Face capture ready for {me?.name||"student"}.</p>
        <button className="primary" disabled={loading} onClick={register}>
          {loading?"Registering with Luxand...":"Register / Update Face"}
        </button>
      </div>}
      <p className="hint">Keep your full face visible, look directly at the camera and use good lighting. Maximum 5 MB.</p>
    </Card>
  </PageSection>;
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
