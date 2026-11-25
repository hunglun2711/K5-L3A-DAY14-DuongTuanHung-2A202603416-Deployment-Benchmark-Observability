# Day 14 Lab - Mission Answers

**Học viên:** Dương Tuấn Hưng  
**MSSV:** 2A202603416 · **Lớp:** K5-L3A  
**Ngày thực hiện:** 2026-11-25

---

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found in `01-localhost-vs-production/develop/app.py`

1. **Hardcode secrets trong source code** (dòng 17–18): `OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"` và `DATABASE_URL = "postgresql://admin:password123@localhost:5432/mydb"` ghi trực tiếp vào code, đẩy lên GitHub sẽ bị lộ ngay lập tức.
2. **Hardcode cấu hình toàn cục, không đọc từ biến môi trường** (dòng 21–22): `DEBUG = True`, `MAX_TOKENS = 500` cố định trong file, không thể đổi theo môi trường (`dev`/`staging`/`production`) mà không sửa code.
3. **Dùng `print()` thay cho structured logging và log cả secret** (dòng 33–34, 38): `print(f"[DEBUG] Using key: {OPENAI_API_KEY}")` vừa khó thu thập/lọc trên log aggregator, vừa làm lộ secret ra stdout/log file.
4. **Thiếu endpoint health check & readiness** (dòng 42–43): Không có `/health` (liveness) và `/ready` (readiness), nên cloud platform / load balancer không biết khi nào container chết để restart hoặc chưa sẵn sàng để ngừng route traffic.
5. **Bind `localhost` và hardcode `port=8000` với `reload=True`** (dòng 49–53): `host="localhost"` chỉ nhận kết nối nội bộ (không nhận traffic từ ngoài container/Docker); `port=8000` bỏ qua biến `PORT` do Railway/Render cấp; `reload=True` bật file watcher tốn CPU/RAM và không an toàn trong production.
6. **Không quản lý lifecycle / graceful shutdown**: Không có `lifespan` hay xử lý `SIGTERM` để chờ các request đang xử lý (in-flight) hoàn thành trước khi tắt.

*(Trong `01-localhost-vs-production/production/app.py` và `config.py`, các vấn đề trên đã được khắc phục: `Settings` đọc biến môi trường + `validate()` fail-fast khi `ENVIRONMENT=production` thiếu `AGENT_API_KEY`, log JSON, có `/health` và `/ready`, bind `settings.host` (`0.0.0.0`) và `settings.port` từ `PORT`, và có `lifespan` + `SIGTERM` handler.)*

### Exercise 1.2: Chạy bản develop & production

**Kết quả chạy thực tế `01-localhost-vs-production/develop/app.py` (nhận `question` qua query param):**
```text
POST /ask?question=Hello -> HTTP 200
{"answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
```

**Kết quả chạy thực tế `01-localhost-vs-production/production/app.py` (với `ENVIRONMENT=production DEBUG=false`):**
```text
GET /health -> HTTP 200
{"status":"ok","uptime_seconds":0.3,"version":"1.0.0","environment":"production","timestamp":"2026-11-25T08:54:19.255627+00:00"}

GET /ready -> HTTP 200
{"ready":true}

POST /ask -> HTTP 200
{"question":"Hello","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé.","model":"gpt-4o-mini"}
```

### Exercise 1.3: Comparison table

| Feature | Develop (`develop/app.py`) | Production (`production/app.py`) | Why Important? |
|---------|-----------------------------|-----------------------------------|----------------|
| **Config & Secrets** | Hardcode `OPENAI_API_KEY`, `DATABASE_URL`, `DEBUG=True`, `port=8000` | Đọc qua `Settings` từ env vars (`os.getenv`), `validate()` fail-fast | Tách biệt config khỏi code (12-Factor), không lộ secret vào Git, cùng 1 image chạy được ở dev/staging/prod |
| **Health / Readiness** | Không có (`/health`, `/ready` đều thiếu) | Có `GET /health` (liveness) và `GET /ready` (readiness, trả 503 nếu chưa ready) | Orchestrator/cloud tự động restart container lỗi (`/health`) và chỉ route traffic khi app đã sẵn sàng (`/ready`) |
| **Logging** | `print("[DEBUG] ...")`, in cả `OPENAI_API_KEY` | `logging` với format JSON (`time`, `level`, `msg`), không log secret | Log JSON dễ parse, index và truy vấn trên Grafana Loki / Datadog / Cloud Logging; tránh rò rỉ thông tin nhạy cảm |
| **Network & Server** | `host="localhost"`, `port=8000`, `reload=True` | `host="0.0.0.0"`, `port=settings.port`, `reload=settings.debug` | `0.0.0.0` cần thiết để container nhận traffic từ bên ngoài; `PORT` lấy từ platform; tắt `reload` tránh tốn tài nguyên và crash bất ngờ |
| **Shutdown** | Thoát đột ngột | `lifespan` context manager + `signal.signal(SIGTERM, ...)` | Hoàn thành các request đang chạy và đóng kết nối sạch sẽ, không làm người dùng nhận lỗi 502/504 khi redeploy |

