# Day 14 Lab - Mission Answers

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found (`01-localhost-vs-production/develop/app.py`)

1. **API key và DB URL hardcode** (dòng 17-18: `OPENAI_API_KEY = "sk-..."`, `DATABASE_URL = "postgresql://admin:password123@..."`). Push lên GitHub là lộ secret.
2. **Log ra secret** (dòng 34: `print(f"[DEBUG] Using key: {OPENAI_API_KEY}")`). Log aggregator sẽ lưu key dạng plain text.
3. **Dùng `print()` thay vì logging có cấu trúc** (dòng 33, 34, 38). Không có level, không có timestamp, không parse được bằng máy.
4. **Không có health check** (`/health`, `/ready`). Platform không biết khi nào agent crash để restart.
5. **Port cố định 8000** (dòng 52). Railway/Render inject cổng qua biến `PORT`, nên app không nhận được cổng của platform.
6. **`host="localhost"`** (dòng 51). Trong container chỉ nghe được từ bên trong, bên ngoài không truy cập được (cần `0.0.0.0`).
7. **`reload=True` và `DEBUG = True` cứng** (dòng 21, 53). Debug/reload không nên bật ở production.
8. **Không có xử lý shutdown** (không có lifespan/SIGTERM). Request đang chạy có thể bị cắt khi tắt.
9. **Không có config management**: `DEBUG`, `MAX_TOKENS` là hằng số trong code, đổi môi trường phải sửa code.

### Exercise 1.2: Chạy bản develop

Lệnh chạy trong WSL Ubuntu (`os.name` = `posix`), `python app.py` rồi gọi:

```
$ curl -s -X POST "http://localhost:8000/ask?question=Hello"
{"answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}

$ curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:8000/ask -H "Content-Type: application/json" -d '{"question":"Hello"}'
422          # bản develop nhận `question` qua query, không nhận JSON

$ curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health
404          # không có health check
```

Log phía server của bản develop (lộ secret):

```
[DEBUG] Got question: Hello
[DEBUG] Using key: sk-hardcoded-...   (key giả của bài mẫu, đã rút gọn; log in nguyên cả key)
[DEBUG] Response: Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận.
```

Kết luận: app chạy được nhưng chưa production-ready.

### Exercise 1.3: Comparison table

Kết quả chạy bản production (`01-localhost-vs-production/production/app.py`):

```
GET  /health -> {"status":"ok","uptime_seconds":4.6,"version":"1.0.0","environment":"development",...}
GET  /ready  -> {"ready":true}
POST /ask {"question":"Hello"} -> {"question":"Hello","answer":"Tôi là AI agent ...","model":"gpt-4o-mini"}
POST /ask {}                   -> {"detail":"question field is required"} [422]
```

| Feature | Develop | Production | Why Important? |
|---------|---------|------------|----------------|
| Config | Hardcode trong code (`OPENAI_API_KEY`, `DATABASE_URL`, `DEBUG`) | Đọc từ env qua `config.py` (`os.getenv`), `.env.example` | Secret không nằm trong repo; đổi môi trường dev/staging/prod mà không sửa code (12-Factor) |
| Secrets | Hardcode và còn in ra log | Không có secret trong code, không log secret (chỉ log `question_length`) | Tránh lộ key khi push GitHub hoặc đọc log |
| Health check | Không có (`/health` → 404) | `/health` (liveness) và `/ready` (readiness, 503 khi chưa sẵn sàng) | Platform biết khi nào restart container và khi nào được route traffic |
| Logging | `print()` | Logger, định dạng JSON (`{"time","level","msg"}`), log sự kiện có cấu trúc | Máy parse được (Loki, Datadog), có level, không lộ secret |
| Host / Port | `localhost`, cổng 8000 cứng | `0.0.0.0`, `PORT` từ env | Container và Railway/Render cần nghe mọi interface và dùng cổng được inject |
| Reload / Debug | `reload=True`, `DEBUG=True` cứng | `reload` chỉ khi `DEBUG=true` | Reload ở production gây tốn tài nguyên và rủi ro |
| Shutdown | Đột ngột, không xử lý | `lifespan` + handler SIGTERM, log "shutting down gracefully" | Request đang chạy được hoàn thành trước khi tắt, không mất dữ liệu |
| Lỗi input | FastAPI mặc định | Trả 422 kèm `detail` rõ ràng khi thiếu `question` | Client biết lỗi do đâu |

### Checkpoint 1 - tự kiểm tra

- Hardcode secret nguy hiểm vì code bị push lên Git là key lộ vĩnh viễn trong lịch sử commit.
- Health check cho platform biết app còn sống (`/health`) và sẵn sàng nhận traffic (`/ready`) để tự restart/route.
- Graceful shutdown: khi nhận SIGTERM, app xử lý xong request đang chạy rồi mới thoát.
- Ví dụ anti-pattern develop đã được production sửa: `app.py` dòng 17 hardcode key → `config.py` dòng 32 `os.getenv("AGENT_API_KEY", "")`.

## Part 2: Docker

### Exercise 2.1: Dockerfile questions (`02-docker/develop/Dockerfile`)

1. **Base image:** `python:3.11` (bản đầy đủ, nặng).
2. **Working directory:** `/app` (`WORKDIR /app`).
3. **Tại sao `COPY requirements.txt` trước:** mỗi lệnh trong Dockerfile là một layer được cache. Nếu `requirements.txt` không đổi thì layer `pip install` được dùng lại; chỉ khi sửa code (`app.py`) mới build lại từ bước copy code. Nếu `COPY . .` đứng trước thì sửa 1 dòng code cũng phải cài lại toàn bộ thư viện.
4. **CMD vs ENTRYPOINT:** `CMD` là lệnh mặc định, có thể bị ghi đè khi chạy `docker run <image> <lệnh khác>`. `ENTRYPOINT` là chương trình cố định của container, tham số truyền thêm khi `docker run` sẽ được nối vào sau nó (muốn ghi đè phải dùng `--entrypoint`). File này dùng `CMD ["python", "app.py"]`.

### Exercise 2.2: Build và run (build từ gốc repo)

```
$ docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .
$ docker run -d --name agent-dev -p 8000:8000 my-agent:develop
$ curl -s -X POST "http://localhost:8000/ask?question=What%20is%20Docker"
{"answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}
$ curl -s -i http://localhost:8000/health | head -1
HTTP/1.1 200 OK
```

### Exercise 2.3: Multi-stage build (`02-docker/production/Dockerfile`)

- **Stage 1 (`builder`):** từ `python:3.11-slim`, cài `gcc`, `libpq-dev` rồi `pip install --user` các dependency vào `/root/.local`. Stage này chỉ để build, không dùng để deploy.
- **Stage 2 (`runtime`):** từ `python:3.11-slim`, tạo user non-root `appuser`, chỉ copy `/root/.local` (các package đã cài) và source code từ builder sang, có `HEALTHCHECK`, chạy bằng `uvicorn` 2 workers.
- **Vì sao nhỏ hơn:** (1) dùng base `slim` thay vì bản đầy đủ; (2) `gcc`, `libpq-dev`, apt cache và các công cụ build ở stage 1 không được copy sang image cuối.

Kích thước đo bằng `docker images` / `docker image inspect`:

| Image | Size (docker images) | Bytes |
|-------|----------------------|-------|
| `my-agent:develop` (single-stage, `python:3.11`) | 1.67 GB | 1,667,787,976 |
| `my-agent:advanced` (multi-stage, `python:3.11-slim`) | 240 MB | 239,811,351 |

- Develop: **1.67 GB (≈ 1,590 MiB)**
- Production: **240 MB (≈ 229 MiB)**
- Difference: image production **nhỏ hơn 85.6 %** (≈ 1.43 GB), và dưới ngưỡng 500 MB của Part 6.

### Exercise 2.4: Docker Compose stack (`02-docker/production/docker-compose.yml`)

Services (project `k5-day14-docker`): `nginx`, `agent`, `redis`, `qdrant`, cùng chung network bridge `internal`.

```
Client ──► nginx (:80 trong container, publish ra host)
              │  reverse proxy + rate limit 10 req/s + security headers
              ▼
           agent (FastAPI :8000, KHÔNG publish ra host)
              ├──► redis  (:6379, cache/session/rate limit, có healthcheck)
              └──► qdrant (:6333, vector DB cho RAG, có healthcheck)
```

- Các service nói chuyện với nhau qua tên service trong network `internal` (`redis://redis:6379/0`, `http://qdrant:6333`, `agent:8000` trong `nginx.conf`).
- `depends_on` với `condition: service_healthy`: `agent` chỉ khởi động sau khi `redis` và `qdrant` healthy.
- Chỉ `nginx` mở port ra ngoài; agent không truy cập trực tiếp được từ host (gọi `localhost:8000` → không phản hồi, `000`).

Lưu ý khi chạy: cổng 80 trên máy mình đang bị **IIS (dịch vụ W3SVC) của Windows** chiếm nên `nginx` báo lỗi `ports are not available: exposing port TCP 0.0.0.0:80`. Mình không tắt IIS mà chạy lại với file override đổi cổng host sang **8081** (`ports: !override ["8081:80"]`), không sửa file trong repo. Vì vậy các lệnh test dưới đây dùng `localhost:8081` thay cho `localhost`.

```
$ docker compose -p k5-day14-docker -f docker-compose.yml -f override.yml up -d
agent   Up 20 seconds (healthy)   8000/tcp
nginx   Up 20 seconds             0.0.0.0:8081->80/tcp
qdrant  Up 31 seconds (healthy)   6333-6334/tcp
redis   Up 31 seconds (healthy)   6379/tcp

$ curl -s -i http://localhost:8081/health | head -1
HTTP/1.1 200 OK
$ curl -s http://localhost:8081/health
{"status":"ok","uptime_seconds":19.1,"version":"2.0.0","timestamp":"2026-11-25T08:37:14.359068"}
$ curl -s -X POST http://localhost:8081/ask -H "Content-Type: application/json" -d '{"question":"Explain microservices"}'
{"answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}
$ curl -s -i http://localhost:8081/health | grep -i "x-frame\|x-content\|server"
Server: nginx
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
```

Stack đã được dừng bằng `docker compose -p k5-day14-docker down`. Cách debug container: `docker logs <container>`, `docker exec -it <container> /bin/sh`.

### Checkpoint 2 - tự kiểm tra

- Số MB ở trên là số đo từ máy mình (`docker images`), không chép từ README.
- Multi-stage giảm dung lượng bằng cách bỏ toàn bộ công cụ build (gcc, apt cache) khỏi image cuối và dùng base `slim`.
- `COPY requirements.txt` phải đứng trước `COPY . .` để tận dụng cache layer cài dependency.

## Part 4: API Security

Chạy trong WSL Ubuntu (`os.name` = `posix`), token JWT đã được che (`<MASKED>`).

### Exercise 4.1: API key authentication (`04-api-gateway/develop/app.py`)

- **API key được check ở đâu?** Trong hàm dependency `verify_api_key` (dòng 39-54), gắn vào `/ask` bằng `Depends(verify_api_key)` (dòng 70). Key đúng lấy từ biến môi trường `AGENT_API_KEY` (dòng 35), header đọc bằng `APIKeyHeader(name="X-API-Key", auto_error=False)`.
- **Sai key thì sao?** Thiếu key → **401**, có key nhưng sai → **403** (bản develop tách hai trường hợp). Lưu ý: hợp đồng Part 6 yêu cầu cả thiếu lẫn sai đều **401**.
- **Rotate key thế nào?** Key không nằm trong code mà trong env: đổi giá trị `AGENT_API_KEY` rồi restart/redeploy, không cần sửa code. Muốn rotate không gián đoạn thì cho phép cùng lúc key cũ và key mới trong một khoảng thời gian rồi mới bỏ key cũ.

