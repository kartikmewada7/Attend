from fastapi import APIRouter
from app.redis_client import ping_redis

router = APIRouter(prefix="/api", tags=["Health"])


@router.get("/health")
def health():
    return {"status": "ok", "redis": ping_redis()}
