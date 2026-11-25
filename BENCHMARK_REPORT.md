# Benchmark & Observability Report — Day 14

> Mọi con số trong báo cáo lấy từ các file JSON/CSV trong `reports/` và `benchmark-results/`, không ước lượng.
> Tất cả các phần (1-7) đã điền. Log thô của các thí nghiệm nằm trong `reports/alert_experiments.log` và `reports/phase_c_traces.log`.

**Họ tên:** Nguyễn Trần Tiến (MSSV 2A202603504)
**Ngày chạy:** 2026-11-25
**Môi trường:** Windows 11 Home, Intel Core i5-12450H (12 luồng), WSL2 Ubuntu được cấp 7.8 GB RAM, Python 3.11.18, Docker Desktop 4.100 (WSL2). Agent (1 tiến trình uvicorn) và công cụ sinh tải `load_test.py` chạy **chung một máy** nên kết quả ở mức concurrency cao có thể bị ảnh hưởng bởi chính máy sinh tải.

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | < 500 ms | Khi tải thấp (concurrency ≤ 10) p95 đo được ≈ 221 ms, nên 500 ms để dư khoảng gấp đôi cho dao động mà người dùng vẫn thấy câu trả lời gần như tức thì. Chọn p95 vì avg che giấu tail (xem 2.2). |
| Error rate `/ask` | < 2 % | Mock LLM cố ý lỗi ~1 % (`MOCK_ERROR_RATE=0.01`); đo được 0.67-1.60 % ở các lượt chạy. Ngưỡng 2 % chấp nhận được nhiễu nền đó nhưng bắt được khi lỗi thật tăng. |
| Accuracy trên golden dataset | ≥ 95 % | Với 23 câu, ngưỡng này cho phép sai tối đa 1 câu (22/23 = 95.7 %). v2 ban đầu (91.3 %) sẽ không đạt, tức gate bắt được việc knowledge base chưa đủ; v2 sau khi sửa (100 %) đạt. Ngoài ra không cho phép regression so với baseline. |

Lưu ý: với 3 % request chậm thêm ~1.5 s, **p99 luôn ≈ 1.7 s** nên mình không đặt SLO theo p99 cho agent này; nếu cần thì phải xử lý nguyên nhân request chậm trước (timeout, hedging) thay vì nới ngưỡng.

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

Agent v2 chạy local ở cổng 8002, 300 request mỗi lượt, SLO của công cụ: p95 ≤ 500 ms và error rate ≤ 2 %. File gốc: `reports/load_v2_c{1,10,50,100}.json`.

### 2.1 Concurrency vs latency (agent v2)

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|
| 1 | 4.27 | 191.6 | 221.7 | 1686.0 | 1.00 % (3/300) | PASS |
| 10 | 39.91 | 192.5 | 221.5 | 1683.9 | 0.67 % (2/300) | PASS |
| 50 | 101.15 | 208.6 | 311.1 | 1685.9 | 1.00 % (3/300) | PASS |
| 100 | 50.46 | 437.2 | 4139.1 | 4436.2 | 0.67 % (2/300) | **FAIL** (p95) |

Vì mỗi lượt 300 request là quá ngắn (ở concurrency 50 chỉ chạy 2.97 giây, bị chi phối bởi một request chậm 1.7 s), mình chạy thêm các lượt **20 giây** để có trạng thái ổn định (file `reports/load_v2_c{10,50,100}_20s.json`):

| Concurrency | Số request | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|---|
| 10 | 843 | 40.56 | 189.8 | 221.3 | 1700.1 | 0.71 % | PASS |
| 50 | 4091 | 190.36 | 198.0 | 258.8 | 1711.1 | 1.22 % | PASS |
| 100 | 1186 | 52.17 | 1216.5 | 5126.1 | 5498.8 | 1.60 % | **FAIL** (p95) |

