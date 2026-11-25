"""
Kết nối Redis dùng chung cho rate limiter và cost guard.

  • Đọc REDIS_URL từ config.
  • `redis.from_url` chỉ tạo client, KHÔNG kết nối ngay → app vẫn khởi động được khi Redis chưa sẵn sàng
    (kết nối thật chỉ xảy ra ở lần gọi lệnh đầu tiên).
  • Timeout ngắn để khi Redis chết thì /ready trả lời nhanh (503) thay vì treo.
  • redis_healthy() dùng cho GET /ready.
"""
import redis

from app.config import settings

r = redis.from_url(
    settings.redis_url,
    decode_responses=True,
    socket_connect_timeout=1,
    socket_timeout=2,
)


def redis_healthy() -> bool:
    """True nếu ping Redis thành công; mọi lỗi kết nối → False."""
    try:
        return bool(r.ping())
    except redis.RedisError:
        return False
    except OSError:
        return False
