# Benchmark & Observability Report — Day 14

> Mọi con số dưới đây được ghi nhận trực tiếp từ các file JSON trong `reports/` và output thực thi trên máy ngày 2026-11-25, không ước lượng.

**Họ tên:** Dương Tuấn Hưng (MSSV: 2A202603416 · Lớp: K5-L3A)  
**Ngày chạy:** 2026-11-25  
**Môi trường:** Windows 10 (10.0.19045), Intel Core i5-1135G7 @ 2.40GHz, Python 3.11.15 (`.venv`, chạy local không Docker do lỗi Windows `0x800f0922` khi bật WSL2/VirtualMachinePlatform)

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | < 500 ms | 95% người dùng nhận phản hồi trong dưới nửa giây (trải nghiệm mượt khi LLM mock latency nền ~120–180ms + retrieval ~20ms), tránh để tail latency ở mức 3% làm hỏng p95 |
| Error rate `/ask` | < 2.0 % | Mock LLM có tỉ lệ lỗi upstream ngẫu nhiên mặc định ~1%; đặt ngưỡng 2% cho phép dung sai error budget nhỏ trước khi coi là sự cố |
| Accuracy trên golden dataset | ≥ 85 % | Đảm bảo chất lượng RAG của agent v2 ổn định khi thay đổi prompt/KB/model và chặn các PR làm giảm chất lượng (regression = 0) |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2)

Chạy `python load_test.py --url http://127.0.0.1:8002 --requests 300 --concurrency <c>` (lưu tại [reports/](reports/)):

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|
| 1 | 4.22 | 202.8 | 246.9 | 1714.6 | 2.00% | PASS |
| 10 | 47.68 | 196.4 | 232.6 | 328.6 | 1.67% | PASS |
| 50 | 99.66 | 216.9 | 761.3 | 1728.4 | 1.67% | FAIL (p95 > 500ms) |
| 100 | 46.64 | 727.4 | 4374.3 | 5011.1 | 1.33% | FAIL (p95 > 500ms) |

**Nhận xét:** RPS có tăng tuyến tính theo concurrency không? Vì sao?

RPS **không tăng tuyến tính**. Từ concurrency 1 → 10, RPS tăng gần tuyến tính (`4.22 → 47.68 req/s`, gấp ~11.3x) vì agent xử lý `async` nên chờ I/O song song hiệu quả và p50/p95 gần như không đổi (~200–247ms). Từ 10 → 50, RPS chỉ tăng hơn gấp đôi (`47.68 → 99.66 req/s`) nhưng p95 bắt đầu tăng vọt lên `761.3 ms` (vi phạm SLO). Tới concurrency `100`, hệ thống bị nghẽn (saturation) ở 1 process uvicorn + event loop/socket trên Windows khiến RPS **giảm ngược** xuống `46.64 req/s`, p50 tăng lên `727.4 ms` và p95 vọt lên `4374.3 ms`.

### 2.2 Tail latency

Chạy cùng `--requests 300 --concurrency 20` trên agent v2 với 3 mức `MOCK_SLOW_RATE`:

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| 0 | 191.1 | 226.7 | 234.3 |
| 0.03 (mặc định) | 252.8 | 245.2 | 1720.0 |
| 0.1 | 312.2 | 1698.1 | 1716.0 |

**Nhận xét:** Chỉ số nào nhạy nhất với request chậm? Vì sao SLO không nên đặt theo average?

`p99` (và tiếp theo là `p95` khi tỉ lệ request chậm vượt 5%) nhạy nhất với tail latency: khi `MOCK_SLOW_RATE` tăng từ `0` lên `0.03` (chỉ 3% request bị chậm), `avg` chỉ nhích nhẹ `+61.7 ms` (`191.1 → 252.8 ms`), nhưng `p99` nhảy vọt hơn 7 lần (`234.3 → 1720.0 ms`). Khi `MOCK_SLOW_RATE=0.1` (10% request chậm > 5%), `avg` vẫn trông chấp nhận được ở `312.2 ms`, nhưng `p95` đã vọt lên `1698.1 ms` (gấp 3.4 lần ngưỡng SLO 500ms). Do đó không thể đặt SLO theo `average`, vì giá trị trung bình làm mượt và che giấu nhóm người dùng đang phải chờ gần 2 giây.

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4.3% (1/23) | 91.3% (21/23) | 100.0% (23/23) |
| Avg tokens / câu | 57.7 | 109.0 | 113.7 |
| Tổng cost (USD) | $0.000413 | $0.000759 | $0.000790 |
| Cost / câu đúng (USD) | $0.00041295 | $0.00003616 | $0.00003436 |
| Quality gate | FAIL | PASS (so với v1, ≥80%) | PASS (23/23, ≥100%, 0 regression) |

