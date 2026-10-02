"""Redis client with connection pooling and health checks."""
import logging
import time

from redis import ConnectionPool, Redis

from app.core.config import settings

logger = logging.getLogger(__name__)

pool = ConnectionPool.from_url(
    settings.REDIS_URL,
    decode_responses=True,
    max_connections=20,
    socket_timeout=5,
    socket_connect_timeout=5,
    retry_on_timeout=True,
)

redis_client = Redis(connection_pool=pool)


def get_redis() -> Redis:
    return redis_client


def is_redis_available() -> bool:
    try:
        return bool(redis_client.ping())
    except Exception as exc:
        logger.warning("Redis unavailable: %s", exc)
        return False


def ping_redis() -> dict:
    try:
        start = time.perf_counter()
        pong = redis_client.ping()
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        return {"status": "connected", "pong": pong, "latency_ms": latency_ms}
    except Exception as exc:
        return {"status": "disconnected", "error": str(exc)}