**Nhận xét:** RPS **không** tăng tuyến tính trong toàn dải.
- **Từ 1 đến 50:** gần tuyến tính. Mock LLM là bất đồng bộ (`asyncio.sleep`), nên một process xử lý được nhiều request song song; RPS ≈ concurrency / latency trung bình: 10 / 0.2377 s ≈ 42 (đo được 40.6), 50 / 0.2466 s ≈ 203 (đo được 190.4). Latency gần như không đổi (p50 190-208 ms, p95 221-311 ms).
- **Ở 100:** RPS **tụt** còn 52 (thấp hơn mức 50 đến 3.6 lần) và p50 tăng gấp 6, p95 lên 5.1 s. Request không còn được xử lý song song hiệu quả mà xếp hàng. Đây là hiện tượng thật (lượt 20 giây cho kết quả giống lượt 300 request), không phải do mẫu nhỏ.
- **Nguyên nhân (giả thuyết, chưa kiểm chứng):** mình chưa cô lập được. Các nghi vấn: (1) agent chạy 1 process, 1 event loop; (2) `load_test.py` (Python, 1 luồng) và agent cùng chạy trên một máy nên tranh CPU; (3) giới hạn của lớp mạng/kết nối khi mở 100 kết nối cùng lúc. Để xác định cần đo CPU từng tiến trình, hoặc chạy load generator trên máy khác / chạy nhiều worker. Điều chắc chắn là **điểm bão hòa nằm giữa 50 và 100 concurrency** cho cấu hình này, và SLO p95 < 500 ms không còn đạt ở 100.

### 2.2 Tail latency

Agent v2, concurrency 20, 300 request (file `reports/load_v2_slow_{0,0.03,0.1}.json`):

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| 0 | 191.9 | 216.7 | 234.3 |
| 0.03 (mặc định) | 242.3 | 228.4 | 1697.5 |
| 0.1 | 347.2 | 1692.8 | 1717.1 |

**Nhận xét:** Từ 0 lên 0.1, avg chỉ tăng **×1.8** (191.9 → 347.2 ms) nhưng p95 tăng **×7.8** (216.7 → 1692.8) và p99 tăng **×7.3**. Chỉ số nhạy nhất là **percentile ở đúng ngưỡng của tỉ lệ request chậm**: với 3 % chậm, p99 nhảy vọt (234 → 1698 ms) trong khi p95 gần như không đổi (216.7 → 228.4); với 10 % chậm, p95 mới nhảy (vì 10 % > 5 %). Avg chỉ tăng 26 % ở mức 0.03 nên không cảnh báo được gì: cứ 100 người thì 3 người chờ gần 1.7 giây mà avg vẫn "ổn" (242 ms). Vì vậy SLO phải đặt theo p95/p99, không đặt theo average. Ở 0.1, SLO p95 < 500 ms bị **FAIL** (1692.8 ms).

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

23 câu hỏi trong `eval/golden_dataset.jsonl` (không sửa file này). Một câu đúng khi câu trả lời chứa ≥ 60 % keyword mong đợi. File gốc: `reports/eval_v1.json`, `eval_v2.json`, `eval_v2_fixed.json`.

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4.3 % (1/23) | 91.3 % (21/23) | **100 %** (23/23) |
| Avg tokens / câu | 56.7 | 108.7 | 115.6 |
| Tổng cost (USD) | 0.000398 | 0.000756 | 0.000807 |
| Cost / câu đúng (USD) | 0.00039795 | 0.00003599 | **0.00003508** |
| Quality gate | FAIL (accuracy ≥ 80 %) | PASS (accuracy ≥ 80 %, 0 regression) | PASS (accuracy ≥ 100 %, 0 regression) |

**Những câu v2 trả lời sai ban đầu và cách sửa:**

