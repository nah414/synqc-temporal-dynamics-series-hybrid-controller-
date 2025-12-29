# SynQc hosted deployment (SaaS edge + OIDC auth)

This overlay converts your current `docker-compose.yml` into a hosted setup that is safer for end users:

- **No direct API/Redis exposure to the public internet**
- **OIDC login** via `oauth2-proxy`
- **Nginx edge** serves the UI and reverse-proxies `/api/*` to the internal API
- Basic **rate limiting** + **CSRF-origin checks** on API calls

## Files

- `deploy/hosted/docker-compose.hosted.yml`
- `deploy/hosted/nginx/default.conf`
- `deploy/hosted/.env.hosted.example`
- `scripts/generate_hosted_secrets.py`

## Quick start (hosted)

1) Create env file:

```bash
cp deploy/hosted/.env.hosted.example deploy/hosted/.env.hosted
python scripts/generate_hosted_secrets.py
# paste output into deploy/hosted/.env.hosted
```

2) Configure your IdP (Auth0/Okta/Keycloak/Cognito/etc.)

You need:

- `OAUTH2_PROXY_OIDC_ISSUER_URL`
- `OAUTH2_PROXY_CLIENT_ID`
- `OAUTH2_PROXY_CLIENT_SECRET`
- `OAUTH2_PROXY_REDIRECT_URL` (must be `https://YOUR_DOMAIN/oauth2/callback`)

3) Boot:

```bash
docker compose -f deploy/hosted/docker-compose.hosted.yml   --env-file deploy/hosted/.env.hosted   up -d --build
```

4) Visit `https://YOUR_DOMAIN`

You should be redirected to `/oauth2/start` and then to your IdP.

## What changed vs your current compose?

- `api` removed `ports:`, replaced with `expose:`.
- `redis` removed `ports:`.
- `web` now mounts an nginx config that:
  - enforces auth for `/` and `/api/*`
  - proxies `/api/*` to `api:8001`
  - returns JSON `401` for unauthenticated API calls (instead of redirect HTML)

## Next upgrades (strongly recommended)

- Move from single-tenant SQLite to **Postgres** for reliability + multi-user isolation.
- Make the backend **use the auth identity** from `X-Auth-Request-Email`:
  - attach `user_id` to runs
  - filter `/experiments/recent` by user
- Add billing/quotas, per-user shot budgets, and provider-credential vaulting.