Chạy bằng `AGENT_API_KEY=secret-key-123 python app.py`:

```
$ curl -i -X POST http://localhost:8000/ask -H "Content-Type: application/json" -d '{"question":"Hello"}'
HTTP/1.1 401 Unauthorized
{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}

$ curl -i ... -H "X-API-Key: wrong" ...
HTTP/1.1 403 Forbidden
{"detail":"Invalid API key."}

$ curl -i ... -H "X-API-Key: secret-key-123" ...
HTTP/1.1 200 OK
{"question":"Hello","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
```

### Exercise 4.2: JWT authentication (`04-api-gateway/production/auth.py`)

Flow JWT: client gửi `POST /auth/token` với username/password → server `authenticate_user` kiểm tra, `create_token` ký JWT (HS256, bí mật `JWT_SECRET`, chứa `sub`, `role`, `iat`, `exp` 60 phút) → client gửi `Authorization: Bearer <token>` ở các request sau → `verify_token` kiểm tra chữ ký và hạn, không cần tra database (stateless).

Lấy token bằng tài khoản `student` / `demo123` (đường dẫn là `/auth/token`):

```
$ curl -i -X POST http://localhost:8000/ask -H "Content-Type: application/json" -d '{"question":"Hello"}'
HTTP/1.1 401 Unauthorized
{"detail":"Authentication required. Include: Authorization: Bearer <token>"}

$ curl -i -X POST http://localhost:8000/auth/token -d '{"username":"student","password":"bad"}'
HTTP/1.1 401 Unauthorized
{"detail":"Invalid credentials"}

$ curl -s -X POST http://localhost:8000/auth/token -H "Content-Type: application/json" -d '{"username":"student","password":"demo123"}'
{"access_token":"eyJhbGciO...<MASKED>","token_type":"bearer","expires_in_minutes":60,...}

$ curl -i ... -H "Authorization: Bearer abc.def.ghi" ...      # token sai
HTTP/1.1 403 Forbidden
{"detail":"Invalid token."}

$ curl -i ... -H "Authorization: Bearer <TOKEN>" -d '{"question":"Explain JWT"}'
HTTP/1.1 200 OK
{"question":"Explain JWT","answer":"...","usage":{"requests_remaining":9,"budget_remaining_usd":1.6e-05}}
```

### Exercise 4.3: Rate limiting (`04-api-gateway/production/rate_limiter.py`)

- **Algorithm:** **Sliding window** (`RateLimiter` dùng `deque` lưu timestamp từng request của mỗi user, loại timestamp cũ hơn 60 giây rồi đếm).
- **Limit:** user thường `rate_limiter_user = 10` request / 60 giây; admin `rate_limiter_admin = 100` request / 60 giây.
- **Bypass cho admin?** Không có bypass hoàn toàn: `app.py` dòng 141 chọn limiter theo `role` (`admin` → limiter 100 req/phút), tức admin chỉ được hạn mức cao hơn.
- **Lưu ý:** state nằm trong RAM của process (`self._windows`), nên chạy nhiều instance/worker hoặc restart thì mất; Part 6 phải chuyển sang Redis.

Vòng lặp 15 request với token `student` (đã có 1 request thành công trước đó ở bước 4.2, nên request thứ 10 của cửa sổ trở đi bị chặn):

```
call  1 -> 200   ...   call  9 -> 200
call 10 -> 429   call 11 -> 429   ...   call 15 -> 429

$ curl -i ... (request bị chặn)
HTTP/1.1 429 Too Many Requests
x-ratelimit-limit: 10
x-ratelimit-remaining: 0
x-ratelimit-reset: 1795596031
retry-after: 59
{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":59}}
```

Tài khoản `teacher` (admin) gọi 15 lần liên tiếp: `200 200 200 ... 200` (cả 15 đều 200, hạn mức 100/phút). `GET /admin/stats` với token student → **403**, với token teacher → **200**.

### Exercise 4.4: Cost guard

**Code có sẵn** trong `04-api-gateway/production/cost_guard.py` (class `CostGuard`) đã làm sẵn logic, nhưng lưu trong RAM (`self._records`), budget **$1/ngày/user** và **$10/ngày toàn hệ thống**. Hai lớp chặn: user vượt budget → **402**; tổng toàn hệ thống vượt → **503**. `check_budget` được gọi trước khi gọi LLM, `record_usage` ghi token/chi phí sau khi gọi xong. Kết quả đo được:

```
$ curl http://localhost:8000/me/usage -H "Authorization: Bearer <TOKEN>"
{"user_id":"student","date":"2026-11-25","requests":10,"input_tokens":40,"output_tokens":304,"cost_usd":0.000188,"budget_usd":1.0,"budget_remaining_usd":0.999812,"budget_used_pct":0.0}
```

**Cách tiếp cận mình sẽ dùng cho yêu cầu đề (budget $10/tháng, lưu Redis, reset đầu tháng):**

1. Mỗi user một key Redis theo tháng: `budget:{user_id}:{YYYY-MM}`. Sang tháng mới key mới được tạo nên tự "reset", không cần job dọn.
2. Trước khi gọi LLM: đọc giá trị hiện tại; nếu `hiện tại + chi phí ước tính > 10` thì trả **402**, ngược lại cộng thêm bằng `INCRBYFLOAT` (thao tác nguyên tử, an toàn khi nhiều worker/instance cùng ghi).
3. Đặt `EXPIRE` ~32 ngày để key tháng cũ tự xoá.
4. Vì state nằm trong Redis chứ không trong RAM nên đúng yêu cầu stateless: restart hoặc scale nhiều instance vẫn dùng chung một bộ đếm.

Mình **chưa sửa code** trong `04-api-gateway` (bản mẫu đã có logic RAM). Phiên bản Redis này sẽ được hiện thực trong `06-lab-complete/app/cost_guard.py` ở Part 6 (`check_budget()` → 402, `record_cost()` dùng `INCRBYFLOAT`).

