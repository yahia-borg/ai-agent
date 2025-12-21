"""
Tool result caching to reduce database queries
"""
from typing import Any, Optional, Dict
from functools import wraps
import hashlib
import json
import time
from datetime import datetime, timedelta

# In-memory cache (can be replaced with Redis in production)
_cache: Dict[str, Dict[str, Any]] = {}
_cache_ttl = 3600  # 1 hour TTL


def get_cache_key(tool_name: str, *args, **kwargs) -> str:
    """Generate cache key from tool name and arguments"""
    # Create a hash of the arguments
    key_data = {
        "tool": tool_name,
        "args": args,
        "kwargs": kwargs
    }
    key_str = json.dumps(key_data, sort_keys=True)
    return hashlib.md5(key_str.encode()).hexdigest()


def get_cached_result(tool_name: str, *args, **kwargs) -> Optional[Any]:
    """Get cached result if available and not expired"""
    cache_key = get_cache_key(tool_name, *args, **kwargs)
    
    if cache_key in _cache:
        cached_item = _cache[cache_key]
        # Check if expired
        if datetime.now() - cached_item["timestamp"] < timedelta(seconds=_cache_ttl):
            return cached_item["result"]
        else:
            # Remove expired entry
            del _cache[cache_key]
    
    return None


def set_cached_result(tool_name: str, result: Any, *args, **kwargs) -> None:
    """Cache a tool result"""
    cache_key = get_cache_key(tool_name, *args, **kwargs)
    _cache[cache_key] = {
        "result": result,
        "timestamp": datetime.now()
    }


def clear_cache() -> None:
    """Clear all cached results"""
    global _cache
    _cache = {}


def cache_tool_result(ttl: int = 3600):
    """
    Decorator to cache tool results
    
    Args:
        ttl: Time to live in seconds (default: 1 hour)
    """
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Check cache
            cached = get_cached_result(func.__name__, *args, **kwargs)
            if cached is not None:
                return cached
            
            # Execute function
            result = await func(*args, **kwargs)
            
            # Cache result
            set_cached_result(func.__name__, result, *args, **kwargs)
            
            return result
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # Check cache
            cached = get_cached_result(func.__name__, *args, **kwargs)
            if cached is not None:
                return cached
            
            # Execute function
            result = func(*args, **kwargs)
            
            # Cache result
            set_cached_result(func.__name__, result, *args, **kwargs)
            
            return result
        
        # Return appropriate wrapper based on whether function is async
        import inspect
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator

