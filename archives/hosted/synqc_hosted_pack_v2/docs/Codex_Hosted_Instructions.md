# Codex instructions: Hosted hardening (copy/paste)

Goal: Make hosted mode safe + simple for users who don't want to run locally.

You have an existing docker-compose describing:
- api (FastAPI on :8001, currently published)
- worker
- redis
- web (static on :8080)

We will add a hosted compose that:
- publishes ONLY one public service (nginx edge)
- keeps api+redis internal only
- uses oauth2-proxy for OIDC login (cookie-based)
- proxies /api/* -> api:8001/* (strip /api prefix)
- supports SSE and WebSockets (Shor live channels)

---

## Step 1: Add hosted files

Create directories:
- deploy/hosted/edge
- deploy/hosted  (for env templates)
- scripts
- docs

Add these files with the exact contents from this PR:
- docker-compose.hosted.yml
- deploy/hosted/.env.hosted.example
- deploy/hosted/edge/Dockerfile
- deploy/hosted/edge/nginx.conf
- scripts/generate_hosted_secrets.py
- docs/Hosted_Mode.md

Optional defense-in-depth middleware template:
- backend/synqc_backend/security/edge_identity.py

---

## Step 2: Verify frontend uses same-origin /api

Open web/index.html and confirm:

- `getApiBase()` uses `window.location.origin + "/api"` when served over http(s).
- `file://` falls back to `http://localhost:8001`.

This is already present in the provided UI shell.

---

## Step 3: Disable query-string auth by default in hosted mode

Security issue: current UI accepts `?api_key=...` / `?token=...` and stores them in localStorage.
For a hosted consumer product, you generally do NOT want secrets in URLs or localStorage.

Implement:

- Add a guard like:

```js
const ALLOW_URL_AUTH = (location.protocol === "file:" || window.SYNQC_ALLOW_URL_AUTH === true);
```

- Only run the query-string token ingestion if `ALLOW_URL_AUTH` is true.
- Default `window.SYNQC_ALLOW_URL_AUTH` to false.

Result:
- local dev with `file://` still works
- hosted deployments ignore accidental URL tokens

---

## Step 4: Hosted compose must not publish api/redis ports

In docker-compose.hosted.yml:
- api must use `expose: ["8001"]` and NO `ports:` mapping
- redis must have NO `ports:` mapping

Only edge publishes a port.

---

## Step 5: Auth gate at nginx edge

In deploy/hosted/edge/nginx.conf:

- protect `/` and `/api/*` with:
  - `auth_request /oauth2/auth`
  - `error_page 401 = /oauth2/start?rd=$request_uri`

- proxy `/oauth2/*` to `oauth2-proxy:4180`

Also ensure:

- `/api/shor/runs/stream` has `proxy_buffering off` and long `proxy_read_timeout`
- `/api/shor/runs/ws` works (Upgrade / Connection headers)
- experiment runs are rate-limited (harder throttle than reads)

---

## Step 6: Smoke tests

Run:

```bash
cp deploy/hosted/.env.hosted.example deploy/hosted/.env.hosted
python scripts/generate_hosted_secrets.py
# paste OAUTH2_PROXY_COOKIE_SECRET into deploy/hosted/.env.hosted

docker compose --env-file deploy/hosted/.env.hosted -f docker-compose.hosted.yml up -d --build
```

Check:

- `http://localhost:8080` redirects to login / provider
- after login, UI loads and `/api/health` works
- "Run preset" -> `/api/experiments/run` succeeds
- Shor tab:
  - `/api/shor/health` loads
  - live runs: SSE or WS stream works

---

## Step 7 (optional defense-in-depth): Require identity headers in the API

Enable:

- Add middleware from `backend/synqc_backend/security/edge_identity.py`
- Set `SYNQC_REQUIRE_EDGE_IDENTITY=true` for hosted deployments

This ensures:
- even if someone reaches the API container directly, calls are rejected
  unless they come via the edge (which injects identity headers).