| ID | Keyword bị thiếu | Bạn đã sửa gì |
|---|---|---|
| `security-02` ("JWT khác gì API key trong xác thực?") | `token`, `hết hạn`, `chữ ký` (thiếu cả 3, score 0) | v2 trả lời câu chung chung ("Tôi là AI agent được deploy lên cloud...") vì knowledge base không có tài liệu nào được kích hoạt bởi từ khóa `jwt`. Thêm một entry vào `KNOWLEDGE_BASE` (`develop/utils/mock_llm.py`) kích hoạt bằng `["jwt"]`, nội dung nêu API key không tự hết hạn còn JWT là token có chữ ký số chứa thời điểm hết hạn. |
| `scaling-03` ("Kubernetes HPA scale dựa trên những chỉ số nào?") | `cpu`, `memory`, `custom metrics` (thiếu cả 3, score 0) | Cùng nguyên nhân (không có tài liệu cho HPA). Thêm entry kích hoạt bằng `["hpa", "kubernetes", "autoscal"]`, nội dung nêu HPA dựa trên CPU, memory hoặc custom metrics. |

Đã kiểm tra trước khi thêm: chỉ hai câu này chứa các từ khóa mới (`jwt`, `hpa`, `kubernetes`, `autoscal`) nên không ảnh hưởng 21 câu còn lại. Kết quả: so với baseline `eval_v2.json`, **2 câu được cải thiện, 0 regression**. Khi sửa mình tắt/bật lại agent v2 vì app không tự nạp lại code.

**Quality gate bằng exit code:** chạy eval cho v1 với `--baseline reports/eval_v2.json` thì **exit code = 1**: accuracy giảm từ 91.3 % xuống 4.3 % và có **20 câu regression**. Chạy eval cho v2 đã sửa thì exit code = 0.

Job CI (GitHub Actions) chặn merge khi chất lượng giảm: bước `run_eval.py` trả exit code 1 khi accuracy < `--min-accuracy` hoặc có regression so với baseline, nên job fail và (nếu bật branch protection yêu cầu job này) PR không merge được:

```yaml
name: quality-gate
on: [pull_request]
jobs:
  eval:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - name: Run agent + eval
        working-directory: 06-lab-complete/benchmark-observability/develop
        run: |
          pip install -r requirements.txt
          AGENT_VERSION=v2 MOCK_ERROR_RATE=0 python app.py &
          sleep 3
          python eval/run_eval.py --url http://localhost:8000 --min-accuracy 0.85
```

Mình chỉ trình bày job này, không thêm vào repo, để tránh tự chạy một workflow trên GitHub Actions ngoài ý muốn.

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:**
- **Chất lượng:** v2 (có retrieval) đúng 100 % so với 4.3 % của v1, vì v1 không có tài liệu nên chỉ trả lời chung chung.
- **Chi phí:** v2 tốn nhiều token hơn (108.7 so với 56.7 token/câu, **+92 %**) vì prompt dài hơn do chèn tài liệu, nên tổng cost cao hơn (0.000756 so với 0.000398 USD, +90 %). Nhưng tính **trên mỗi câu đúng**, v2 rẻ hơn khoảng **11 lần** (0.00003599 so với 0.00039795 USD), vì v1 trả tiền cho gần như toàn câu sai. Đây là lý do "cost / câu đúng" là chỉ số đáng tin hơn "cost / câu" để so hai phiên bản.
- **Latency:** v2 thêm bước retrieval (~20 ms) nên p95 trong eval tăng nhẹ (188.4 → 217.7 ms, +29.3 ms, +15.5 %). Nhưng không nên kết luận latency từ eval 23 câu: một request chậm là p95 nhảy vọt (lần chạy kiểm tra gate của v1 cho p95 = 1515.6 ms chỉ do 1-2 request rơi vào nhóm chậm). Latency phải đo bằng load test (phần 2).
- **Đáng đánh đổi không:** có, chất lượng tăng từ gần 0 lên 100 % trong khi latency tăng khoảng 30 ms và chi phí mỗi câu đúng giảm 11 lần.

---

## 4. Observability stack (production)

Stack Docker Compose (project `k5-day14-observability`): Nginx → 2 agent (v2) → Prometheus, Grafana, Jaeger, Locust. Mỗi container agent bị giới hạn 0.5 CPU / 256 MB. Tải nền cho các thí nghiệm: Locust headless **10 user**, `docker compose` đổi cấu hình bằng biến môi trường rồi tạo lại 2 agent (`up -d --scale agent=2`). Mình dùng 10 user thay vì 30 vì ở 30 user tốc độ chi phí cơ sở đã gần ngưỡng $2/giờ của alert chi phí, nên alert đó sẽ kêu cả khi chưa phá gì.

