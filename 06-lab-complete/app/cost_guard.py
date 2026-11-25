"""
Cost guard (tiêu chí 8).

  • Cộng dồn chi phí LLM (tính theo token) vào Redis, theo ngày và theo tháng.
  • Tổng chi phí vượt DAILY_BUDGET_USD (hoặc MONTHLY_BUDGET_USD) → HTTP 402.

Key Redis có ngày/tháng trong tên (cost:day:2026-11-25, cost:month:2026-11) nên sang ngày/tháng
mới tự "reset" mà không cần job dọn; EXPIRE để key cũ tự biến mất.
INCRBYFLOAT là nguyên tử → an toàn khi nhiều worker / instance cùng ghi.
"""
import time

import redis
from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

# Giá USD / 1K tokens (tham khảo gpt-4o-mini)
PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006

DAY_TTL_SECONDS = 2 * 24 * 3600       # giữ key ngày thêm 1 ngày cho tiện kiểm tra
MONTH_TTL_SECONDS = 32 * 24 * 3600    # theo gợi ý của đề (32 ngày)


def _keys() -> tuple[str, str]:
    return f"cost:day:{time.strftime('%Y-%m-%d', time.gmtime())}", \
           f"cost:month:{time.strftime('%Y-%m', time.gmtime())}"


def check_budget() -> None:
    """Gọi TRƯỚC khi gọi LLM. Hết budget → raise HTTPException(status_code=402)."""
    day_key, month_key = _keys()
    try:
        day_spent, month_spent = (float(v or 0) for v in r.mget(day_key, month_key))
    except (redis.RedisError, OSError):
        raise HTTPException(status_code=503, detail="Cost guard unavailable. Try again shortly.")

    if day_spent >= settings.daily_budget_usd:
        raise HTTPException(
            status_code=402,
            detail=f"Daily budget exceeded (${day_spent:.6f} of ${settings.daily_budget_usd:g}).",
        )
    if month_spent >= settings.monthly_budget_usd:
        raise HTTPException(
            status_code=402,
            detail=f"Monthly budget exceeded (${month_spent:.6f} of ${settings.monthly_budget_usd:g}).",
        )


def record_cost(input_tokens: int, output_tokens: int) -> float:
    """Gọi SAU khi gọi LLM. Cộng chi phí của request vào tổng, trả về chi phí request."""
    cost = (input_tokens / 1000) * PRICE_INPUT_PER_1K + (output_tokens / 1000) * PRICE_OUTPUT_PER_1K
    day_key, month_key = _keys()
    try:
        pipe = r.pipeline()
        pipe.incrbyfloat(day_key, cost)
        pipe.expire(day_key, DAY_TTL_SECONDS)
        pipe.incrbyfloat(month_key, cost)
        pipe.expire(month_key, MONTH_TTL_SECONDS)
        pipe.execute()
    except (redis.RedisError, OSError):
        # LLM đã được gọi xong, đừng làm hỏng response chỉ vì không ghi được chi phí.
        pass
    return cost
