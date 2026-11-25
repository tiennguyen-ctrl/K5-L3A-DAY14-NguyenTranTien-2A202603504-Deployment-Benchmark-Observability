"""
Production AI Agent — Part 6 Final Project

Chạy:   uvicorn app.main:app --workers 2
Kiểm:   python check_production_ready.py

Luồng của POST /ask:  X-API-Key (401) → rate limit (429) → cost guard (402) → LLM → ghi chi phí
"""
import json
import logging
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.auth import verify_api_key
from app.config import settings
from app.cost_guard import check_budget, record_cost
from app.rate_limiter import check_rate_limit
from app.redis_client import r, redis_healthy
from utils.mock_llm import ask as llm_ask


# ──────────────────────────────────────────────────────────
# Structured logging (tiêu chí 10): mỗi dòng log là đúng 1 JSON object
# ──────────────────────────────────────────────────────────
class JsonFormatter(logging.Formatter):
    """Biến LogRecord thành 1 dòng JSON. Field phụ truyền qua `extra={"fields": {...}}`."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
                  + f".{int(record.msecs):03d}Z",
            "lvl": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        entry.update(getattr(record, "fields", {}))
        if record.exc_info:
            # json.dumps escape xuống dòng → stack trace vẫn nằm trên 1 dòng
            entry["exc"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False, default=str)


def setup_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.log_level)
    # uvicorn dựng logger riêng (text thường) trước khi import app → ép dùng cùng handler JSON.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers = [handler]
        lg.propagate = False


setup_logging()
logger = logging.getLogger("agent")


def log(event: str, level: int = logging.INFO, **fields) -> None:
    logger.log(level, event, extra={"fields": fields})


# ──────────────────────────────────────────────────────────
# App + lifespan (tiêu chí 11 — Graceful shutdown)
# ──────────────────────────────────────────────────────────
START_TIME = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    log("startup", environment=settings.environment, port=settings.port)
    if not settings.agent_api_key:
        log("AGENT_API_KEY chưa được đặt: mọi request tới /ask sẽ bị từ chối (401)",
            level=logging.WARNING)
    yield
    # Khi nhận SIGTERM, uvicorn: ngừng nhận kết nối mới → chờ request đang chạy xong → chạy đoạn này.
    # Không tự đăng ký signal handler để không chặn mất handler của uvicorn.
    log("shutdown", uptime_seconds=round(time.time() - START_TIME, 1))
    r.close()


app = FastAPI(title="Production AI Agent", lifespan=lifespan)


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)


@app.middleware("http")
async def access_log(request: Request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    if request.url.path not in ("/health", "/ready"):     # tránh spam log của health check
        log("request", method=request.method, path=request.url.path,
            status=response.status_code, ms=round((time.perf_counter() - started) * 1000, 1))
    return response


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception):
    """Lỗi không lường trước: ghi đầy đủ vào log, nhưng chỉ trả thông báo chung cho client."""
    logger.error("unhandled_error", exc_info=exc, extra={"fields": {"path": request.url.path}})
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


# ──────────────────────────────────────────────────────────
# Health / readiness (tiêu chí 4, 5)
# ──────────────────────────────────────────────────────────
@app.get("/health")
def health():
    """Liveness: luôn 200 khi process còn chạy — KHÔNG phụ thuộc Redis (Redis chết ≠ cần restart)."""
    return {
        "status": "ok",
        "environment": settings.environment,
        "uptime_seconds": round(time.time() - START_TIME, 1),
    }


@app.get("/ready")
def ready():
    """Readiness: chỉ nhận traffic khi Redis dùng được; không thì 503 (không restart)."""
    if not redis_healthy():
        raise HTTPException(status_code=503, detail="Not ready: Redis unavailable")
    return {"status": "ready"}


# ──────────────────────────────────────────────────────────
# Agent endpoint
# ──────────────────────────────────────────────────────────
@app.post("/ask")
def ask(body: AskRequest, api_key: str = Depends(verify_api_key)):
    check_rate_limit(api_key)       # 429 khi vượt RATE_LIMIT_PER_MINUTE
    check_budget()                  # 402 khi hết ngân sách

    answer = llm_ask(body.question)

    # Ước lượng token (mock LLM không trả usage): ~2 token / từ
    input_tokens = len(body.question.split()) * 2
    output_tokens = len(answer.split()) * 2
    cost = record_cost(input_tokens, output_tokens)

    log("ask", input_tokens=input_tokens, output_tokens=output_tokens, cost_usd=round(cost, 8))
    return {"question": body.question, "answer": answer}