**Vì sao cần cả rate limit lẫn cost guard:** rate limit bảo vệ *tốc độ* (chống spam, chống DoS, giữ tài nguyên), cost guard bảo vệ *tiền* (một người gọi chậm nhưng câu hỏi rất dài vẫn có thể đốt hết ngân sách mà không bao giờ chạm rate limit).

### Checkpoint 3 - tự kiểm tra

- Thấy được **429** bằng vòng lặp curl của chính mình (request thứ 10 trở đi).
- Phân biệt 401 (chưa xác thực), 403 (sai key/token hoặc không đủ quyền), 429 (quá tốc độ), 402 (quá ngân sách).

## Part 5: Scaling & Reliability

Mã nguồn mẫu của Part 5 đã có sẵn `/health`, `/ready`, xử lý shutdown và lưu session trong Redis; mình **đọc, chạy và kiểm chứng** chúng (không viết lại). Các output dưới đây là output thật, chạy trong WSL Ubuntu.

### Exercise 5.1: Health checks (`05-scaling-reliability/develop/app.py`)

```
$ curl -i http://localhost:8000/health
HTTP/1.1 200 OK
{"status":"ok","uptime_seconds":3.6,"version":"1.0.0","environment":"development",...,"checks":{"memory":{"status":"ok","used_percent":11.8}}}

$ curl -i http://localhost:8000/ready
HTTP/1.1 200 OK
{"ready":true,"in_flight_requests":1}
```

- **`/health` (liveness):** hỏi "process còn sống không". Nếu fail (không trả 200 hoặc timeout) thì platform **restart** container.
- **`/ready` (readiness):** hỏi "đã sẵn sàng nhận traffic chưa". Trả **503** khi đang khởi động (`_is_ready=False`), đang shutdown, hoặc (ở bản production) mất kết nối Redis. Load balancer chỉ **ngừng gửi request** vào instance đó, không restart.
- Vì sao tách hai cái: Redis chết thì instance không nên bị restart liên tục (restart không sửa được Redis), chỉ nên tạm ngừng nhận traffic. Đây cũng là lý do Part 6 yêu cầu `/health` luôn 200 còn `/ready` trả 503 khi mất Redis.
- (`in_flight_requests: 1` là chính request `/ready` đang được đếm bởi middleware.)

### Exercise 5.2: Graceful shutdown

Cách hoạt động trong code: uvicorn bắt SIGTERM và chạy phần sau `yield` của `lifespan`; ở đó `_is_ready=False` rồi vòng lặp chờ `_in_flight_requests` về 0 (tối đa 30 giây) trước khi thoát. `uvicorn.run(..., timeout_graceful_shutdown=30)`.

Thử nghiệm: gửi 3 request song song rồi gửi `kill -TERM <pid>` ngay sau đó (mỗi request mất khoảng 9 giây):

```
sent SIGTERM at 15:43:32.100
request 2 -> HTTP 200 after 9.069996s
request 1 -> HTTP 200 after 9.071183s
request 3 -> HTTP 200 after 9.071742s

--- server log ---
INFO:     Shutting down
INFO:     127.0.0.1:39170 - "POST /ask?question=LongTask2 HTTP/1.1" 200 OK
INFO:     127.0.0.1:39168 - "POST /ask?question=LongTask1 HTTP/1.1" 200 OK
INFO:     Waiting for connections to close. (CTRL+C to force quit)
INFO:     127.0.0.1:39176 - "POST /ask?question=LongTask3 HTTP/1.1" 200 OK
2026-11-25 15:43:41,209 INFO 🔄 Graceful shutdown initiated...
2026-11-25 15:43:41,209 INFO ✅ Shutdown complete
INFO:     Finished server process [1985]

server còn sống sau đó?  no (exited)
request mới sau khi tắt  -> HTTP 000 (không kết nối được)
```

Kết luận: cả 3 request đang chạy **vẫn trả 200** dù SIGTERM đã được gửi trước đó; server chỉ thoát (~9 giây sau) khi xử lý xong. Request mới sau khi tắt thì không kết nối được. Đúng hành vi graceful shutdown.

### Exercise 5.3: Stateless design (`05-scaling-reliability/production/app.py`)

- **Anti-pattern:** `conversation_history = {}` trong RAM. Khi scale ra nhiều instance mỗi instance có RAM riêng, request thứ 2 của user rơi vào instance khác sẽ "mất" lịch sử.
- **Bản production đã đúng:** `save_session` / `load_session` / `append_to_history` đọc/ghi Redis qua key `session:{session_id}` (dùng `SETEX` có TTL 3600 giây, giữ tối đa 20 message). Không có biến toàn cục nào chứa history khi `USE_REDIS=True` (chỉ có fallback `_memory_store` khi không kết nối được Redis, ghi rõ là "not scalable").
- Instance chỉ giữ `INSTANCE_ID` để biết ai phục vụ; mọi state nằm trong Redis nên instance nào cũng phục vụ được bất kỳ session nào, và có thể tắt/bật instance bất cứ lúc nào.

### Exercise 5.4: Load balancing (3 instance + Nginx + Redis)

Chạy từ `05-scaling-reliability/production/` (cổng host là **8080**, endpoint là **`POST /chat`**):

```
$ touch .env.local
$ docker compose -p k5-day14-scaling up -d --build --scale agent=3
agent  k5-day14-scaling-agent-1  Up 21 seconds (healthy)   8000/tcp
agent  k5-day14-scaling-agent-2  Up 20 seconds (healthy)   8000/tcp
agent  k5-day14-scaling-agent-3  Up 20 seconds (healthy)   8000/tcp
nginx  k5-day14-scaling-nginx-1  Up 20 seconds             0.0.0.0:8080->80/tcp
redis  k5-day14-scaling-redis-1  Up 31 seconds (healthy)    6379/tcp
```

10 request liên tiếp đến `POST /chat` (mỗi request tạo session mới), cột `served_by`:

```
req 1  instance-b3fa43      req 6  instance-7e7311
req 2  instance-3e8e10      req 7  instance-b3fa43
req 3  instance-7e7311      req 8  instance-3e8e10
req 4  instance-b3fa43      req 9  instance-7e7311
req 5  instance-3e8e10      req 10 instance-b3fa43
```

Nginx phân tán **round-robin** đều giữa 3 instance (cứ 3 request thì quay vòng). Nhờ `resolver 127.0.0.11` và `server agent:8000` trong `nginx.conf`, tên `agent` được Docker DNS phân giải ra các IP của các instance. Cấu hình `proxy_next_upstream error timeout http_503; proxy_next_upstream_tries 3;` giúp Nginx tự thử instance khác nếu một instance lỗi.

### Exercise 5.5: Test stateless

```
$ python3 test_stateless.py
Session ID: 61ee3f33-cc15-4cb5-8c7c-bc4887e83117
Request 1: [instance-3e8e10]  Q: What is Docker?
Request 2: [instance-7e7311]  Q: Why do we need containers?
Request 3: [instance-b3fa43]  Q: What is Kubernetes?
Request 4: [instance-3e8e10]  Q: How does load balancing work?
Request 5: [instance-7e7311]  Q: What is Redis used for?
Total requests: 5
Instances used: {'instance-7e7311', 'instance-3e8e10', 'instance-b3fa43'}
✅ All requests served despite different instances!
--- Conversation History ---
Total messages: 10   (5 user + 5 assistant)
✅ Session history preserved across all instances via Redis!
```

Giải thích: 5 câu hỏi cùng một `session_id` được xử lý bởi 3 instance khác nhau, nhưng lịch sử có đủ 10 message vì mọi instance đọc/ghi chung Redis.

Thử thêm (script không tự tắt instance nên mình tự làm): tạo một session, `docker stop` một instance (`k5-day14-scaling-agent-1`), rồi gửi tiếp 4 request cùng session:

```
request after kill -> HTTP 200   (x4)
history after kill: messages: 10  (1 turn trước khi kill + 4 turn sau khi kill, đủ cả hai phía)
```

Nginx thử sang instance khác khi gặp instance đã tắt, và session vẫn nguyên vẹn vì nằm trong Redis. Sau khi xong đã dọn bằng `docker compose -p k5-day14-scaling down`.

### Checkpoint 4 - tự kiểm tra

- Liveness (`/health`) khác readiness (`/ready`): một cái quyết định restart container, một cái quyết định có nhận traffic hay không.
- State trong RAM hỏng khi chạy nhiều instance vì mỗi instance có bộ nhớ riêng; request kế tiếp có thể đến instance không có state đó.
- Đã chạy `docker compose -p k5-day14-scaling up -d --build --scale agent=3`, `python3 test_stateless.py` và giải thích kết quả như trên.

## Part 3: Cloud Deployment

Theo hướng dẫn K5, Part 3 deploy **chính agent Part 6** (`06-lab-complete/`) chứ không deploy app mẫu trong `03-cloud-deployment/`.

### Nền tảng chính: Render (Exercise 3.2)

- **URL public:** https://ai-agent-rbry.onrender.com
- **Cách deploy:** đẩy code lên GitHub (nhánh `lab/day14-work` của fork), Render Dashboard → New → **Blueprint** → chọn repo, branch và Blueprint path `06-lab-complete/render.yaml`. Render tạo hai tài nguyên: web service `ai-agent` (Docker, Free) và Key Value `agent-redis` (Redis, Free), `REDIS_URL` được nối tự động bằng `fromService`, `AGENT_API_KEY` do Render tự sinh (`generateValue: true`).
- **Kiểm tra:** `GET /health` → 200, `GET /ready` → 200 (Redis nối được), `POST /ask` không key → 401, sai key → 401 (kết quả chi tiết trong [DEPLOYMENT.md](DEPLOYMENT.md)). `check_production_ready.py --public-url` xác nhận `/health` → 200.
- **Screenshot:** xem `screenshots/dashboard.png`, `running.png`, `test.png`.
- **Xem log:** Render Dashboard → service `ai-agent` → **Logs** (log là JSON một dòng nên dễ lọc).

### Railway (Exercise 3.1): không dùng được, tài khoản hết trial

Mình đã cài Railway CLI (`npm i -g @railway/cli`) và đăng nhập thành công, nhưng `railway init` trả về `Your trial has expired. Please select a plan to continue using Railway.` Mình không mua gói trả phí nên chọn Render làm nền tảng chính (RUBRIC cho phép Railway **hoặc** Render). Với nền tảng còn lại, mình so sánh hai file cấu hình (file `railway.toml` vẫn được viết đầy đủ và qua script chấm, nhưng chưa deploy thật).

### So sánh `railway.toml` và `render.yaml`

| Điểm | `railway.toml` | `render.yaml` |
|------|----------------|---------------|
| Phạm vi | Chỉ cấu hình **build + deploy của một service** | Mô tả cả **hạ tầng** (nhiều tài nguyên: web service + Key Value) trong một Blueprint |
| Định dạng | TOML (`[build]`, `[deploy]`) | YAML (`services:` là danh sách) |
| Build | `builder = "DOCKERFILE"`, `dockerfilePath` | `runtime: docker`, `dockerfilePath`, `dockerContext` |
| Health check | `healthcheckPath = "/health"` | `healthCheckPath: /health` |
| Restart | `restartPolicyType = "ON_FAILURE"` | Render tự restart khi health check fail |
| Redis | **Không khai báo trong file**: thêm bằng CLI/dashboard (`railway add --database redis`) rồi trỏ `REDIS_URL` | **Khai báo trong cùng file** (`type: keyvalue`) và nối bằng `fromService` |
| Biến môi trường / secret | **Không đặt trong file**: dùng `railway variables set ...` hoặc dashboard | Đặt ngay trong `envVars`; secret dùng `generateValue: true` hoặc `sync: false` để không lộ giá trị |
| Cách deploy | `railway up` đẩy thẳng thư mục local, không cần GitHub | Đọc từ repo GitHub: push code rồi tạo Blueprint |

