# Deployment Information

## Public URL
https://ai-agent-production-968b6e9d.up.railway.app

## Platform
Railway (Docker builder via [06-lab-complete/railway.toml](06-lab-complete/railway.toml) + managed Redis service)

## Test Commands (CP6 Verification)

Thay `<YOUR_KEY>` bằng `AGENT_API_KEY` đã cấu hình trên Railway:

```bash
BASE="https://ai-agent-production-968b6e9d.up.railway.app"
AGENT_API_KEY="<YOUR_KEY>"

# 1. Health check (Expected: 200)
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"

# 2. Readiness check (Expected: 200 when Redis connected)
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"

# 3. Auth check without key (Expected: 401)
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H 'Content-Type: application/json' \
  -d '{"question":"Hello"}'

# 4. Ask with valid API key (Expected: 200)
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: $AGENT_API_KEY" \
  -d '{"user_id":"test","question":"What is deployment?"}'
```

### Kết quả kiểm tra thực tế
```text
1. GET /health              -> 200  {"status":"ok","environment":"production","uptime_seconds":22.8}
2. GET /ready               -> 200  {"status":"ready","redis":"ok"}
3. POST /ask (no key)       -> 401  {"detail":"Invalid or missing API key"}
4. POST /ask (valid key)    -> 200  {"question":"What is deployment?","answer":"Deployment là quá trình đưa code từ máy bạn lên server để người khác dùng được.","usage":{"input_tokens":4,"output_tokens":19,"cost_usd":1.2e-05}}
```

## Environment Variables Set
- `PORT` (Railway tự inject)
- `ENVIRONMENT` (`production`)
- `REDIS_URL` (`${{Redis.REDIS_URL}}` trỏ tới Railway Redis service)
- `AGENT_API_KEY` (đặt trên Railway, không commit vào Git)
- `RATE_LIMIT_PER_MINUTE` (`10`)
- `DAILY_BUDGET_USD` (`1.0`)
- `LOG_LEVEL` (`INFO`)

## Screenshots
- [Deployment dashboard](screenshots/dashboard.png)
- [Service running](screenshots/running.png)
- [Test results](screenshots/test.png)