### 4.1 Screenshot

Tất cả ảnh chụp trong lúc hệ thống có tải nền và đang bị bơm lỗi (`MOCK_ERROR_RATE=0.2` và `MOCK_SLOW_RATE=0.3`), trong thư mục `screenshots/`:

- [x] Dashboard Grafana khi đang có tải: [grafana-dashboard.png](screenshots/grafana-dashboard.png) — Error rate **21.05 %**, Latency p95 **1.89 s**, Traffic 5.2 req/s, Instances up 2, LLM cost (1h) $0.1857.
- [x] Một trace chậm trong Jaeger: [jaeger-slow-trace.png](screenshots/jaeger-slow-trace.png) — trace `2f467a0a…`, 1.7 s, span `chat mock-llm-small` chiếm gần hết.
- [x] Một trace lỗi trong Jaeger (có event `exception`): [jaeger-error-trace.png](screenshots/jaeger-error-trace.png) — trace `6852b424…`, `POST /ask` 503, mục Events (1) → `exception`.
- [x] Trang Alerts của Prometheus với 2 alert đang **firing**: [prometheus-alert-firing.png](screenshots/prometheus-alert-firing.png) — `AgentHighErrorRate` và `AgentHighLatencyP95` (nhóm `agent-slo` hiện FIRING (2)).

### 4.2 Thí nghiệm "phá hệ thống"

Thời gian đo từ lúc ra lệnh đổi cấu hình (gồm cả thời gian tạo lại container) đến lần đầu thấy alert ở trạng thái `firing` qua API Prometheus (`/api/v1/alerts`, hỏi mỗi 5 giây, nên sai số khoảng ±5 giây). Nguồn: `reports/alert_experiments.log` (log thô của script đo; có vài dòng traceback ở phần lấy trace Jaeger do script phụ bị lỗi định dạng, không ảnh hưởng số đo alert), một lần chạy cho mỗi thí nghiệm.

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | `AgentHighErrorRate` (pending sau 27 s) | **88 s** | Error rate (Golden Signals), Requests/s theo status code, LLM calls theo kết quả |
| B | `MOCK_SLOW_RATE=0.3` | `AgentHighLatencyP95` (pending sau 27 s) | **149 s** | Latency p95 (Golden Signals), Latency /ask p50/p95/p99 |
| C | `LLM_MODEL=mock-llm-large` | `LLMCostBurnRateHigh` (pending sau 62 s) | **184 s** (tốc độ chi phí đo được lúc firing: $6.41/giờ) | Cost burn rate (USD/giờ), LLM cost (1h) |
| D | `docker pause` 1 instance | `AgentInstanceDown` (pending sau 11 s) | **41 s** | Instances up, Requests/s theo instance |
| E | `AGENT_VERSION=v1` | **Không có alert nào** sau 150 s (kiểm tra `agent_info` thấy cả 2 instance báo `v1`) | không firing | Phiên bản đang chạy, Retrieval hit ratio (suy ra từ code: v1 không có bước retrieval; mình chưa quan sát trực tiếp các panel này) |

Nhận xét:
- Alert có `for: 1m` (A) firing sau 88 s, `for: 2m` (B) sau 149 s: thời gian ≈ `for` + thời gian metric phản ánh đổi (cửa sổ `rate(...[1m])`, scrape mỗi 5 s, tạo lại container). Alert chi phí (C) chậm nhất vì dùng cửa sổ 5 phút: tốc độ chi phí phải leo dần qua ngưỡng $2/giờ trước khi đồng hồ `for: 2m` bắt đầu chạy.
- **D:** trong lúc instance bị pause, Nginx ghi **10 response 504** (hết thời gian chờ instance không trả lời) cùng 1 response 503 trong khung 41 giây của thí nghiệm, nhưng alert lỗi của agent (`AgentHighErrorRate`) **không firing**, chỉ `AgentInstanceDown` firing. Lỗi 504 xảy ra ở Nginx, request chưa bao giờ được agent xử lý xong nên metric của agent không đếm được. Giám sát chỉ thấy những gì chính service đó nhìn thấy, nên cần thêm giám sát ở tầng load balancer hoặc kiểm tra tổng hợp từ bên ngoài.
- Trong khung thí nghiệm A Nginx còn ghi 82 response 502 (cùng 100 response 503 là lỗi LLM do agent trả về); nhiều khả năng 502 đến từ lúc 2 agent đang được tạo lại và chưa sẵn sàng, mình chưa kiểm chứng riêng điều này.

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**

