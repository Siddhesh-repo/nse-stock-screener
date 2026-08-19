import logging
from redis.asyncio import Redis, ConnectionPool
from app.core.config import settings

logger = logging.getLogger(__name__)

_redis_pool: ConnectionPool | None = None
_redis_client: Redis | None = None


async def init_redis() -> Redis | None:
    """Initialize Redis connection pool asynchronously with fallback."""
    global _redis_pool, _redis_client
    try:
        _redis_pool = ConnectionPool.from_url(settings.redis_url, decode_responses=True)
        _redis_client = Redis(connection_pool=_redis_pool)
        await _redis_client.ping()
        print(f"✅ [REDIS] Successfully connected to Redis at {settings.redis_url}")
        return _redis_client
    except Exception as e:
        print(f"⚠️ [REDIS WARNING] Could not connect to Redis ({e}). Running in in-memory fallback mode.")
        _redis_client = None
        return None


async def close_redis() -> None:
    """Close Redis connection pool gracefully."""
    global _redis_pool, _redis_client
    if _redis_client:
        await _redis_client.aclose()
        _redis_client = None
    if _redis_pool:
        await _redis_pool.disconnect()
        _redis_pool = None


def get_redis() -> Redis | None:
    """Get the active Redis client instance (or None if offline)."""
    return _redis_client
