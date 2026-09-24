import json
import logging
from functools import lru_cache
from typing import Any

import redis

from app.core.config import settings

logger = logging.getLogger(__name__)

DEFAULT_TTL_SECONDS = 60


@lru_cache
def get_redis_client() -> redis.Redis:
    return redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)


def get_cached(key: str) -> Any | None:
    """Returns the cached value for `key`, or None on a miss, bad data, or a
    Redis error — callers should treat None as "go read the database"."""
    try:
        raw = get_redis_client().get(key)
    except redis.RedisError:
        logger.warning("cache read failed for key %s", key, exc_info=True)
        return None

    if raw is None:
        return None

    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        logger.warning("cache value for key %s was not valid JSON, ignoring", key)
        return None


def set_cached(key: str, value: Any, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> None:
    try:
        get_redis_client().set(key, json.dumps(value, default=str), ex=ttl_seconds)
    except redis.RedisError:
        logger.warning("cache write failed for key %s", key, exc_info=True)


def invalidate(key: str) -> None:
    """Deletes one exact key."""
    try:
        get_redis_client().delete(key)
    except redis.RedisError:
        logger.warning("cache invalidate failed for key %s", key, exc_info=True)


def invalidate_prefix(prefix: str) -> None:
    """Deletes every key starting with `prefix`, e.g. invalidate_prefix(f"statement:{contract_id}")
    Uses SCAN rather than KEYS, so this never blocks Redis even on a large keyspace."""
    try:
        client = get_redis_client()
        for key in client.scan_iter(match=f"{prefix}*"):
            client.delete(key)
    except redis.RedisError:
        logger.warning("cache invalidate_prefix failed for prefix %s", prefix, exc_info=True)