Metric hạ tầng (latency, error rate, instance up) không biết câu trả lời đúng hay sai: v1 vẫn trả 200 và nhanh hơn v2 một chút, nên mọi thứ vẫn "xanh" trong khi accuracy rơi từ 100 % xuống 4.3 % (phần 3). Muốn phát hiện, mình sẽ dùng: (1) **eval trên golden dataset** làm quality gate trước mỗi lần deploy và chạy định kỳ (đúng cơ chế đã làm ở phần 3, v1 so với baseline v2 cho exit code 1 và 20 câu regression); (2) **eval lấy mẫu trên traffic thật** (chấm bằng LLM-as-judge hoặc người) và thu feedback người dùng; (3) thêm **metric chất lượng làm proxy** rồi đặt alert, ví dụ tỉ lệ retrieval có kết quả (Retrieval hit ratio) và độ dài/token của câu trả lời, vì v1 làm các chỉ số này đổi hẳn; (4) triển khai canary kèm eval trước khi chuyển hết traffic sang phiên bản mới.

### 4.3 Debug bằng trace

Trace chậm nhất trong 300 trace Jaeger của khung thí nghiệm (lấy bằng API Jaeger, rồi tìm lại log theo `trace_id`; chi tiết trong `reports/phase_c_traces.log`):

- `trace_id`: `2f467a0af7a9f0f97e71cd64466c5139`
- Tổng thời gian: **1720.5 ms** (Jaeger hiển thị 1.7 s)
- Span chiếm nhiều thời gian nhất: `chat mock-llm-small` — **1696.5 ms, 98.6 %** tổng thời gian. Còn lại: `agent.retrieve_context` 19.6 ms (1.1 %); `agent.run` 1716.6 ms và `POST /ask` 1720.5 ms là các span cha bao ngoài. Tức chậm ở bước gọi LLM (upstream), không phải code của agent hay bước retrieval.
- Dòng log tương ứng (`docker compose logs agent | grep <trace_id>`): `llm_ms` 1695.9 khớp với span `chat` (1696.5 ms), `ms` 1719.2 khớp với span gốc.

```json
{"ts": "2026-11-25T13:25:32.559693+00:00", "level": "INFO", "service": "observable-agent", "instance": "e484495ae17d", "event": "llm_call", "trace_id": "2f467a0af7a9f0f97e71cd64466c5139", "span_id": "b984a3830187fbc7", "request_id": "2f26128e9839", "model": "mock-llm-small", "agent_version": "v2", "input_tokens": 95, "output_tokens": 55, "cost_usd": 4.7e-05, "llm_ms": 1695.9}
{"ts": "2026-11-25T13:25:32.560374+00:00", "level": "INFO", "service": "observable-agent", "instance": "e484495ae17d", "event": "http_request", "trace_id": "2f467a0af7a9f0f97e71cd64466c5139", "span_id": "b984a3830187fbc7", "request_id": "2f26128e9839", "method": "POST", "route": "/ask", "status": 200, "ms": 1719.2}
```

Trace lỗi (cũng khớp với log theo `trace_id`):

- `trace_id`: `6852b424fe0aada4b9608531f26eb33d`, tổng 875.7 ms, `POST /ask` trả **503**.
- Các span `POST /ask`, `agent.run` và `chat mock-llm-small` đều đánh dấu ERROR; span `chat` có event **`exception`** (`exception.type = utils.mock_llm.LLMError`, `exception.message = Upstream LLM error: 503 Service Unavailable (mock)`), stack trace chỉ đến `app/main.py` dòng 153 (`run_agent`) và `utils/mock_llm.py` dòng 199 (`generate`).