---

## Part 2: Docker

### Exercise 2.1: Dockerfile questions (`02-docker/develop/Dockerfile`)

1. **Base image:** `python:3.11` (full Debian + Python distribution, kích thước lớn ~1 GB vì kèm compiler, thư viện hệ thống).
2. **Working directory:** `/app` (`WORKDIR /app`).
3. **Tại sao `COPY requirements.txt` trước `COPY . .`:** Docker cache từng layer theo thứ tự; nếu `requirements.txt` không đổi thì bước `RUN pip install` được tái sử dụng từ cache khi sửa source code, giúp rebuild nhanh hơn rất nhiều.
4. **CMD vs ENTRYPOINT khác nhau thế nào:**
   - `ENTRYPOINT` định nghĩa lệnh chính cố định của container (khó bị ghi đè, tham số truyền sau `docker run <image> ...` sẽ nối vào sau `ENTRYPOINT`).
   - `CMD` cung cấp lệnh hoặc tham số mặc định, dễ bị ghi đè hoàn toàn khi truyền command mới trong `docker run`.

### Exercise 2.2 – 2.4: Multi-stage build & Docker Compose stack

- **Cơ chế multi-stage trong `02-docker/production/Dockerfile`:**
  - **Stage 1 (`builder`, `python:3.11-slim`):** Cài `gcc`, `libpq-dev` và `pip install --no-cache-dir --user -r requirements.txt` vào `/root/.local`.
  - **Stage 2 (`runtime`, `python:3.11-slim`):** Không chứa `gcc`, `libpq-dev` hay apt cache; chỉ `COPY --from=builder /root/.local /home/appuser/.local`, copy code cần chạy, tạo user non-root `appuser`, khai báo `HEALTHCHECK` và `CMD`. Nhờ loại bỏ toàn bộ build toolchain và cache, image cuối giảm kích thước mạnh (thường từ ~1 GB xuống ~180–250 MB) và giảm bề mặt tấn công (attack surface).

- **Architecture diagram (`02-docker/production/docker-compose.yml`):**
```text
Client ──(:80 / :443)──▶ Nginx (reverse proxy, rate limit, security headers)
                            │
                            ▼ (network: internal)
                          Agent (:8000, depends_on redis & qdrant healthy)
                            ├──▶ Redis (:6379, session & rate limit)
                            └──▶ Qdrant (:6333, vector DB cho RAG)
```

> **Ghi chú môi trường:** Máy hiện tại chưa bật được WSL2 / Docker Desktop do Windows báo lỗi `0x800f0922` (`CBS_E_INSTALLERS_FAILED`) khi cài `VirtualMachinePlatform` & `Microsoft-Windows-Subsystem-Linux`, nên chưa build image để đo kích thước MB thực tế hay chạy `docker compose up` trực tiếp. Không ghi số đo ước lượng; sẽ bổ sung số MB đo thật ngay sau khi khắc phục Docker trên máy hoặc chạy trên máy có Docker.

---

## Part 3: Cloud Deployment

### Exercise 3.1 – 3.2: Triển khai & So sánh `railway.toml` vs `render.yaml`

- **URL public (Part 6):** *(Chưa deploy lên cloud trong bước offline này — xem cấu hình sẵn sàng deploy trong [06-lab-complete/railway.toml](06-lab-complete/railway.toml) và [06-lab-complete/render.yaml](06-lab-complete/render.yaml), hướng dẫn chi tiết trong [DEPLOYMENT.md](DEPLOYMENT.md)).*
- **So sánh `railway.toml` vs `render.yaml`:**

