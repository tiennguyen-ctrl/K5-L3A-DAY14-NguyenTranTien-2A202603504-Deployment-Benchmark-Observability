"""
Rate limiting (tiêu chí 7).

  • Mỗi API key tối đa RATE_LIMIT_PER_MINUTE request trong 60 giây (sliding window).
  • Vượt giới hạn → HTTP 429 kèm header Retry-After.
  • State lưu trong Redis (sorted set) nên mọi worker / instance dùng chung và vẫn còn
    sau khi restart agent.

Vì sao dùng script Lua: "xoá cũ → đếm → thêm mới" phải là MỘT bước nguyên tử. Nếu làm
bằng 3 lệnh riêng, hai worker cùng đếm được 4/5 rồi cùng thêm → cho qua 6 request.
Redis chạy script Lua tuần tự nên không có chuyện đó.
"""
import hashlib
import math
import time
import uuid

import redis
from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

WINDOW_SECONDS = 60

_SLIDING_WINDOW = """
local key    = KEYS[1]
local now    = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit  = tonumber(ARGV[3])
local member = ARGV[4]

redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
local count = redis.call('ZCARD', key)
if count >= limit then
  local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
  return {0, count, oldest[2]}
end
redis.call('ZADD', key, now, member)
redis.call('PEXPIRE', key, window)
return {1, count + 1, 0}
"""


def check_rate_limit(key: str) -> None:
    """Raise HTTP 429 nếu `key` vượt giới hạn; Redis lỗi → 503 (không cho qua mù quáng)."""
    # Không lưu API key thật trong Redis, chỉ lưu bản băm.
    redis_key = "ratelimit:" + hashlib.sha256(key.encode()).hexdigest()[:16]
    now_ms = int(time.time() * 1000)
    try:
        allowed, _count, oldest = r.eval(
            _SLIDING_WINDOW, 1, redis_key,
            now_ms, WINDOW_SECONDS * 1000, settings.rate_limit_per_minute,
            f"{now_ms}-{uuid.uuid4().hex[:8]}",
        )
    except (redis.RedisError, OSError):
        raise HTTPException(status_code=503, detail="Rate limiter unavailable. Try again shortly.")

    if not allowed:
        retry_after = max(1, math.ceil((float(oldest) + WINDOW_SECONDS * 1000 - now_ms) / 1000))
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded: {settings.rate_limit_per_minute} requests per minute.",
            headers={"Retry-After": str(retry_after)},
        )