```json
{"ts": "2026-11-25T13:25:54.737414+00:00", "level": "INFO", "service": "observable-agent", "instance": "e484495ae17d", "event": "llm_error", "trace_id": "6852b424fe0aada4b9608531f26eb33d", "span_id": "605a30e7ec61d9ef", "request_id": "c57f52d8fc0a", "error": "Upstream LLM error: 503 Service Unavailable (mock)"}
{"ts": "2026-11-25T13:25:54.737706+00:00", "level": "INFO", "service": "observable-agent", "instance": "e484495ae17d", "event": "http_request", "trace_id": "6852b424fe0aada4b9608531f26eb33d", "span_id": "605a30e7ec61d9ef", "request_id": "c57f52d8fc0a", "method": "POST", "route": "/ask", "status": 503, "ms": 875.1}
```

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

Lệnh: `docker compose -p k5-day14-observability run --rm locust ... --headless -u 100 -r 10 -t 2m --csv /mnt/results/scale_{1,3}`. Cấu hình mặc định (`MOCK_SLOW_RATE=0.03`, `MOCK_ERROR_RATE=0.01`), agent v2. File gốc: `benchmark-results/scale_1_stats.csv` và `scale_3_stats.csv`. Hàng `/ask` (SLO tính trên endpoint này):

| Số instance | Request `/ask` | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|---|
| 1 | 7114 | 59.61 | 200 | 290 | 1700 | 70 (0.98 %) |
| 3 | 7113 | 59.60 | 200 | 280 | 1700 | 71 (1.00 %) |

Tổng gộp cả `/health`: 1 instance 7831 request, 65.62 req/s, p95 280 ms; 3 instance 7800 request, 65.36 req/s, p95 270 ms.

**Giải thích kết quả:** Scale từ 1 lên 3 instance **không cải thiện** RPS, p95 hay p99 (59.61 so với 59.60 req/s; p95 290 so với 280 ms; p99 cùng 1700 ms). Lý do nằm trong số liệu:
- **Tải bị giới hạn bởi người dùng mô phỏng, không phải bởi năng lực agent.** Locust là hệ kín: mỗi user nghỉ 0.5-2 giây (trung bình 1.25 s) giữa các lần hỏi, nên 100 user chỉ tạo ra khoảng 100 / (1.25 + 0.24) ≈ 67 req/s, đúng với 65.6 req/s đo được ở cả hai cấu hình. Một instance đã xử lý trọn vẹn mức tải đó (p95 290 ms, chưa bão hòa; ở phần 2 một process đạt 190 req/s ở concurrency 50), nên thêm instance không có gì để chia.
- **Độ trễ mỗi request nằm ở bước gọi LLM (mock), không ở hạ tầng.** Mỗi request tốn ≈ 190-200 ms ở LLM bất kể có bao nhiêu instance; thêm instance không làm LLM nhanh hơn. Panel "LLM latency p95 theo model" là chỗ phù hợp để quan sát nút thắt này (mình chưa chụp panel đó).
- **p99 không đổi (1700 ms)** vì đó là 3 % request chậm thêm ~1.5 s do mock LLM (`MOCK_SLOW_RATE=0.03`), không phụ thuộc số instance. Scale ngang không sửa được tail latency do upstream.
- Failures ≈ 1 % ở cả hai cấu hình đúng bằng `MOCK_ERROR_RATE=0.01`: là lỗi upstream giả lập, không phải do thiếu tài nguyên.
- Scale chỉ có ích khi tải thật sự vượt năng lực một instance (nhiều user hơn hoặc ít thời gian nghỉ hơn). Mình **chưa thử** tải đó trong stack Docker, nên không kết luận được điểm bão hòa của stack ở đây; điểm bão hòa chỉ đo được ở phần 2 (agent chạy trực tiếp, nằm giữa 50 và 100 concurrency).