**Những câu v2 trả lời sai ban đầu và cách bạn sửa:**

| ID | Keyword bị thiếu | Bạn đã sửa gì |
|---|---|---|
| `security-02` | `token`, `hết hạn`, `chữ ký` | Thêm entry `(["jwt"], ...)` giải thích JWT có chữ ký số, chứa thông tin user và thời điểm hết hạn vào `KNOWLEDGE_BASE` trong `develop/utils/mock_llm.py` và `production/utils/mock_llm.py` |
| `scaling-03` | `cpu`, `memory`, `custom metrics` | Thêm entry `(["hpa", "kubernetes", "autoscal"], ...)` giải thích Kubernetes HPA scale pod theo CPU, memory hoặc custom metrics vào `KNOWLEDGE_BASE` trong cả `develop` và `production` |

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:**

Agent v2 thêm bước retrieval (RAG) nên prompt dài hơn: số token trung bình mỗi câu tăng gần gấp đôi (`57.7 → 109.0–113.7` tokens/câu), kéo theo tổng chi phí cho 23 câu tăng từ `$0.000413` lên `$0.000790` và thêm ~20ms retrieval latency. Tuy nhiên, độ chính xác nhảy từ `4.3%` (1/23) lên `100.0%` (23/23), khiến **chi phí trên mỗi câu trả lời đúng** của v2 (`$0.00003436`) **rẻ hơn ~12 lần** so với v1 (`$0.00041295`). Việc thêm bước retrieval là hoàn toàn xứng đáng.

**CI Quality Gate ([.github/workflows/eval.yml](.github/workflows/eval.yml)):**

Đã tạo GitHub Actions workflow chạy `python eval/run_eval.py --url http://localhost:8000 --min-accuracy 0.85` trên mỗi `pull_request`. Khi chạy thử kiểm chứng trên `v1` so với baseline `eval_v2.json`, `run_eval.py` phát hiện 20 câu bị regression và trả về **exit code 1** (`Quality gate ... ❌ FAIL`), giúp CI tự động chặn merge PR nếu code mới làm giảm độ chính xác hoặc gây regression.

---

## 4. Observability stack (production)

Chạy full stack Docker Compose (`-p k5-day14-observability`, 3 replicas `agent` + `nginx` + `prometheus` + `grafana` + `jaeger` + `locust`) trên GitHub Codespaces, kết hợp kiểm chứng `/metrics` và JSON log của `06-lab-complete/benchmark-observability/production/app/main.py`:

**Mẫu output `/metrics` và JSON log thu được trực tiếp từ `06-lab-complete/benchmark-observability/production/app/main.py` (`AGENT_VERSION=v2`):**
```text
http_requests_total{method="GET",route="/health",status="200"} 1.0
http_requests_total{method="POST",route="/ask",status="200"} 2.0
agent_in_flight_requests 0.0
llm_requests_total{model="mock-llm-small",status="ok"} 2.0
llm_tokens_total{model="mock-llm-small",type="input"} 150.0
llm_tokens_total{model="mock-llm-small",type="output"} 77.0
llm_cost_usd_total{model="mock-llm-small"} 6.869999999999999e-05
agent_info{model="mock-llm-small",version="v2"} 1.0
```
```json
{"ts": "2026-11-25T08:56:51.818186+00:00", "level": "INFO", "service": "observable-agent", "instance": "local", "event": "llm_call", "trace_id": "", "span_id": "", "request_id": "10bca39d6cd5", "model": "mock-llm-small", "agent_version": "v2", "input_tokens": 81, "output_tokens": 46, "cost_usd": 4e-05, "llm_ms": 192.1}
{"ts": "2026-11-25T08:56:51.818864+00:00", "level": "INFO", "service": "observable-agent", "instance": "local", "event": "http_request", "trace_id": "", "span_id": "", "request_id": "10bca39d6cd5", "method": "POST", "route": "/ask", "status": 200, "ms": 219.5}
```