| Tiêu chí | `railway.toml` | `render.yaml` |
|----------|----------------|---------------|
| **Định dạng & Mục đích** | TOML, cấu hình build & deploy cho **1 service** hiện tại | YAML (Blueprint IaC), có thể khai báo **nhiều services** (web service + managed Redis) trong 1 file |
| **Cách build** | `builder = "DOCKERFILE"` (hoặc `"NIXPACKS"`), Railway tự detect `Dockerfile` | `runtime: docker` + `dockerfilePath: ./Dockerfile` (hoặc `runtime: python` + `buildCommand`) |
| **Health check** | `healthcheckPath = "/health"`, `healthcheckTimeout = 30` | `healthCheckPath: /health` |
| **Biến môi trường & Secret** | Không khai báo secret trong `railway.toml`; đặt qua `railway variables set` hoặc Dashboard | Khai báo ngay trong `envVars:` của Blueprint; giá trị thường dùng `value:`, secret dùng `generateValue: true` (tự sinh) hoặc `sync: false` (nhập trên Dashboard) |
| **Restart / Auto-deploy** | `restartPolicyType = "ON_FAILURE"`, `restartPolicyMaxRetries = 3` | `autoDeploy: true` (tự deploy khi push GitHub) |

### Exercise 3.3: GCP Cloud Run CI/CD Pipeline (`03-cloud-deployment/production-cloud-run/`)

Đọc `cloudbuild.yaml` và `service.yaml`, pipeline CI/CD trên Google Cloud Build chạy tuần tự 4 bước khi push code:
1. **`test` (`python:3.11-slim`):** Cài `requirements.txt` + `pytest` và chạy `pytest tests/ -v`; nếu test fail thì dừng pipeline ngay.
2. **`build` (`gcr.io/cloud-builders/docker`):** Build Docker image gắn tag `$COMMIT_SHA` và `latest` (tận dụng `--cache-from` từ image `latest`).
3. **`push` (`gcr.io/cloud-builders/docker`):** Đẩy các tag image lên Container Registry (`gcr.io/$PROJECT_ID/ai-agent`).
4. **`deploy` (`gcr.io/cloud-builders/gcloud`):** Deploy revision mới lên Cloud Run (`asia-southeast1`) với `min-instances=1`, `max-instances=10`, `512Mi` RAM, gắn biến môi trường và secret lấy từ Secret Manager (`--set-secrets`). File `service.yaml` mô tả cấu hình Knative Service tương ứng (concurrency 80, liveness `/health`, startup `/ready`, secret `secretKeyRef`).

---

## Part 4: API Security

### Exercise 4.1: API Key Authentication (`04-api-gateway/develop/app.py`)

- API key được kiểm tra trong dependency `verify_api_key` dùng `APIKeyHeader(name="X-API-Key", auto_error=False)`.
- Thiếu key → `401 Unauthorized`; sai key → `403 Forbidden` trong bản develop (`04-api-gateway/develop/app.py` dòng 49–53). Để rotate key không downtime, đặt key mới vào biến môi trường (hoặc hỗ trợ danh sách key hợp lệ trong giai đoạn chuyển tiếp rồi bỏ key cũ).

**Kết quả chạy thực tế (`AGENT_API_KEY=secret-key-123`):**
```text
No key -> HTTP 401: {"detail":"Missing API key. Include header: X-API-Key: <your-key>"}
Wrong key -> HTTP 403: {"detail":"Invalid API key."}
Valid key -> HTTP 200: {"question":"Hello","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
```

### Exercise 4.2 – 4.3: JWT Authentication & Rate Limiting (`04-api-gateway/production/`)

- **Thuật toán trong `rate_limiter.py`:** **Sliding Window Counter** dùng `collections.deque` lưu timestamp của từng request theo `user_id`, loại bỏ các timestamp cũ hơn `now - 60s` rồi đếm số phần tử còn lại.
- **Giới hạn:** User (`student`) = **10 requests/phút** (`rate_limiter_user`), Admin (`teacher`) = **100 requests/phút** (`rate_limiter_admin`). Để mở rộng cho admin, `app.py` chọn limiter dựa trên `role` trích xuất từ JWT payload (`rate_limiter_admin if role == "admin" else rate_limiter_user`).

**Kết quả chạy thực tế (login `POST /auth/token` với `student` / `demo123`, token đã che `<MASKED_JWT>`, gửi 12 requests liên tiếp tới `POST /ask`):**
```text
POST /auth/token -> HTTP 200 (Authorization: Bearer <MASKED_JWT>)
Req  1 -> HTTP 200
Req  2 -> HTTP 200
Req  3 -> HTTP 200
Req  4 -> HTTP 200
Req  5 -> HTTP 200
Req  6 -> HTTP 200
Req  7 -> HTTP 200
Req  8 -> HTTP 200
Req  9 -> HTTP 200
Req 10 -> HTTP 200
Req 11 -> HTTP 429 (Retry-After=59) {"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":59}}
Req 12 -> HTTP 429 (Retry-After=59) {"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":59}}
```