---

## 6. Kết luận

- 3 điều bạn học được về benchmark & observability:
  1. **Trung bình che giấu tail; phải đo p95/p99 và đối chiếu SLO.** Với 3 % request chậm thêm 1.5 s, avg chỉ tăng 26 % (191.9 → 242.3 ms) trong khi p99 tăng ×7 (234 → 1698 ms). Scale ngang (phần 5) cũng không sửa được tail do upstream gây ra.
  2. **Metric hạ tầng không bắt được lỗi chất lượng.** Thí nghiệm E (đổi sang v1) làm accuracy rơi từ 100 % xuống 4.3 % mà không alert nào kêu; chỉ eval trên golden dataset (quality gate với exit code) mới bắt được. Cần cả hai loại benchmark, lấy "cost / câu đúng" thay vì "cost / câu" để so hai phiên bản.
  3. **Quan sát chỉ thấy những gì chính service nhìn thấy.** Khi một instance bị pause, Nginx trả 504 nhưng agent không hề ghi nhận lỗi; chỉ `AgentInstanceDown` (dựa trên `up == 0`) phát hiện được. Và khi cần tìm nguyên nhân chậm/lỗi, trace cho biết đúng bước (span `chat` chiếm 98.6 %), còn log theo `trace_id` cho chi tiết.
- Nếu đưa agent này lên production thật, bạn sẽ thêm metric / alert nào nữa?

  - **Chất lượng:** alert trên tỉ lệ retrieval hit và độ dài câu trả lời (proxy cho lỗi như thí nghiệm E), cùng eval định kỳ trên mẫu traffic thật.
  - **Tầng load balancer / từ bên ngoài:** alert theo tỉ lệ 5xx của Nginx và một synthetic check gọi `/ask` từ ngoài, vì lỗi 504 không hiện ở metric của agent.
  - **Saturation:** alert khi `agent_in_flight_requests` cao kéo dài và đo CPU/memory của container.
  - **Chi phí:** budget theo từng user và theo ngày (bổ sung cho alert tốc độ chi phí hiện tại), tách ngưỡng theo model.
  - **p99:** theo dõi riêng p99 và xử lý request chậm ở upstream (timeout ngắn, retry/hedging) vì scale ngang không giải quyết được.

---

## 7. Ghi chú về quá trình đo (để đối chiếu, không ẩn lỗi)

- **Dockerfile của stack Part 7 có lỗi và mình đã sửa 1 dòng.** Lần dựng đầu tiên, container `agent` crash liên tục (`ModuleNotFoundError: No module named 'uvicorn'`) nên Locust báo 100 % lỗi 502; mình **bỏ hết file CSV của lần đó** và đo lại. Nguyên nhân: user `agent` có home là `/app` (`useradd -d /app`) nên Python tìm package người dùng ở `/app/.local`, trong khi builder đã copy sang `/home/agent/.local`. Sửa: thêm `ENV PYTHONUSERBASE=/home/agent/.local` vào `06-lab-complete/benchmark-observability/production/Dockerfile`. Sau đó mình thêm chốt chặn: chỉ chạy Locust khi `/ask` qua Nginx trả 200 và Prometheus thấy đủ target agent đang `up`.
- Pha chụp ảnh bị gián đoạn một lần (Docker Desktop tắt giữa chừng nên mất trạng thái và trace cũ), nên mình dựng lại stack và tạo lại trạng thái lỗi; trace trong phần 4.3 và ảnh Jaeger đều lấy từ lần dựng lại này. Số liệu thời gian-đến-firing (4.2) lấy từ lần chạy trước khi bị gián đoạn, log thô nằm ở `reports/alert_experiments.log`.
- Mỗi thí nghiệm ở 4.2 chỉ chạy **một lần** nên thời gian-đến-firing có sai số vài chục giây giữa các lần chạy khác nhau.
- Agent trong stack được chạy bằng 1 worker mỗi container (đúng thiết kế của đề, vì `prometheus_client` lưu metric trong bộ nhớ từng process).