Vì sao khác: Railway tách "cấu hình service" (file) khỏi "tài nguyên và biến" (CLI/dashboard), ưu tiên triển khai nhanh từ máy. Render theo hướng Infrastructure-as-Code: một file YAML mô tả toàn bộ stack nên dựng lại được tự động từ repo.

### Exercise 3.3: Cloud Run CI/CD (chỉ đọc, không deploy)

`cloudbuild.yaml` là pipeline Google Cloud Build chạy khi push lên `main`, gồm 4 bước tuần tự (`waitFor`): (1) **test**: cài dependency và chạy `pytest tests/` trong `python:3.11-slim`; (2) **build** image Docker, gắn hai tag `$COMMIT_SHA` và `latest`, dùng `--cache-from` để tận dụng layer cache; (3) **push** toàn bộ tag lên Container Registry (`gcr.io/$PROJECT_ID/ai-agent`); (4) **deploy** lên Cloud Run bằng `gcloud run deploy` (vùng `asia-southeast1`, `--min-instances=1` tránh cold start, `--max-instances=10`, 512Mi RAM, `OPENAI_API_KEY` lấy từ **Secret Manager** bằng `--set-secrets`). `service.yaml` là bản mô tả khai báo (Knative Service) của cùng dịch vụ: autoscaling 1 đến 10 instance, `containerConcurrency: 80`, giới hạn CPU/RAM, biến môi trường và secret qua `secretKeyRef`, `livenessProbe` gọi `/health` và `startupProbe` gọi `/ready`; có thể áp dụng bằng `gcloud run services replace service.yaml`.

### Checkpoint 3 - tự kiểm tra

- Có public URL hoạt động (Render).
- Biến môi trường đặt trên nền tảng (`render.yaml` `envVars` / dashboard), không ghi trong code.
- Xem log: Render → service → Logs.

---

## Part 6: Final Project

Code nằm trong `06-lab-complete/` (không sửa `check_production_ready.py`). Chạy trong WSL Ubuntu (`os.name` = `posix`) bằng Python 3.11 (cùng phiên bản với image Docker; Python 3.14 của Ubuntu không cài được `pydantic==2.9.0` đã ghim vì thiếu bản dựng sẵn).

### Kết quả `python check_production_ready.py` (chạy đầy đủ, có Docker)

```
  📋 Checklist Deliverable
     ✅ Dockerfile (multi-stage, < 500 MB)
     ✅ docker-compose.yml (agent + redis)
     ✅ .dockerignore
     ✅ Health check endpoint (GET /health)
     ✅ Readiness endpoint (GET /ready)
     ✅ API Key authentication
     ✅ Rate limiting
     ✅ Cost guard
     ✅ Config từ environment variables
     ✅ Structured logging
     ✅ Graceful shutdown
     ✅ Public URL ready (Railway / Render config)
----------------------------------------------------------------
  Result: 12/12 tiêu chí đạt · 43/43 checks passed
  🎉 PASS 12/12 — PRODUCTION READY! Deploy nào!
```

Một số số đo từ output: image **238 MB** (build 21 giây), `docker stop` **exit code 0 trong 1.0 giây**, rate limit trả 429 sau đúng 5 request (`RATE_LIMIT_PER_MINUTE=5`), cost guard trả 402 ở request thứ 1 khi budget ≈ 0, 31 dòng log JSON hợp lệ.

### Thiết kế từng thành phần (giải thích để bảo vệ bài)