### Exercise 4.4: Cost Guard implementation

- Rate limit bảo vệ **tốc độ gọi** (chống spam/DDoS), còn Cost guard bảo vệ **ngân sách tiền** (vì 1 câu hỏi rất dài hoặc model đắt vẫn tiêu tốn nhiều token dù dưới rate limit).
- Trong Part 6 (`06-lab-complete/app/cost_guard.py`), cost guard được triển khai stateless qua Redis:
  1. Trước khi gọi LLM (`check_budget()`): đọc tổng chi phí hiện tại trong Redis theo key ngày UTC `cost:daily:YYYY-MM-DD`; nếu `>= DAILY_BUDGET_USD` thì chặn ngay bằng `HTTP 402 Payment Required`.
  2. Sau khi gọi LLM (`record_cost(input_tokens, output_tokens)`): tính chi phí theo đơn giá `PRICE_INPUT_PER_1K` ($0.00015) và `PRICE_OUTPUT_PER_1K` ($0.0006), cộng dồn nguyên tử vào Redis bằng `INCRBYFLOAT` và đặt `EXPIRE` 2 ngày.

---

## Part 5: Scaling & Reliability

### Exercise 5.1 – 5.2: Health checks & Graceful shutdown (`05-scaling-reliability/develop/`)

- **Phân biệt `/health` và `/ready`:**
  - `GET /health` (**Liveness probe**): kiểm tra process còn sống không; luôn trả `200` khi process hoạt động bình thường (kể cả khi dependency như Redis bị gián đoạn) để tránh orchestrator restart container liên tục gây cascade failure.
  - `GET /ready` (**Readiness probe**): kiểm tra app đã sẵn sàng nhận traffic chưa (đã khởi động xong và kết nối được Redis/DB); trả `503` khi chưa sẵn sàng để load balancer tạm ngừng gửi request vào instance đó.
- **Graceful shutdown:** Khi nhận `SIGTERM`, app ngừng nhận traffic mới (readiness chuyển false), chờ các request in-flight xử lý xong, đóng kết nối Redis trong `lifespan` shutdown, rồi thoát với exit code `0`.

**Kết quả chạy thực tế `05-scaling-reliability/develop/app.py`:**
```text
GET /health -> HTTP 200
{"status":"ok","uptime_seconds":0.3,"version":"1.0.0","environment":"development","timestamp":"2026-11-25T08:54:25.321534+00:00","checks":{"memory":{"status":"ok","used_percent":68.4}}}
GET /ready -> HTTP 200
{"ready":true,"in_flight_requests":1}
POST /ask?question=Hello -> HTTP 200
{"answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
```

### Exercise 5.3 – 5.5: Stateless design & Load balancing (`05-scaling-reliability/production/`)

- **Tại sao state trong RAM bị hỏng khi scale:** Khi chạy nhiều instance (ví dụ `--scale agent=3`) sau Nginx load balancer, request 1 có thể vào `agent-1` còn request 2 vào `agent-2`. Nếu lưu `conversation_history` hoặc rate-limit counter trong dict ở RAM, `agent-2` không thấy dữ liệu của `agent-1`.
- **Cách khắc phục trong `05-scaling-reliability/production/app.py`:** Lưu toàn bộ session vào Redis (`_redis.setex(f"session:{session_id}", ttl_seconds, ...)` và `_redis.get(...)`), nên mọi instance đều đọc/ghi chung một nguồn trạng thái.
- *(Ghi chú: Do Docker Desktop chưa khởi động được trên máy vì lỗi Windows `0x800f0922`, chưa chạy được `docker compose -p k5-day14-scaling up -d --build --scale agent=3` và `test_stateless.py` trên stack Docker; sẽ bổ sung output thực tế ngay khi có Docker.)*

---

## Part 6: Final Project (`06-lab-complete/`)

