import os
from functools import lru_cache

import redis as redis_lib


@lru_cache(maxsize=1)
def get_redis_client() -> redis_lib.Redis:
    url = os.getenv("REDIS_URL", "redis://localhost:6379")
    return redis_lib.from_url(url, decode_responses=True)
