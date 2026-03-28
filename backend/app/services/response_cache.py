"""
Redis-based cache for LLM intent classifications and responses.
Provides fast lookups to skip redundant LLM calls for repeated messages.
"""
import redis.asyncio as redis
import hashlib
import logging
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


class ResponseCache:
    """Redis cache for LLM intent classifications and responses."""

    def __init__(self):
        self._redis: Optional[redis.Redis] = None
        self.INTENT_TTL = 3600        # 1 hour for intent classifications
        self.RESPONSE_TTL = 1800      # 30 min for full responses
        self.TOOL_RESPONSE_TTL = 300  # 5 min for tool-flow responses (data changes)

    async def _get_redis(self) -> Optional[redis.Redis]:
        """Lazy-initialize Redis connection. Returns None if unavailable."""
        if self._redis is not None:
            return self._redis
        try:
            self._redis = redis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            # Verify connection
            await self._redis.ping()
            return self._redis
        except Exception as e:
            logger.warning(f"Redis unavailable, caching disabled: {e}")
            self._redis = None
            return None

    def _make_key(self, prefix: str, message: str, context: str = "") -> str:
        """Normalized cache key from message + context."""
        normalized = message.lower().strip()
        raw = f"{prefix}:{normalized}:{context}"
        return f"agent:{hashlib.sha256(raw.encode()).hexdigest()[:16]}"

    async def get_intent(self, message: str) -> Optional[str]:
        """Check if intent for this message is cached."""
        r = await self._get_redis()
        if not r:
            return None
        try:
            return await r.get(self._make_key("intent", message))
        except Exception as e:
            logger.warning(f"Redis get_intent error: {e}")
            return None

    async def set_intent(self, message: str, intent: str):
        """Cache intent classification."""
        r = await self._get_redis()
        if not r:
            return
        try:
            await r.setex(self._make_key("intent", message), self.INTENT_TTL, intent)
        except Exception as e:
            logger.warning(f"Redis set_intent error: {e}")

    async def get_response(self, message: str, context: str = "") -> Optional[str]:
        """Check if full response is cached (for chat messages only)."""
        r = await self._get_redis()
        if not r:
            return None
        try:
            return await r.get(self._make_key("response", message, context))
        except Exception as e:
            logger.warning(f"Redis get_response error: {e}")
            return None

    async def set_response(
        self,
        message: str,
        response: str,
        context: str = "",
        is_tool_flow: bool = False,
    ):
        """Cache full LLM response."""
        r = await self._get_redis()
        if not r:
            return
        try:
            ttl = self.TOOL_RESPONSE_TTL if is_tool_flow else self.RESPONSE_TTL
            await r.setex(
                self._make_key("response", message, context), ttl, response
            )
        except Exception as e:
            logger.warning(f"Redis set_response error: {e}")


# Singleton instance
_response_cache: Optional[ResponseCache] = None


def get_response_cache() -> ResponseCache:
    """Get or create ResponseCache singleton."""
    global _response_cache
    if _response_cache is None:
        _response_cache = ResponseCache()
    return _response_cache