Đã hoàn thiện toàn bộ TODO trong `06-lab-complete/`:
- [app/config.py](06-lab-complete/app/config.py): đọc env vars bằng `os.getenv` + `load_dotenv()`, không hardcode secret.
- [app/redis_client.py](06-lab-complete/app/redis_client.py): kết nối Redis không ping lúc import, hàm `redis_healthy()` và `close_redis()`.
- [app/auth.py](06-lab-complete/app/auth.py): `verify_api_key` dùng `APIKeyHeader(auto_error=False)` + `secrets.compare_digest`, thiếu/sai → `401`.
- [app/rate_limiter.py](06-lab-complete/app/rate_limiter.py): sliding window 60s bằng Redis sorted set (`ZREMRANGEBYSCORE`, `ZCARD`, `ZADD`, `EXPIRE`), vượt giới hạn → `429` + `Retry-After: 60`.
- [app/cost_guard.py](06-lab-complete/app/cost_guard.py): theo dõi chi phí ngày trong Redis (`INCRBYFLOAT`), vượt `DAILY_BUDGET_USD` → `402`.
- [app/main.py](06-lab-complete/app/main.py): `JsonFormatter` xuất 1 JSON object/dòng, `lifespan` đóng Redis khi shutdown, `/health` luôn 200, `/ready` 200/503 theo Redis, `/ask` nối `verify_api_key` → `check_rate_limit` → `check_budget` → `llm_ask` → `record_cost`.
- [Dockerfile](06-lab-complete/Dockerfile), [docker-compose.yml](06-lab-complete/docker-compose.yml), [.dockerignore](06-lab-complete/.dockerignore), [.env.example](06-lab-complete/.env.example), [railway.toml](06-lab-complete/railway.toml), [render.yaml](06-lab-complete/render.yaml).

### Output `python check_production_ready.py --static-only`
*(Toàn bộ 28/28 kiểm tra tĩnh đều ✅, không có mục nào ❌; các mục runtime/Docker chưa chạy do chưa có Docker/Redis trên máy Windows)*:

```text
🔎 Kiểm tra D:\K5-L3A-DAY14-DuongTuanHung-2A202603416-Deployment-Benchmark-Observability\06-lab-complete
  ⏳ Kiểm tra tĩnh: file, Dockerfile, compose, config, code...

================================================================
  Production Readiness Check — Day 14 Lab
================================================================

⚠️  1. Dockerfile (multi-stage, < 500 MB)
     ✅ Dockerfile tồn tại
     ✅ requirements.txt tồn tại
     ✅ Multi-stage build (≥ 2 lệnh FROM)
     ✅ Base image gọn (slim / alpine / distroless) — stage cuối dùng python:3.11-slim
     ✅ Chạy bằng user non-root
     ✅ Có HEALTHCHECK
     ⚠️  Docker: build image thành công — chưa chạy (--static-only)
     ⚠️  Docker: image < 500 MB — chưa chạy (--static-only)
     ⚠️  Docker: container chạy được, GET /health → 200 — chưa chạy (--static-only)

✅ 2. docker-compose.yml (agent + redis)
     ✅ docker-compose.yml tồn tại
     ✅ Có service agent (build từ Dockerfile) + redis — services: agent, redis — đọc bằng PyYAML
     ✅ Service agent kết nối redis (REDIS_URL + depends_on)

✅ 3. .dockerignore
     ✅ .dockerignore tồn tại và có nội dung
     ✅ .dockerignore loại trừ .env (secrets)
     ✅ .dockerignore loại trừ __pycache__, venv

⚠️  4. Health check endpoint (GET /health)
     ✅ Code có route /health
     ⚠️  Khi chạy: GET /health → 200 — chưa chạy (--static-only)

⚠️  5. Readiness endpoint (GET /ready)
     ✅ Code có route /ready
     ⚠️  Khi chạy: GET /ready → 200 — chưa chạy (--static-only)
     ⚠️  Khi chạy: Redis mất kết nối → /ready 503 (còn /health vẫn 200) — chưa chạy (--static-only)

⚠️  6. API Key authentication
     ✅ Code đọc header X-API-Key
     ⚠️  Khi chạy: thiếu / sai API key → 401 — chưa chạy (--static-only)
     ⚠️  Khi chạy: API key đúng → 200 — chưa chạy (--static-only)

⚠️  7. Rate limiting
     ✅ Code trả HTTP 429 khi vượt giới hạn
     ⚠️  Khi chạy: vượt giới hạn → 429 — chưa chạy (--static-only)
     ⚠️  Khi chạy: state nằm trong Redis — restart agent vẫn bị 429 — chưa chạy (--static-only)

⚠️  8. Cost guard
     ✅ Code trả HTTP 402 khi hết budget
     ⚠️  Khi chạy: hết budget → 402 — chưa chạy (--static-only)

⚠️  9. Config từ environment variables
     ✅ app/config.py đọc biến môi trường
     ✅ .env.example liệt kê đủ biến cấu hình
     ✅ .env nằm trong .gitignore
     ✅ Không hard-code secret trong code
     ⚠️  Khi chạy: agent dùng AGENT_API_KEY và RATE_LIMIT_PER_MINUTE từ env — chưa chạy (--static-only)

⚠️  10. Structured logging
     ✅ Code ghi log dạng JSON
     ⚠️  Khi chạy: mọi dòng log của app là JSON hợp lệ — chưa chạy (--static-only)

⚠️  11. Graceful shutdown
     ✅ Code xử lý SIGTERM / lifespan shutdown
     ⚠️  Khi chạy: SIGTERM lúc đang có request → request vẫn 200, process tự thoát — chưa chạy (--static-only)
     ⚠️  Docker: `docker stop` tắt êm (exit code 0, < 10s) — chưa chạy (--static-only)

✅ 12. Public URL ready (Railway / Render config)
     ✅ Có railway.toml hoặc render.yaml (không chỉ toàn comment)
     ✅ railway.toml: builder + healthcheckPath = "/health"
     ✅ render.yaml: web service + healthCheckPath /health
     ✅ render.yaml: secret không ghi thẳng giá trị (generateValue / sync: false)
     ✅ App lắng nghe theo biến PORT do platform cấp

================================================================
  📋 Checklist Deliverable
     ⚠️  Dockerfile (multi-stage, < 500 MB)
     ✅ docker-compose.yml (agent + redis)
     ✅ .dockerignore
     ⚠️  Health check endpoint (GET /health)
     ⚠️  Readiness endpoint (GET /ready)
     ⚠️  API Key authentication
     ⚠️  Rate limiting
     ⚠️  Cost guard
     ⚠️  Config từ environment variables
     ⚠️  Structured logging
     ⚠️  Graceful shutdown
     ✅ Public URL ready (Railway / Render config)
----------------------------------------------------------------
  Result: 3/12 tiêu chí đạt · 28/28 checks passed
```

