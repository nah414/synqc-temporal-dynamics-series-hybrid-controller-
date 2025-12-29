# Hosted mode reference (SynQc)

This repo currently runs locally with:

- `api` exposed on `:8001`
- `web` exposed on `:8080`
- UI calls `http://localhost:8001` by default **only when opened via `file://`**

For **hosted consumer mode**, the goal is:

- expose **only one public origin** (the UI origin)
- UI calls `/api/*` on the same origin (no CORS)
- enforce end-user login at the edge (no API keys pasted in the browser)
- keep API + Redis internal-only

## What the provided hosted stack does

`docker-compose.hosted.yml` adds:

- `edge` (nginx):
  - serves `./web` static files
  - proxies `/api/*` -> `api:8001/*`
  - enforces auth via `auth_request` -> `oauth2-proxy`
  - supports SSE + WebSocket upgrade

- `oauth2-proxy`:
  - handles OIDC login
  - issues a session cookie
  - provides identity headers to nginx (`X-Auth-Request-User`, `X-Auth-Request-Email`)

## Quick start

1) Copy env template:

```bash
cp deploy/hosted/.env.hosted.example deploy/hosted/.env.hosted
python scripts/generate_hosted_secrets.py
# paste OAUTH2_PROXY_COOKIE_SECRET into deploy/hosted/.env.hosted
```

2) Start hosted stack:

```bash
docker compose --env-file deploy/hosted/.env.hosted -f docker-compose.hosted.yml up -d --build
```

3) Open:

- `http://localhost:8080/` (UI)
- API is reachable only through the edge at `http://localhost:8080/api/...`

## Recommended production hardening

- Put the edge behind HTTPS and a known domain.
- Set:
  - `OAUTH2_PROXY_COOKIE_SECURE=true`
  - `OAUTH2_PROXY_REDIRECT_URL=https://yourdomain.com/oauth2/callback`
- Consider blocking `/api/docs` & `/api/openapi.json` at the edge if you don't want to publish internals.
- Disable URL-query token ingestion in the UI for hosted mode:
  - allow `?api_key=` / `?token=` only for `file://` or explicit dev flag
- Optional defense-in-depth:
  - add backend middleware that requires `X-Auth-Request-*` headers
    (`SYNQC_REQUIRE_EDGE_IDENTITY=true`)