| Thành phần | File | Cách làm và lý do |
|---|---|---|
| Config | `app/config.py` | Mọi giá trị đọc bằng `os.getenv` (`PORT`, `ENVIRONMENT`, `AGENT_API_KEY`, `REDIS_URL`, `RATE_LIMIT_PER_MINUTE`, `DAILY_BUDGET_USD`, `MONTHLY_BUDGET_USD`, `LOG_LEVEL`). `AGENT_API_KEY` mặc định là chuỗi rỗng: chưa cấu hình thì từ chối tất cả thay vì chấp nhận một key mặc định đoán được. `.env.example` chỉ có placeholder. |
| Redis client | `app/redis_client.py` | `redis.from_url(...)` chỉ tạo client chứ không kết nối ngay, nên app vẫn **khởi động được khi Redis chưa sẵn sàng**. Timeout ngắn (kết nối 1s, đọc 2s) để `/ready` trả 503 nhanh thay vì treo. |
| `/health` và `/ready` | `app/main.py` | `/health` (liveness) **luôn 200**, không đụng Redis: Redis chết thì restart app cũng không sửa được. `/ready` (readiness) trả **503** khi ping Redis lỗi để load balancer ngừng gửi traffic mà không restart. Đã kiểm chứng: dừng Redis → `/health` 200, `/ready` 503. |
| Log JSON | `app/main.py` | `JsonFormatter` (`json.dumps`), mỗi dòng là 1 object (`ts`, `lvl`, `logger`, `event` + field phụ); stack trace nằm trong field `exc` trên một dòng. Gắn cùng handler cho logger `uvicorn*` nên cả log của uvicorn cũng là JSON. |
| API key | `app/auth.py` | `APIKeyHeader(name="X-API-Key", auto_error=False)` rồi tự `raise HTTPException(401)`. Nếu để mặc định `auto_error=True`, FastAPI trả 403 khi thiếu header. Dùng `secrets.compare_digest` để so sánh thời gian không đổi. Thiếu **và** sai key đều 401. |
| Rate limit | `app/rate_limiter.py` | Sliding window 60 giây bằng Redis **sorted set**, theo từng API key (chỉ lưu bản băm SHA-256 của key). Dùng **script Lua** để "xóa cũ → đếm → thêm" là một thao tác nguyên tử: nếu làm bằng 3 lệnh riêng thì 2 worker có thể cùng đếm 4/5 rồi cùng thêm, cho qua 6 request. Vượt thì 429 kèm `Retry-After` (tính từ request cũ nhất trong cửa sổ). State ở Redis nên restart agent hoặc chạy nhiều worker/instance vẫn dùng chung (script chấm đã kiểm chứng). |
| Cost guard | `app/cost_guard.py` | `INCRBYFLOAT` cộng dồn chi phí vào key `cost:day:YYYY-MM-DD` và `cost:month:YYYY-MM` (có `EXPIRE`). Tên key có ngày/tháng nên sang kỳ mới tự "reset". `check_budget()` chạy **trước** khi gọi LLM (vượt → 402), `record_cost()` chạy **sau**. Chi phí tính từ số token ước lượng × bảng giá `PRICE_*_PER_1K`. |
| Lỗi Redis | cả hai file trên | Redis lỗi khi rate-limit/cost-guard → trả **503** (không cho qua mù quáng, không crash). Ghi chi phí thất bại thì chỉ bỏ qua vì LLM đã được gọi xong. |
| Xử lý lỗi | `app/main.py` | Input sai (vd `question` rỗng) → 422 kèm mô tả; lỗi không lường trước → handler trả `{"detail":"Internal server error"}` và ghi stack trace vào log, **không lộ stack trace cho client**. |
| Graceful shutdown | `app/main.py`, `Dockerfile` | Không tự đăng ký handler SIGTERM (để khỏi chặn mất handler của uvicorn). uvicorn nhận SIGTERM → ngừng nhận kết nối mới → chờ request đang chạy xong → chạy phần sau `yield` của `lifespan` (log + đóng Redis). Trong Docker, `CMD ["sh","-c","exec uvicorn ..."]` để uvicorn thay shell và là PID 1, nhờ vậy `docker stop` nhận SIGTERM và thoát 0 trong 1 giây. |
| Dockerfile | `Dockerfile` | Stage `builder` cài dependency vào `/install` (`pip install --prefix`), stage `runtime` (`python:3.11-slim`) chỉ copy `/install` + `app/` + `utils/`; user non-root `app`; `HEALTHCHECK` gọi `/health` theo `$PORT`; `COPY requirements.txt` trước source để tận dụng cache layer. |
| `.dockerignore` | `.dockerignore` | Loại `.env`, `.env.*` (giữ `.env.example`), `__pycache__`, `venv`, `.git`, `*.md`, `benchmark-observability/`, script chấm. |
| Compose | `docker-compose.yml` | `agent` (build từ Dockerfile, `env_file` với `required: false`, `REDIS_URL=redis://redis:6379/0`, `depends_on` redis với `service_healthy`) + `redis:7-alpine` có healthcheck. |
| Deploy config | `railway.toml`, `render.yaml` | Railway: `builder = "DOCKERFILE"`, `healthcheckPath = "/health"`. Render: web service Docker + `healthCheckPath: /health`, `AGENT_API_KEY` dùng `generateValue: true`, Redis khai báo là service `keyvalue` và nối qua `fromService`. Cả hai nghe cổng theo `$PORT` (qua `CMD` của Dockerfile). |

### Chạy thật bằng Docker Compose (ngoài script chấm)

`docker compose up -d --build` (có `.env` tạm với key ngẫu nhiên và `RATE_LIMIT_PER_MINUTE=5`, đã xóa sau khi test):

```
agent  Up 8 seconds (healthy)   0.0.0.0:8000->8000/tcp
redis  Up 14 seconds (healthy)  6379/tcp

health 200            ready 200
no key    401         wrong key 401
right key 200  {"question":"What is deployment?","answer":"Deployment là quá trình đưa code từ máy bạn lên server..."}
question rỗng -> 422 {"detail":[{"type":"string_too_short","loc":["body","question"],"msg":"String should have at least 1 character",...}]}

6 request liên tiếp (limit 5/phút, đã dùng 1 request ở trên):  200 200 200 200 429 429
  (429 kèm header  retry-after: 60)

Redis keys:  cost:month:2026-11   cost:day:2026-11-25   ratelimit:7bfcc2...   (key đã băm)
Dừng Redis:  /health 200 · /ready 503 {"detail":"Not ready: Redis unavailable"} · /ask 503
docker compose stop agent: mất 1.0 s, exit code 0
```

Dòng log mẫu của agent (đều là JSON một dòng):

```
{"ts": "2026-11-25T09:13:05.264Z", "lvl": "INFO", "logger": "agent", "event": "request", "method": "POST", "path": "/ask", "status": 429, "ms": 2.2}
```

### Vấn đề gặp phải và cách xử lý

- **Python 3.14 không cài được `requirements.txt`:** `pydantic-core` không có wheel cho 3.14, pip đòi biên dịch Rust và thất bại. Mình tạo venv Python 3.11 (đúng phiên bản trong Dockerfile) bằng `uv`.
- **`docker compose config` báo sai đường dẫn (`D:\mnt\d\...`):** lúc đó Docker Desktop đã bị tắt nên WSL rơi về script dự phòng gọi `docker.exe` của Windows và hiểu sai đường dẫn tuyệt đối. Mở lại Docker Desktop (WSL integration hoạt động) thì hết lỗi, không phải lỗi của file compose.
- **Log JSON của app không hiện ở Part 1:** nguyên nhân là `config.py` gọi `logging.warning(...)` trước `logging.basicConfig(...)`, nên `warning()` tự cấu hình logging mặc định (mức WARNING) và `basicConfig` sau đó không còn tác dụng. Ở Part 6 mình cấu hình logging tường minh (`setup_logging()` gắn handler JSON và đặt mức cho root logger) nên không gặp lại.

### Checkpoint 5 - tự kiểm tra

