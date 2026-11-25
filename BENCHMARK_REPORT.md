# Benchmark & Observability Report — Day 14

> Mọi con số trong báo cáo lấy từ các file JSON/CSV trong `reports/` và `benchmark-results/`, không ước lượng.
> Trạng thái: **phần 1-3 (CP7) đã điền**; phần 4-5 (Observability stack, scaling) và phần 6 sẽ điền ở CP8.

**Họ tên:** Nguyen Tran Tien (MSSV 2A202603504)
**Ngày chạy:** 2026-11-25
**Môi trường:** Windows 11 Home, Intel Core i5-12450H (12 luồng), WSL2 Ubuntu được cấp 7.8 GB RAM, Python 3.11.18. Agent (1 tiến trình uvicorn) và công cụ sinh tải `load_test.py` chạy **chung một máy** nên kết quả ở mức concurrency cao có thể bị ảnh hưởng bởi chính máy sinh tải.

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

_Điền ở CP8 (Prometheus, Grafana, Jaeger, Locust, alerts)._

### 4.1 Screenshot

- [ ] Dashboard Grafana khi đang có tải (thấy rõ Golden Signals)
- [ ] Một trace chậm trong Jaeger (thấy span nào chiếm thời gian)
- [ ] Một trace lỗi trong Jaeger (có event `exception`)
- [ ] Trang Alerts của Prometheus với ít nhất 1 alert đang **firing**

### 4.2 Thí nghiệm "phá hệ thống"

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | | | |
| B | `MOCK_SLOW_RATE=0.3` | | | |
| C | `LLM_MODEL=mock-llm-large` | | | |
| D | `docker pause` 1 instance | | | |
| E | `AGENT_VERSION=v1` | | | |

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**

...

### 4.3 Debug bằng trace

- `trace_id`: ...
- Tổng thời gian: ... ms
- Span chiếm nhiều thời gian nhất: ...
- Dòng log tương ứng (grep theo `trace_id`):

```json

```

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | | | | | |
| 3 | | | | | |

**Giải thích kết quả:** ...

---

## 6. Kết luận

_Điền ở CP8._
