import os
from functools import lru_cache

import redis as redis_lib


@lru_cache(maxsize=1)
def get_redis_client() -> redis_lib.Redis | None:
    """Return a Redis client, or None when REDIS_URL is not set (Redis is optional)."""
    url = os.getenv("REDIS_URL", "").strip()
    if not url:
        return None
    # Short timeouts so an unreachable Redis can never stall a request.
    return redis_lib.from_url(url, decode_responses=True, socket_connect_timeout=2, socket_timeout=2)