**Kiểm thử runtime cục bộ với `TestClient` + in-memory Redis stub:**
- `GET /health` → `200`, `GET /ready` → `200` (khi Redis up) và `503` (khi Redis down, `/health` vẫn `200`).
- `POST /ask` không có key / sai key → `401`, đúng key → `200`.
- Cost guard với `DAILY_BUDGET_USD=0.00001` → trả `402` ngay khi vượt ngân sách.
- Rate limit với `RATE_LIMIT_PER_MINUTE=5` → trả `429` sau khi đủ 5 request.
- Mọi dòng log của logger `app` đều parse được thành JSON hợp lệ (`startup`, `request`, `llm_call`, `graceful_shutdown`).

---

## AI log

1. **Hỏi gì:** Cách hoàn thiện các `TODO` trong `06-lab-complete/` đạt chuẩn 12-Factor, stateless qua Redis (sliding window sorted set, cost guard, JSON logging, multi-stage Dockerfile, compose, railway/render) và cách chẩn đoán lỗi bật WSL2/Docker trên Windows (`0x800f0922`).
2. **Nhận gì:** Gợi ý cấu trúc từng module `app/config.py`, `app/redis_client.py`, `app/auth.py`, `app/rate_limiter.py`, `app/cost_guard.py`, `app/main.py`, `Dockerfile` multi-stage dùng `PYTHONUSERBASE`, `docker-compose.yml`, workflow CI `.github/workflows/eval.yml`, cùng 2 entry bổ sung cho `KNOWLEDGE_BASE` (`hpa/kubernetes/autoscal` và `jwt`).
3. **Tự sửa & tự kiểm tra thế nào:**
   - Tự chỉnh `app/config.py` fallback `DAILY_BUDGET_USD` / `MONTHLY_BUDGET_USD`, dùng `secrets.compare_digest` trong `auth.py`, và pipeline Redis trong `rate_limiter.py` & `cost_guard.py`.
   - Tự chạy `check_production_ready.py --static-only` (28/28 checks passed), viết test `TestClient` kiểm tra đủ 200/401/402/429/503 + JSON logs, chạy trực tiếp Part 1, Part 4, Part 5 và toàn bộ load test / eval Part 7 (`eval_v2_fixed.json` đạt `23/23 = 100.0%`, 0 regression).
