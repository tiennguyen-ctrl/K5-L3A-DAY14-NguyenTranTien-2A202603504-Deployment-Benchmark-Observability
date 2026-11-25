# Deployment Information

## Public URL

https://ai-agent-rbry.onrender.com

## Platform

**Render** (Blueprint từ `06-lab-complete/render.yaml`): web service `ai-agent` (Docker, gói Free) + Key Value `agent-redis` (Redis, gói Free). Agent được deploy là agent của Part 6 (`06-lab-complete/`).

Lưu ý: gói Free của Render ngủ sau khoảng 15 phút không có request, request đầu tiên sau đó có thể chậm 30-60 giây.

## Test Commands

### Health Check
```bash
curl https://ai-agent-rbry.onrender.com/health
# {"status":"ok","environment":"production","uptime_seconds":194.7}   -> HTTP 200
```

### Readiness (Redis nối được)
```bash
curl https://ai-agent-rbry.onrender.com/ready
# {"status":"ready"}   -> HTTP 200
```

### API Test — không có key (phải bị từ chối)
```bash
curl -i -X POST https://ai-agent-rbry.onrender.com/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Hello"}'
# HTTP 401
```

### API Test — có key
```bash
curl -X POST https://ai-agent-rbry.onrender.com/ask \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"question": "Hello"}'
# HTTP 200
```

Kết quả 4 lệnh tự kiểm (chỉ in mã HTTP):

| Lệnh | Kỳ vọng | Kết quả đo được |
|------|---------|-----------------|
| `GET /health` | 200 | 200 |
| `GET /ready` | 200 | 200 |
| `POST /ask` không có key | 401 | 401 (sai key cũng 401) |
| `POST /ask` có key | 200 | 200 |

`python check_production_ready.py --public-url https://ai-agent-rbry.onrender.com` cũng xác nhận `Public URL: GET /health → 200`.

## Environment Variables Set

Đặt trong `render.yaml` / dashboard Render, **không ghi trong code**:

| Biến | Cách đặt |
|------|----------|
| `PORT` | Render tự cấp; `CMD` trong Dockerfile nghe theo `${PORT:-8000}` |
| `ENVIRONMENT` | `production` |
| `AGENT_API_KEY` | Render tự sinh (`generateValue: true`), xem trong dashboard → Environment, không nằm trong repo |
| `REDIS_URL` | Lấy từ service `agent-redis` (`fromService` → `connectionString`) |
| `RATE_LIMIT_PER_MINUTE` | `10` |
| `DAILY_BUDGET_USD` | `1.0` |
| `MONTHLY_BUDGET_USD` | `10.0` |

## Screenshots

- [Deployment dashboard](screenshots/dashboard.png)
- [Service running](screenshots/running.png)
- [Test results](screenshots/test.png)
