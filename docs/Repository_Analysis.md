# SynQc TDS Repository — Safety & Effectiveness Review

## Scope and context
This review covers the SynQc Temporal Dynamics Series frontend (`web/index.html`), backend (`backend/synqc_backend`), operational assets (`backend/ops`), and developer tooling. It summarizes architecture, safety controls, observed risks, and recommended next steps for a production-ready deployment.

## Architecture overview
### Backend (FastAPI + engine)
- **Configuration & guardrails:** Environment-backed `SynQcSettings` defines shot ceilings, session budgets, API-key enforcement, CORS allowlist, Redis integration, and metrics settings. 【F:backend/synqc_backend/config.py†L9-L58】
- **Execution engine:** `SynQcEngine` clamps shot budgets, enforces per-session quotas via `BudgetTracker`, adjusts KPI status when guardrails trigger, and stores runs with timestamps. 【F:backend/synqc_backend/engine.py†L28-L99】
- **Budget tracking:** Redis-backed atomic reserve script (with thread-safe memory fallback) guards shot quotas and exposes health metadata for monitoring. 【F:backend/synqc_backend/budget.py†L9-L111】
- **Hardware abstraction:** Registry includes a local simulator plus provider shells (AWS, IBM, Azure, IonQ, Rigetti); provider classes are structured for live SDK wiring but currently simulate KPIs. 【F:backend/synqc_backend/hardware_backends.py†L13-L182】【F:backend/synqc_backend/hardware_backends.py†L184-L265】
- **API surface:** FastAPI app exposes health, hardware discovery, run submission/polling, and recent history endpoints. API key enforcement is baked into all data/execution routes, and CORS is restricted to configured origins. 【F:backend/synqc_backend/api.py†L30-L119】【F:backend/synqc_backend/api.py†L144-L218】
- **Background queue & metrics:** Thread-pool job queue executes runs; Prometheus exporter publishes budget/queue health on a background loop. 【F:backend/synqc_backend/jobs.py†L27-L115】【F:backend/synqc_backend/metrics.py†L12-L131】

### Frontend (single-file console)
- **Backend wiring:** Detects backend base URL (query override → file:// localhost → host:8001), caches health/hardware/recents, and clamps shot budgets based on `/health` guardrails. 【F:web/index.html†L1188-L1319】【F:web/index.html†L1592-L1664】
- **Preset execution flow:** Runs presets via `POST /experiments/run`, updates KPI visuals, and refreshes history/hardware lists after completion. 【F:web/index.html†L1741-L1774】
- **Data views:** Experiments and hardware tabs render read-only tables/cards from cached API responses with filter pills. 【F:web/index.html†L1520-L1679】【F:web/index.html†L1682-L1739】
- **Safety in rendering:** Chat/log text uses DOM text nodes (no `innerHTML`) to mitigate XSS risk. 【F:web/index.html†L1844-L1899】

### Operational tooling
- **Load test harness:** `backend/scripts/load_test.py` drives concurrent submissions, checks `/health` and Prometheus metrics, and fails in strict mode if queues fail to drain or Redis disconnects. 【F:backend/scripts/load_test.py†L1-L204】
- **Monitoring configs:** Sample Prometheus/Alertmanager manifests in `backend/ops` align with exported queue/budget metrics.

## Safety, reliability, and effectiveness assessment
**Strengths**
- Shot guardrails and per-session budgets are enforced before backend execution, with Redis-backed atomicity for multi-worker safety. 【F:backend/synqc_backend/engine.py†L41-L87】【F:backend/synqc_backend/budget.py†L49-L111】
- API key enforcement is centralized; missing keys return 401/500 rather than silently running. CORS defaults are restrictive. 【F:backend/synqc_backend/api.py†L59-L119】
- Metrics and health endpoints expose queue depth, budget backend status, and configuration, enabling operational observability and alerting. 【F:backend/synqc_backend/api.py†L97-L119】【F:backend/synqc_backend/metrics.py†L12-L131】
- Frontend respects backend guardrails (shot caps, allowed hardware list) and keeps UI interactions read-only outside run submission. 【F:web/index.html†L1592-L1664】【F:web/index.html†L1520-L1739】

**Gaps / risks**
- Backend does not enforce `allow_remote_hardware` on execution paths; callers can submit runs targeting provider shells even when discovery filtering hides them. Add a server-side check before dispatching to remote backends. 【F:backend/synqc_backend/api.py†L122-L142】【F:backend/synqc_backend/engine.py†L68-L99】
- API key requirement is enabled by default, but the frontend never sends `X-Api-Key`, so a secured backend will reject UI traffic unless the requirement is disabled. Propagate the key from UI configuration or allow token injection. 【F:backend/synqc_backend/api.py†L59-L119】【F:web/index.html†L1188-L1237】
- In-memory budget tracker lacks TTL eviction, so long-running dev sessions may never reclaim quota without process restart; Redis mode applies TTL correctly. Consider expiring in-memory entries on access. 【F:backend/synqc_backend/budget.py†L49-L111】
- Metrics server binds immediately on import and has no auth; ensure network exposure is controlled (e.g., firewalls, sidecar auth) in shared environments. 【F:backend/synqc_backend/api.py†L30-L45】【F:backend/synqc_backend/metrics.py†L12-L69】
- Provider backends are simulation placeholders; live SDK wiring, credential handling, and result validation remain to be implemented before production use. 【F:backend/synqc_backend/hardware_backends.py†L98-L182】
- Job queue is in-memory with no persistence or cancellation; process restarts drop in-flight runs, and long jobs cannot be aborted. 【F:backend/synqc_backend/jobs.py†L27-L115】
- Health/metrics endpoints reveal configuration details (CORS, redis_url) that may be sensitive; consider redacting or scoping in production. 【F:backend/synqc_backend/api.py†L97-L119】

**Effectiveness**
- The simulator and provider shells return KPI bundles with status logic, enabling UI visualization and guardrail testing without hardware. 【F:backend/synqc_backend/hardware_backends.py†L40-L182】
- UI ties KPI values to animations and clear status pills, improving operator feedback. 【F:web/index.html†L1287-L1319】【F:web/index.html†L1520-L1554】
- Load-test script plus Prometheus exporters provide a path to validate queue drain and budget stability under concurrency. 【F:backend/scripts/load_test.py†L1-L204】

## Recommendations (next steps)
1) Enforce `allow_remote_hardware` in the backend request path (reject non-sim targets when disabled) and return a 403 to callers. 【F:backend/synqc_backend/api.py†L122-L142】【F:backend/synqc_backend/engine.py†L68-L99】
2) Add API-key propagation in the frontend (configurable header) or toggle `require_api_key` via deployment config to avoid UI/Backend mismatch. 【F:backend/synqc_backend/api.py†L59-L119】【F:web/index.html†L1188-L1237】
3) Implement TTL eviction for in-memory budget tracking to mirror Redis behavior and prevent quota exhaustion in dev scenarios. 【F:backend/synqc_backend/budget.py†L49-L111】
4) Gate metrics/health exposure behind auth or network policy when running outside isolated environments. 【F:backend/synqc_backend/metrics.py†L12-L69】【F:backend/synqc_backend/api.py†L97-L119】
5) Replace provider simulation stubs with live SDK integrations plus error-handling, result validation, and timeout controls; add tests per provider. 【F:backend/synqc_backend/hardware_backends.py†L98-L182】
6) Consider durable queueing or at least graceful shutdown hooks to avoid lost runs during process restarts; add cancellation support for long-running jobs. 【F:backend/synqc_backend/jobs.py†L27-L115】

## Testing performed
- `python -m compileall backend/synqc_backend`
