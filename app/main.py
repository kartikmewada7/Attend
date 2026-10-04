import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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


app = FastAPI(title="AI Face Recognition Attendance API", version="5.0.0", lifespan=lifespan)

origins = [i.strip() for i in settings.CORS_ORIGINS.split(",") if i.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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


@app.get("/")
def root():
    return {"message": "Attendance Management API is running", "docs": "/docs", "health": "/api/health"}
