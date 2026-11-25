# Deployment Information

## Public URL
*(Pending Railway deploy — đã cấu hình đầy đủ [06-lab-complete/railway.toml](06-lab-complete/railway.toml), [06-lab-complete/render.yaml](06-lab-complete/render.yaml) và [06-lab-complete/Dockerfile](06-lab-complete/Dockerfile))*

## Platform
Railway (Docker builder via `06-lab-complete/railway.toml` + managed Redis)

## Cách deploy nhanh lên Railway

```bash
npm i -g @railway/cli
cd 06-lab-complete
railway login
railway init
# Tạo thêm database Redis trong project trên Railway Dashboard (Add -> Database -> Redis)
railway variables set ENVIRONMENT=production RATE_LIMIT_PER_MINUTE=10 DAILY_BUDGET_USD=1.0 AGENT_API_KEY=<YOUR_SECRET_KEY> REDIS_URL=<RAILWAY_REDIS_URL>
railway up
railway domain
```

## Test Commands (CP6 Verification)

Thay `<PUBLIC_URL>` và `<YOUR_KEY>` bằng URL public và `AGENT_API_KEY` đã cấu hình trên Railway:

```bash
BASE="https://<PUBLIC_URL>"
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
  -d '{"user_id":"test","question":"Hello"}'
```

## Environment Variables Set
- `PORT` (Railway tự inject)
- `ENVIRONMENT` (`production`)
- `REDIS_URL` (kết nối tới Railway Redis service)
- `AGENT_API_KEY` (đặt trên Railway Dashboard/CLI, không commit vào Git)
- `RATE_LIMIT_PER_MINUTE` (`10`)
- `DAILY_BUDGET_USD` (`1.0`)
- `LOG_LEVEL` (`INFO`)

## Screenshots
- `screenshots/dashboard.png` *(chụp sau khi deploy Railway)*
- `screenshots/running.png` *(chụp sau khi deploy Railway)*
- `screenshots/test.png` *(chụp sau khi chạy 4 lệnh CP6)*
