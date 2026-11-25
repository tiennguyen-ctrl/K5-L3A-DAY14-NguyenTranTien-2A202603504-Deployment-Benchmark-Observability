# ============================================================
# Production Dockerfile — multi-stage, non-root, HEALTHCHECK
#
# Build (từ thư mục 06-lab-complete):  docker build -t agent .
# Chạy:                                docker run -p 8000:8000 -e AGENT_API_KEY=... agent
# ============================================================

# ── Stage 1: builder — cài dependencies ─────────────────────
# Công cụ build và cache pip chỉ nằm ở stage này, không vào image cuối.
FROM python:3.11-slim AS builder

WORKDIR /build

# Copy requirements TRƯỚC source: sửa code không phải cài lại thư viện (tận dụng layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Stage 2: runtime — chỉ copy kết quả, chạy bằng user non-root ──
FROM python:3.11-slim AS runtime

# Không ghi .pyc, log ra stdout ngay (không buffer)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN groupadd --system app && useradd --system --gid app --no-create-home app

WORKDIR /app

# Packages đã cài ở builder → /usr/local (đã nằm trong PATH và sys.path)
COPY --from=builder /install /usr/local

COPY --chown=app:app app ./app
COPY --chown=app:app utils ./utils

USER app

EXPOSE 8000

# Liveness: gọi GET /health theo biến PORT (Railway/Render cấp cổng riêng)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os, urllib.request as u; u.urlopen('http://localhost:%s/health' % os.environ.get('PORT', '8000'), timeout=3)"

# `exec` để uvicorn thay thế shell và trở thành PID 1 → nhận SIGTERM khi `docker stop`
# và thoát êm (exit code 0). Cổng lấy từ biến PORT, mặc định 8000.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2"]
