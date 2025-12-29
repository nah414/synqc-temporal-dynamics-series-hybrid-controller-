# Hosted Demo Playbook

A lightweight hosted demo lets prospects click through the SynQc TDS console without installing anything locally. The frontend is static (single `web/index.html`), so hosting only requires a static site target and a reachable backend API.

## Prerequisites
- A backend deployment accessible from the internet (e.g., a small VM or container host running `uvicorn synqc_backend.api:app`).
- A DNS name for the frontend (e.g., `demo.example.com`).
- An explicit CORS allowlist on the backend that includes the frontend origin.

## Quick publish steps (GitHub Pages example)
1. Copy the frontend into a Pages branch:
   ```bash
   git checkout --orphan gh-pages
   git rm -rf .
   mkdir -p web
   cp -r ../web/* web/
   echo "" > .nojekyll
   git add web .nojekyll
   git commit -m "Publish SynQc TDS demo"
   git push origin gh-pages
   ```
2. Enable GitHub Pages for the repository and point it at the `gh-pages` branch.
3. Configure the backend with a stable URL (e.g., `https://api.example.com`) and set the CORS allowlist:
   ```bash
   export SYNQC_CORS_ALLOW_ORIGINS=https://demo.example.com
   uvicorn synqc_backend.api:app --host 0.0.0.0 --port 8001
   ```
4. Update the frontend default API pointer inside the hosted page by adding a query param to the published URL, e.g., `https://demo.example.com/?api=https://api.example.com`.

## Health and monitoring
- Run `backend/scripts/quickstart_health_check.py` against the hosted API before opening access to prospects to ensure `/health`, Redis, and simulator presets are functioning.
- Keep `SYNQC_REQUIRE_API_KEY` enabled for public deployments and distribute keys separately or embed a demo key via the `?apiKey=` query parameter on the hosted URL when appropriate.

## Reference ingress + control plane flow
```
Internet
  |
  v
[ Edge / Nginx ]  (public: 80/443)
  |         \
  |          \  auth_request
  |           -> [ oauth2-proxy ] (OIDC login)
  |
  +--> serves static UI: /
  |
  +--> proxies API: /api/*  ---> [ synqc-api ] (private)
                             |
                             +--> Redis (queue)
                             +--> Postgres (durable store)
                             |
                             +--> [ synqc-worker ] (private) --> Providers
```

## Notes
- The hosted frontend uses only static assets; the only runtime dependency is the backend API you point it at.
- Rebuilds are fast—updating the `gh-pages` branch or your chosen static host is enough to refresh the demo.
