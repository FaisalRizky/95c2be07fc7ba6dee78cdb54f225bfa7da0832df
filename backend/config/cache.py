import time
from functools import wraps
from typing import Any, Protocol

from config.app import config


class CacheEngine(Protocol):
    def get(self, key: str) -> Any | None: ...
    def set(self, key: str, value: Any, ttl_seconds: int) -> None: ...


class MemoryTTLCache:
    def __init__(self):
        self._cache = {}

    def get(self, key: str) -> Any | None:
        if key in self._cache:
            value, timestamp, ttl = self._cache[key]
            if time.time() - timestamp < ttl:
                return value
            else:
                del self._cache[key]
        return None

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        self._cache[key] = (value, time.time(), ttl_seconds)


# // implement redis here
# class RedisCache:
#     ...


def _initialize_cache() -> CacheEngine:
    engine_type = config.CACHE_ENGINE
    if engine_type == "memory":
        print("[startup] Using MemoryTTLCache Engine")
        return MemoryTTLCache()
    else:
        raise NotImplementedError(f"Cache engine '{engine_type}' is not yet implemented. See config/cache.py.")


class CacheProvider:
    """Provides a global active cache engine context."""
    _engine: CacheEngine = _initialize_cache()

    @classmethod
    def get_engine(cls) -> CacheEngine:
        return cls._engine

    @classmethod
    def set_engine(cls, engine: CacheEngine):
        cls._engine = engine


def apply_cache(ttl_seconds: int = 3600):
    """Decorator that dynamically uses the active CacheEngine context at runtime."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Create a basic string key from the function name and arguments
            key = func.__name__ + str(args) + str(kwargs)
            engine = CacheProvider.get_engine()

            cached_val = engine.get(key)
            if cached_val is not None:
                return cached_val

            result = func(*args, **kwargs)
            engine.set(key, result, ttl_seconds)
            return result
        return wrapper
    return decorator
