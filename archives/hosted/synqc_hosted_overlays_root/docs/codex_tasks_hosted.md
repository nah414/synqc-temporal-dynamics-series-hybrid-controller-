# Codex task list: Hosted hardening (OIDC + edge proxy)

Use this as a checklist / prompt for Codex.

## Goal

Turn the repo into a safer hosted app:

- UI served from nginx edge
- `/api/*` reverse-proxied to internal `api` service
- no public exposure of `api`/`redis`
- OIDC login via oauth2-proxy
- minimal CSRF + rate limiting at the edge
- release workflow builds/pushes images

## Tasks

### 1) Add hosted deployment overlay files
- Create `deploy/hosted/docker-compose.hosted.yml` (see overlay)
- Create `deploy/hosted/nginx/default.conf` (see overlay)
- Create `deploy/hosted/.env.hosted.example` (see overlay)
- Create `deploy/hosted/README.md` (see overlay)
- Create `scripts/generate_hosted_secrets.py` (see overlay)

### 2) Ensure the web image supports nginx config override
Option A (fast, dev-friendly):
- Keep `volumes:` mount in compose (already in overlay)

Option B (release-friendly):
- Modify `web/Dockerfile` so it copies `deploy/hosted/nginx/default.conf` into `/etc/nginx/conf.d/default.conf` when building a *hosted* image.
- Simplest approach:
  - add `web/Dockerfile.hosted` that `FROM` your existing nginx base and copies the hosted config
  - in compose hosted, point at `dockerfile: Dockerfile.hosted`

### 3) UI hardening: disable URL credential seeding in hosted mode
- Patch `web/index.html` so `?api_key=` / `?token=` are only persisted when:
  - `file://` OR
  - `localhost/127.0.0.1`
- Keep the “URL cleanup” behavior so secrets are removed from the address bar.

### 4) Add a release workflow to push images to GHCR
- Add `.github/workflows/release-images.yml` (see overlay)
- Confirm repo has Packages enabled
- Tag a release `v0.1.0` and confirm images appear in GHCR

### 5) Verify runtime behavior
- `docker compose -f deploy/hosted/docker-compose.hosted.yml ... up`
- Confirm:
  - hitting `/` redirects to IdP login
  - after login, UI loads
  - UI calls to `/api/health` succeed (cookie-based auth)
  - direct access to `:8001` is impossible (no published port)

### 6) Stretch: backend identity support (for per-user history)
- In the API, read `X-Auth-Request-Email` (from oauth2-proxy) and attach it to:
  - experiment records
  - shor runs
- Update list endpoints to filter to the calling user.
- Add an admin override if needed.

(Do this after the edge auth is working; it’s a bigger change because it touches persistence + schemas.)
