import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.database import engine
from app.models import *  # noqa: F401,F403
from app.redis_client import ping_redis
from app.routes import (
    assignments,
    attendance,
    auth,
    face_attendance,
    health,
    marks,
    profile,
    student_portal,
    students,
)

logger = logging.getLogger("uvicorn")


@asynccontextmanager
async def lifespan(app: FastAPI):
    info = ping_redis()
    if info.get("status") == "connected":
        logger.info("Redis connected (latency: %s ms)", info.get("latency_ms"))
    else:
        logger.warning("Redis unavailable: %s — using memory cache", info.get("error"))
    yield


app = FastAPI(title="AI Face Recognition Attendance API", version="5.2.0", lifespan=lifespan)

origins = [i.strip() for i in settings.CORS_ORIGINS.split(",") if i.strip()]


# ── Critical: Guarantee CORS headers on EVERY response (even 500 crashes) ──
@app.middleware("http")
async def cors_always_middleware(request: Request, call_next):
    origin = request.headers.get("origin")

    # Fast-path for OPTIONS preflight
    if request.method == "OPTIONS" and origin:
        return JSONResponse(
            content="OK",
            headers={
                "Access-Control-Allow-Origin": origin,
                "Access-Control-Allow-Credentials": "true",
                "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
                "Access-Control-Allow-Headers": "Authorization, Content-Type, Accept",
                "Access-Control-Max-Age": "600",
            },
        )

    try:
        response = await call_next(request)
    except Exception as exc:
        logger.exception("Unhandled error on %s %s: %s", request.method, request.url, exc)
        response = JSONResponse(
            status_code=500,
            content={"detail": str(exc) or "Internal server error"},
        )

    if origin:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"

    return response


# Add standard CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["*"],
    allow_origin_regex=r"^https?://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Global exception on %s %s: %s", request.method, request.url, exc)
    origin = request.headers.get("origin", "*")
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc) or "Internal server error"},
        headers={
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Allow-Methods": "*",
            "Access-Control-Allow-Headers": "*",
        },
    )


app.include_router(health.router)
app.include_router(auth.router)
app.include_router(students.router)
app.include_router(profile.router)
app.include_router(student_portal.router)
app.include_router(attendance.router)
app.include_router(face_attendance.router)
app.include_router(assignments.router)
app.include_router(marks.router)


# ==========================================
# FRONTEND SERVING LOGIC (SPA)
# ==========================================

# Directory path jahan frontend ka build (dist) rakha hoga
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

# Check if static folder exists (Docker me build hone ke baad ye exist karega)
if os.path.exists(STATIC_DIR):
    
    # 1. Vite ke 'assets' folder (JS/CSS) ko mount karein
    assets_dir = os.path.join(STATIC_DIR, "assets")
    if os.path.exists(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    # 2. Catch-all route to serve the React/Vite SPA aur files
    @app.get("/{catchall:path}")
    async def serve_frontend(catchall: str):
        # API aur Docs ke broken requests par HTML serve karne se rokein
        if catchall.startswith("api/") or catchall in ["docs", "openapi.json", "redoc"]:
            return JSONResponse(status_code=404, content={"detail": "API Route Not Found"})
        
        # Agar koi direct file mangi gayi hai (jaise favicon.ico, logo.png)
        file_path = os.path.join(STATIC_DIR, catchall)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
            
        # Baaki sabhi frontend routes ke liye index.html return karein (React Router handle karega)
        index_path = os.path.join(STATIC_