### 4.1 Screenshot
- [x] [Dashboard Grafana khi đang có tải](screenshots/grafana-dashboard.png) (panel *Latency /ask — p50/p95/p99* và *Requests/s theo status code* có dữ liệu thực)
- [x] [Trace trong Jaeger](screenshots/jaeger-slow-trace.png) (`observable-agent`, 20 traces với duration lên tới ~900ms)
- [x] [Trace lỗi trong Jaeger](screenshots/jaeger-error-trace.png) (`observable-agent: POST /ask` HTTP 503, tag lỗi ở `POST /ask`, `agent.run`, `chat mock-llm-small`)
- [x] [Trang Alerts của Prometheus với 2 alert đang **FIRING**](screenshots/prometheus-alert-firing.png) (`AgentHighErrorRate` và `AgentHighLatencyP95`)

### 4.2 Thí nghiệm "phá hệ thống" & Phân tích Exercise 7.4–7.6

Chạy Locust 30 users / ramp up 5 với cấu hình `MOCK_ERROR_RATE=0.2` và `MOCK_SLOW_RATE=0.3`:

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | `AgentHighErrorRate` (`critical`) | ~1 phút (theo rule `for: 1m`) | *Requests/s theo status code* (~3 req/s lỗi `503` trên tổng ~15 req/s `200`+`503`) |
| B | `MOCK_SLOW_RATE=0.3` | `AgentHighLatencyP95` (`warning`) | ~2 phút (theo rule `for: 2m`) | *Latency /ask — p50/p95/p99* (`p95` ~1.88s, `p99` ~1.96s vượt ngưỡng 1s; `p50` vẫn ~200ms, `avg` ~600ms) |

- **Tại sao `curl http://localhost:8080/metrics` trả về 404 (Exercise 7.4):** Trong [nginx.conf](06-lab-complete/benchmark-observability/production/nginx/nginx.conf), `location = /metrics { return 404; }` chủ động chặn truy cập `/metrics` từ bên ngoài để tránh lộ thông tin nội bộ (route, lưu lượng, model, chi phí); chỉ Prometheus trong mạng nội bộ `obs_net` mới scrape trực tiếp `agent:8000/metrics`.
- **Tại sao `input_tokens > output_tokens`:** Trong `mock_llm.py`, prompt đầu vào của v2 gồm `SYSTEM_PROMPT + context (tài liệu RAG) + question` (~70–95 tokens), dài hơn câu trả lời ngắn gọn ở đầu ra (~30–55 tokens). Thực tế chạy 2 câu trên `production/app` ghi nhận `input=150` tokens so với `output=77` tokens.
- **Thí nghiệm E (`AGENT_VERSION=v1`) không làm alert nào firing — cách phát hiện trong production:**
  Các alert hạ tầng (`AgentHighErrorRate`, `AgentHighLatencyP95`, `AgentInstanceDown`, `LLMCostBurnRateHigh`) chỉ đo HTTP status 5xx, latency, `up` và cost — khi đổi về `v1`, agent vẫn trả `HTTP 200` rất nhanh và còn tốn ít tiền hơn nên mọi panel hạ tầng đều xanh. Để phát hiện sự cố suy giảm chất lượng này trong production, phải chạy **eval trên golden dataset làm quality gate trong CI/CD** trước khi deploy (như `.github/workflows/eval.yml`), kết hợp giám sát metric chất lượng như `agent_retrieval_requests_total{outcome="hit"|"miss"}` (retrieval hit ratio giảm về 0), feedback người dùng và chạy LLM-as-judge / online eval trên mẫu traffic thật.
- **Thí nghiệm D (`docker pause` thay vì `docker stop` và lỗi 504 ở Nginx):** `docker stop` làm container biến mất khỏi Docker DNS nên Prometheus không còn thấy target để báo `up == 0`; `docker pause` giữ nguyên IP trong DNS nhưng container treo nên Prometheus scrape lỗi → `up == 0` sau 30s (`AgentInstanceDown`). Lỗi 504 do Nginx timeout (`proxy_read_timeout 10s`) xảy ra trước khi agent trả response, nên `http_requests_total` của agent không ghi nhận — cần theo dõi cả metric của Nginx và synthetic monitoring từ bên ngoài.

### 4.3 Debug bằng trace
Quan sát trực tiếp từ ảnh trace Jaeger [jaeger-error-trace.png](screenshots/jaeger-error-trace.png) và [jaeger-slow-trace.png](screenshots/jaeger-slow-trace.png):