- `/health` phải trả 200 khi Redis chết còn `/ready` phải trả 503, vì hai probe phục vụ hai mục đích khác nhau: liveness quyết định restart container, readiness quyết định có nhận traffic hay không. Redis chết thì restart app vô ích (còn gây vòng lặp restart), chỉ cần tạm ngừng nhận traffic.
- Đã chạy `--static-only` sớm và chạy lại sau mỗi bước; bản đầy đủ đã `PASS 12/12` trước khi sang CP6.

<!-- Part 7 sẽ ghi trong BENCHMARK_REPORT.md -->

---

## AI log

| Lần | Hỏi gì | Nhận gì | Tự sửa / tự kiểm tra thế nào |
|-----|--------|---------|------------------------------|
| 1 | Phân tích `develop/app.py` và `production/app.py` của Part 1, chạy cả hai bản | Danh sách anti-pattern, bảng so sánh, bản nháp mục Part 1 | Chạy lại các lệnh `curl` trong WSL, các output ở trên là output thật; đối chiếu số dòng với file gốc |
| 2 | Đọc Dockerfile/compose/nginx của Part 2, build 2 image, chạy stack Compose | Trả lời Exercise 2.1-2.4, sơ đồ stack; phát hiện cổng 80 bị IIS chiếm và dùng override cổng 8081 | Số MB lấy từ `docker images` và `docker image inspect` trên máy mình; kiểm tra lại `docker compose ps` và `curl` qua Nginx |
| 3 | Đọc code Part 4 (API key, JWT, rate limiter, cost guard), chạy cả hai bản và vòng lặp curl | Giải thích Exercise 4.1-4.4, cách làm cost guard bằng Redis (chưa implement trong Part 4, để cho Part 6) | Output 401/403/200/429 lấy từ lệnh curl thật, token đã che; đối chiếu với số dòng trong code |
| 4 | Đọc code Part 5, chạy health/ready, thử SIGTERM khi đang có request, dựng stack 3 instance + Nginx + Redis, chạy `test_stateless.py`, tắt thử 1 instance | Giải thích Exercise 5.1-5.5; mã mẫu đã có sẵn health/shutdown/Redis nên chỉ đọc và kiểm chứng, không viết lại | Các output (3 request vẫn 200 sau SIGTERM, 10 request chia round-robin qua 3 instance, session còn 10 message sau khi tắt instance) lấy từ lệnh thật trong WSL |
| 5 | Viết code Part 6 (`config`, `redis_client`, `auth`, `rate_limiter` bằng Redis + Lua, `cost_guard`, `main`, `Dockerfile`, `.dockerignore`, `docker-compose.yml`, `.env.example`, `railway.toml`, `render.yaml`) và chạy `check_production_ready.py` | Code Part 6 và bảng giải thích thiết kế ở trên; AI cũng chẩn đoán 3 sự cố môi trường (Python 3.14, Docker Desktop bị tắt, thứ tự `logging.warning`/`basicConfig`) | Chạy `--static-only` rồi bản đầy đủ tới `PASS 12/12`; tự chạy thêm `docker compose up` với curl thật (401/200/422/429/402, dừng Redis → 503, `docker stop` 1.0s); xác nhận `check_production_ready.py` không bị sửa (`git diff` rỗng). **Cần tự đọc và hiểu từng file trong `06-lab-complete/app/` trước khi nộp** (Lab Coach có thể hỏi) |
| 6 | Cài Railway CLI, thử deploy; chuyển sang Render; kiểm tra URL public; viết `DEPLOYMENT.md` và mục Part 3 (so sánh `railway.toml`/`render.yaml`, pipeline Cloud Run) | Phát hiện Railway hết trial; hướng dẫn tạo Blueprint trên Render; bản nháp các tài liệu | Tự thao tác trên Render (tạo Blueprint, chọn branch `lab/day14-work`); mã HTTP `/health`, `/ready`, `/ask` 401 lấy từ `curl` thật vào URL public; `check_production_ready.py --public-url` |
| 7 | Chạy agent v1/v2 local, load test 4 mức concurrency và 3 mức `MOCK_SLOW_RATE`, eval v1/v2, sửa `KNOWLEDGE_BASE`, điền phần 1-3 của `BENCHMARK_REPORT.md` | Chạy các lệnh; chọn từ khóa/nội dung 2 tài liệu mới trong KB (JWT, HPA); bản nháp báo cáo; đề xuất chạy thêm lượt 20 giây để kiểm tra trạng thái ổn định | Mọi số trong báo cáo lấy từ file JSON trong `reports/` (đã đối chiếu); kiểm tra từ khóa mới không trùng câu nào khác trong golden dataset; không sửa `golden_dataset.jsonl`; phần nguyên nhân RPS tụt ở concurrency 100 ghi rõ là giả thuyết chưa kiểm chứng. **Cần tự đọc và hiểu báo cáo (đặc biệt vì sao p95/p99 thay avg) trước khi nộp** |
| 8 | Dựng stack Part 7 Bước 2 (Prometheus, Grafana, Jaeger, Locust, Nginx), chạy Locust headless 1 và 3 instance, thí nghiệm A-E đo thời gian alert firing, lấy trace chậm/lỗi và log theo `trace_id`, điền phần 4-7 của `BENCHMARK_REPORT.md` | Phát hiện và sửa lỗi trong Dockerfile của stack (thiếu `PYTHONUSERBASE`, agent crash nên lần đo đầu 100% lỗi 502, đã bỏ CSV đó và đo lại có chốt chặn); script đo thời gian firing; chẩn đoán lỗi script phụ (Jaeger v2 chỉ có API v3); bản nháp báo cáo | Số trong báo cáo đã đối chiếu bằng script với file CSV/JSON; ảnh chụp do **chính mình** thao tác trên Grafana/Prometheus/Jaeger; ghi rõ trong báo cáo mục 7 những gì lỗi hoặc chưa kiểm chứng (nguyên nhân RPS tụt ở concurrency 100, 82 lỗi 502, các panel chưa chụp). **Cần tự đọc và hiểu báo cáo (đặc biệt vì sao scale 3 instance không cải thiện) trước khi nộp** |
