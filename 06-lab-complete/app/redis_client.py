"""
Kết nối Redis dùng chung cho rate limiter và cost guard.
"""
import redis

from app.config import settings

r: redis.Redis | None = (
    redis.Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
    )
    if settings.redis_url
    else None
)


def redis_healthy() -> bool:
    """Kiểm tra kết nối Redis cho readiness probe."""
    if r is None:
        return False
    try:
        return bool(r.ping())
    except Exception:
        return False


def close_redis() -> None:
    """Đóng Redis connection pool khi tắt app."""
    if r is not None:
        try:
            r.close()
        except Exception:
            pass