- Trace ID (rút gọn hiển thị trên Jaeger UI): `f936069` (`observable-agent: POST /ask`, HTTP `503`)
- Tổng thời gian: `113 ms` (4 spans, depth 3)
- Span chiếm nhiều thời gian nhất: `chat mock-llm-small` (`94.2 ms`, chiếm **83.4%** tổng thời gian request), trong khi `agent.retrieve_context` chỉ mất `16.4 ms` (**14.5%**).
- Tương tự ở danh sách trace trong Jaeger (`jaeger-slow-trace.png`), các trace chậm nhất đạt gần `900 ms` đều do thời gian chờ ở span LLM (`chat mock-llm-small`). Dòng log JSON của agent tự động gắn `trace_id` và `span_id` từ `current_trace_ids()` để liên kết chéo với Jaeger.

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

Số liệu lấy trực tiếp từ [scale_1_stats.csv](benchmark-results/scale_1_stats.csv) và [scale_3_stats.csv](benchmark-results/scale_3_stats.csv) (chạy trên GitHub Codespaces, Docker Compose `-p k5-day14-observability`):

### Tổng hợp (`Aggregated` — `POST /ask` + `GET /health`)
| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | 65.26 | 190 | 260 | 1700 | 82 / 7780 (1.05%) |
| 3 | 65.93 | 190 | 240 | 1700 | 66 / 7859 (0.84%) |

### Riêng endpoint `POST /ask`
| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | 59.93 | 200 | 260 | 1700 | 82 / 7144 (1.15%) |
| 3 | 60.08 | 200 | 250 | 1700 | 66 / 7162 (0.92%) |

**Giải thích kết quả:** Scale lên 3 instance chỉ giúp `p95` giảm nhẹ (`260ms → 250ms` ở `/ask`, `260ms → 240ms` tổng hợp; riêng `/health` giảm rõ `33ms → 23ms` ở p95 và `83ms → 45ms` ở p99 do bớt tranh chấp event loop), còn `p50` (`200ms`) và `p99` (`1700ms`) gần như giữ nguyên. Nguyên nhân là agent chạy `async` nên ở mức tải ~65 req/s, 1 instance chưa bị bão hòa CPU; **nút thắt nằm ở latency tự nhiên của upstream LLM call** (`chat mock-llm-small` mất ~120–180ms + ~20ms retrieval và 3% request slow cộng thêm ~1500ms), nên tăng số replica không thể làm LLM trả lời nhanh hơn. Tỉ lệ failure ~1% (`1.15%` và `0.92%`) khớp với `MOCK_ERROR_RATE=0.01` mặc định của mock LLM.

---

## 6. Kết luận

- **3 điều học được về benchmark & observability:**
  1. Latency trung bình (`avg`) che giấu rất tốt vấn đề tail latency: chỉ 3% request chậm đã đẩy `p99` lên ~1.7s trong khi `avg` chỉ nhích nhẹ, nên SLO bắt buộc phải đặt theo `p95`/`p99`.
  2. Benchmark hiệu năng và benchmark chất lượng giải quyết 2 bài toán độc lập: agent v1 nhanh và rẻ hơn mỗi câu nhưng accuracy chỉ 4.3%, trong khi v2 dùng RAG đắt hơn ~2x mỗi câu nhưng **cost / câu đúng rẻ hơn ~12x** và đạt 100% sau khi bổ sung Knowledge Base.
  3. Metrics (Prometheus), Traces (OpenTelemetry/Jaeger) và JSON Logs gắn `trace_id` bổ trợ lẫn nhau, nhưng giám sát hạ tầng thuần túy không bắt được lỗi chất lượng (`AGENT_VERSION=v1`) — cần kết hợp CI quality gate (`run_eval.py`) và metric nghiệp vụ (`retrieval_hit`).
- **Nếu đưa agent này lên production thật, sẽ thêm metric / alert nào nữa?**
  - Metric `rate_limit_exceeded_total` (HTTP 429) và `budget_exceeded_total` (HTTP 402) để phát hiện sớm hành vi lạm dụng API key hoặc client sắp chạm ngưỡng ngân sách.
  - Metric tỷ lệ retrieval miss (`agent_retrieval_requests_total{outcome="miss"} / total`) kèm alert khi tỉ lệ miss tăng đột biến, và online eval score (LLM-as-judge trên mẫu 5–10% traffic thật) để phát hiện sớm hiện tượng model/prompt drift.
