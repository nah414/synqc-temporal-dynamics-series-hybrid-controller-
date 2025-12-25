# SynQc TDS Backend v0.1

Backend API and engine for the **SynQc Temporal Dynamics Series (SynQc TDS)** console.

This package provides:

- A FastAPI application with endpoints for running **SynQc experiment presets**
  (health diagnostics, latency characterization, backend comparison, DPD demo).
- A `SynQcEngine` that:
  - Validates and normalizes requests,
  - Applies basic **safety and shot-limit guardrails**,
  - Routes to a hardware backend (local simulator by default),
  - Computes **KPIs** (fidelity, latency, backaction, shot usage, status).
- A simple in-memory (with optional JSON) **experiment store** for recent runs.
- A **hardware target registry** pre-populated with five production provider shells
  (AWS Braket, IBM Quantum, Microsoft Azure Quantum, IonQ Cloud, Rigetti Forest)
  plus the local simulator so consumers can point SynQc TDS at real hardware stacks
  while retaining the same API surface.

> This is a structured skeleton meant to be stable and extensible.
> Real hardware integration (AWS Braket, IBM Qiskit, Azure Quantum, IonQ native, Rigetti SDK)
> should be plugged into `synqc_backend.hardware_backends` in a controlled way, without
> touching the API contracts.

### Qiskit integration (Aer simulators or IBM Quantum)

- Install optional dependencies with `pip install -e .[qiskit]` to pull in `qiskit`, `qiskit-aer`, and `qiskit-ibm-runtime`.
- Point a SynQc backend id at a Qiskit backend by setting `SYNQC_QISKIT_BACKEND_<BACKEND_ID>`.
  - Example: `SYNQC_QISKIT_BACKEND_IBM_QUANTUM=aer_simulator` wires IBM Quantum runs through Qiskit's Aer simulator.
  - Any backend name resolvable by `qiskit_aer.Aer.get_backend` is supported; the engine will still enforce shot budgets.
- Optional cloud backdoor: if you have IBM Quantum Runtime credentials, set `SYNQC_QISKIT_RUNTIME_TOKEN`,
  `SYNQC_QISKIT_RUNTIME_CHANNEL` (e.g., `cloud`), and/or `SYNQC_QISKIT_RUNTIME_INSTANCE` to resolve the backend from
  IBM Quantum Runtime instead of Aer. The same backend id mapping is used, so you can toggle between local and cloud
  by changing environment variables.
- When the variable is present, the engine swaps in the Qiskit provider client for that backend id so KPI extraction can use
  live Qiskit counts instead of synthetic draws. Leave the variable unset to continue using the built-in simulator.

---

## Requirements

- Python **3.12+**
- Recommended: create a virtual environment. In restricted networks, pre-install
  `wheel` so editable installs do not fail when the build backend tries to build
  metadata. Once `wheel` is available, use the helper script to bypass build
  isolation so `pip` reuses the system `setuptools`/`wheel` instead of trying to
  download them through a blocked proxy.
- The dev container and CI both use `backend/requirements.lock` to pre-build
  wheels (core runtime + Qiskit + Braket + IonQ extras), reducing proxy friction
  and keeping installs repeatable. If you update dependencies, rebuild the wheel
  cache (`pip wheel -r backend/requirements.lock`) or regenerate the lock list to
  keep the image and automation consistent.

```bash
python3.12 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install wheel
./scripts/dev_install.sh  # uses PIP_NO_BUILD_ISOLATION=1 under the hood
```

Or install just the runtime deps:

```bash
pip install fastapi uvicorn[standard] pydantic numpy redis prometheus-client
```

For the optional load-test helper, install the `dev` extra to pull in `httpx`
and `wheel` (the latter ensures `bdist_wheel` is available during editable
installs even when your network blocks package indexes):

```bash
pip install -e .[dev]
# If your proxy blocks build isolation downloads, prefer the helper script:
# ./scripts/dev_install.sh
```

---

## How to Run the Backend (Local)

From the project root (where this README and `pyproject.toml` live):

```bash
uvicorn synqc_backend.api:app --host 0.0.0.0 --port 8001 --reload
```

Run the dedicated worker in a separate process when you want API responsiveness and scalable execution threads:

```bash
python -m synqc_backend.worker
```

Then you can access:

- API docs: http://localhost:8001/docs
- Health check: `GET /health`
- Hardware targets: `GET /hardware/targets`
- Engineering controls: `GET/POST /controls/profile`
- Submit experiment run: `POST /runs` (or legacy `POST /experiments/run`)
- Poll run status: `GET /runs/{id}`
- Load test helper: `python backend/scripts/load_test.py` (prefers cached `httpx` wheel in `backend/synqc_backend/vendor/httpx_wheels/`)
  - In CI, set `SYNQC_HTTPX_VENDOR=backend/synqc_backend/vendor/httpx_wheels/` (or replace the cached wheel with the official package) so the load test uses the real client rather than the stub.
  - Keep the vendored wheel current (e.g., update to the latest httpx patch release when bumping dependencies) to stay aligned with FastAPI/Starlette testclient expectations.

### Run with Docker Compose (API + Redis + Web)

For containerized deployments that need the API, Redis, and frontend to talk to each other in real time, use the provided `docker-compose.yml` from the repo root. Copy the sample env first so Compose picks up your overrides:

```bash
cp .env.example .env
docker compose up --build
```

The stack now includes a `redis` service configured for append-only persistence and mounted storage. The API is automatically pointed at this instance via `SYNQC_REDIS_URL=redis://redis:6379/0` (override with your own endpoint if needed). Data for Redis and the job queue are persisted in Docker volumes (`synqc_redis_data`, `synqc_data`) so containers can be restarted without losing state.

Once containers are healthy, verify the API can reach Redis by checking the health endpoint (returns `budget_tracker.redis_connected: true` when Redis is up):

```bash
docker compose ps
curl -sf http://127.0.0.1:8001/health
# Optional: run an active Redis probe from inside the backend container
docker compose run --rm api python -m synqc_backend.redis_healthcheck
```

### Redis connectivity probe without Docker

If Docker is unavailable, you can still validate Redis access from your host environment as long as you have a reachable Redis endpoint:

```bash
# Point these at your running Redis instance (defaults are the Compose settings)
export REDIS_URL=${REDIS_URL:-redis://localhost:6379/0}
export REDIS_EVENTS_CHANNEL=${REDIS_EVENTS_CHANNEL:-synqc:events}

# Run the same probe used in the container image
python -m synqc_backend.redis_healthcheck
```

The script exits with a non-zero status if ping or publish fails, making it easy to wire into CI checks or local troubleshooting even when Docker isn't present.

---

## Core Concepts

### Presets (High-Level Experiments)

The backend currently supports four high-level **presets** that align with the SynQc TDS UI:

- `health` — Qubit Health Diagnostics (T1/T2*/echo/RB conceptual bundle).
- `latency` — Latency Characterization probes.
- `backend_compare` — Backend A/B Comparison (currently returns a single simulated result;
  future work will query multiple hardware backends).
- `dpd_demo` — Guided SynQc Drive–Probe–Drive demo (simulated only).

Each preset is a **recipe** that the backend turns into lower-level control sequences.
For now, the implementation is a **simulated KPI generator** tuned to reasonable ranges,
with the structure ready for real hardware integration.

### KPIs

For each experiment run, the backend returns a `KpiBundle` with:

- `fidelity` (float, 0–1),
- `latency_us` (float, approximate microseconds),
- `backaction` (float, 0–1),
- `shots_used` (int),
- `shot_budget` (int),
- `status` ("ok" | "warn" | "fail").

These map directly onto the tiles in the SynQc TDS frontend.

### Engineering controls

Operators can tune a lightweight **control profile** that influences runs and the
frontend visualization. The active profile is exposed via `/health` and can be
managed with `GET/POST /controls/profile`.

For CI environments without outbound package access, drop a cached wheel such as
`httpx-0.27.2-py3-none-any.whl` into `backend/synqc_backend/vendor/httpx_wheels/`
so the load test can run without skipping or downloads.

### Safety & Guardrails

The engine enforces:

- A **maximum shot budget per experiment** (configurable via settings),
- A soft warning if large shot budgets are used on non-simulator targets,
- A **Redis-backed session shot counter** with thread-safe in-memory fallback.

Future work can extend this into persistent, per-user quotas.

---

## File Layout

- `synqc_backend/__init__.py` — package marker.
- `synqc_backend/config.py` — configuration & settings.
- `synqc_backend/models.py` — Pydantic models and enums (presets, KPIs, requests, responses).
- `synqc_backend/hardware_backends.py` — abstraction and implementations for hardware backends.
- `synqc_backend/engine.py` — `SynQcEngine` orchestration and safety checks.
- `synqc_backend/storage.py` — simple in-memory (optional JSON) experiment store.
- `synqc_backend/api.py` — FastAPI application exposing the REST endpoints.

This structure is intentionally clear so that future additions (e.g., real QPU support)
can be isolated and reviewed.

---

## Notes for Future Hardware Integration

1. **Do not modify API contracts lightly.**  
   Frontends (SynQc TDS and others) rely on the `RunExperimentRequest` and
   `RunExperimentResponse` shapes defined in `models.py`.

2. **Add new backends by subclassing `BaseBackend`.**  
   Implement the `run_experiment` method and register the backend in
   `get_backend()` in `hardware_backends.py`.

3. **Keep risk and quota logic in `engine.py`.**  
   This isolates safety-related reasoning in one place, making audits and changes easier.

4. **Use clear version tags.**
   Whenever major behavior changes, bump a version string somewhere visible (e.g. in `config.py`
   and the README) and log it.

---

## Production deployment: shared Redis for budgets and queue metrics

Budgets and the background job queue can be coordinated across workers by pointing the backend to
the same Redis instance:

```bash
export SYNQC_REDIS_URL=redis://redis-host:6379/0
# Optional: extend session budget retention (default 3600s)
export SYNQC_SESSION_BUDGET_TTL_SECONDS=7200
```

The health endpoint now exposes operational signals needed to validate multi-worker correctness:

- `budget_tracker.redis_connected` and `budget_tracker.session_keys` to ensure Redis is reachable and holding the expected number of session budgets.
- `queue.total`, `queue.queued`, `queue.running`, and `queue.oldest_queued_age_s` to verify that runs are flowing and no backlog is building up under load.

Monitor `/health` while generating load to confirm counters move across workers and that Redis remains reachable.

### Prometheus metrics, alerting, and scraping

The backend exports Prometheus metrics on port `9000` by default (configurable via `SYNQC_METRICS_PORT`).
Set `SYNQC_ENABLE_METRICS=false` to disable export, and adjust scrape cadence with `SYNQC_METRICS_COLLECTION_INTERVAL_SECONDS`.

Key series to scrape:

- `synqc_redis_connected{backend="redis|memory"}` — 1 when the budget tracker is reachable.
- `synqc_budget_session_keys{backend="redis|memory"}` — current count of active session budget keys.
- `synqc_budget_session_key_churn_total{backend="redis|memory"}` — cumulative changes in budget key counts (use `rate()` for churn alerts).
- `synqc_queue_jobs_queued` / `synqc_queue_oldest_queued_age_seconds` — backlog depth and age to catch growing queues.
- `synqc_queue_jobs_running` / `synqc_queue_max_workers` — current concurrency versus pool size.

Scrape and alert setup:

1. Add a scrape job pointed at the metrics exporter port. A starter scrape job lives at `backend/ops/prometheus-synqc-example.yml`; drop this into your Prometheus ConfigMap or `prometheus.yml` and tweak the target to match your deployment.
2. If you use Prometheus Operator, convert the scrape job into a `ServiceMonitor` and the alerts into `PrometheusRule` resources. The expressions in the example file match the recommended guardrails in this README.
3. Validate the configuration with `promtool check config prometheus-synqc-example.yml` (or your merged config) before rolling it out, then reload your Prometheus server so the scrape job is active.
4. Confirm the job is live by hitting your Prometheus UI and querying `synqc_queue_jobs_queued` and `synqc_redis_connected` for the `synqc-backend` job.

Alerting rules (tune for your SLOs) are now factored into `backend/ops/synqc-alerts.yml` and cover Redis disconnects, queue backlogs, and budget-key churn spikes. Mount or merge this rules file wherever your Prometheus server expects rule definitions.

### CI/staging Prometheus scrape + alert routing

The GitHub Actions workflow now boots Prometheus and Alertmanager alongside the backend during load tests to prove we can scrape and route alerts in automation:

- Prometheus uses `backend/ops/prometheus-ci-scrape.yml` to scrape `host.docker.internal:9000` (the metrics exporter) and sends alerts to the colocated Alertmanager on port `9093`.
- Alertmanager uses `backend/ops/alertmanager-ci.yml` to forward alerts to a local webhook listener. The workflow fails if the webhook receives any alerts during a healthy run.

To mirror this in staging, reuse the same configs with your target addresses:

```bash
docker run -d --name synqc-alertmanager \
  -v $(pwd)/ops/alertmanager-ci.yml:/etc/alertmanager/alertmanager.yml \
  --add-host host.docker.internal:host-gateway \
  -p 9093:9093 prom/alertmanager:latest

docker run -d --name synqc-prometheus \
  -v $(pwd)/ops/prometheus-ci-scrape.yml:/etc/prometheus/prometheus.yml \
  -v $(pwd)/ops/synqc-alerts.yml:/etc/prometheus/synqc-alerts.yml \
  --add-host host.docker.internal:host-gateway \
  -p 9090:9090 prom/prometheus:latest
```

Then point `host.docker.internal:9000` at your staging exporter or swap in the hostname for your deployment. Wire the Alertmanager receiver to your preferred routing targets (email/Slack/PagerDuty) by editing `alertmanager-ci.yml`.

### Staging/production paging routes

Use `backend/ops/alertmanager-staging.yml` when you want to exercise real paging channels (Slack, PagerDuty, and an optional webhook mirror) while keeping the same alert rules. Render it via `envsubst` so your secrets stay outside of git:

```bash
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..."
export SLACK_CHANNEL="#synqc-paging"
export PAGERDUTY_ROUTING_KEY="<pagerduty-key>"
export WEBHOOK_MIRROR_URL="https://alert-mirror.example.com/alerts"
envsubst < backend/ops/alertmanager-staging.yml > /tmp/alertmanager.yml
docker run -d --name synqc-alertmanager \
  -v /tmp/alertmanager.yml:/etc/alertmanager/alertmanager.yml \
  --add-host host.docker.internal:host-gateway \
  -p 9093:9093 prom/alertmanager:latest
```

Swap the webhook URL for a dead-simple HTTP sink (like [webhook.site](https://webhook.site/)) when validating staging before wiring real paging targets. Keep the CI webhook receiver enabled as a mirror so you can assert delivery while the paging routes stay live.

When running the GitHub Actions load-test workflow against real paging channels, point `ALERTMANAGER_CONFIG_TEMPLATE` at the staging template and let the workflow render it (e.g., `ALERTMANAGER_CONFIG_TEMPLATE=backend/ops/alertmanager-staging.yml`). Secrets for Slack/PagerDuty/webhook destinations should be provided as repository or environment secrets consumed by `envsubst`.

**GitHub Secrets to set for staging/production paging**

- `SLACK_WEBHOOK_URL` — Incoming webhook for your paging channel.
- `SLACK_CHANNEL` — Channel name (e.g., `#synqc-paging`).
- `PAGERDUTY_ROUTING_KEY` — Events V2 routing key for the service.
- `WEBHOOK_MIRROR_URL` — Optional HTTP sink to mirror alerts alongside paging.

Set `ALERTMANAGER_CONFIG_TEMPLATE=backend/ops/alertmanager-staging.yml` as an environment or repository variable to make the CI/staging workflow render the staging template with the secrets above. If the staging template is selected and any of these secrets are missing, the workflow will now fail fast instead of silently rendering empty values.

### Multi-worker load test to verify queue drain and budgets

A lightweight load-test script lives at `backend/scripts/load_test.py` to exercise the queue and budgets while confirming metrics stay healthy:

```bash
python backend/scripts/load_test.py \
  --base-url http://127.0.0.1:8001 \
  --metrics-url http://127.0.0.1:9000/metrics \
  --runs 60 --concurrency 15 \
  --api-key "$SYNQC_API_KEY" \
  --session-id "multi-worker-smoke"
```

What to look for:

- `Runs finished` equals the number submitted.
- `/health` shows `queue.queued == 0` and `queue.running == 0` when the test ends.
- Metrics report `synqc_queue_jobs_queued == 0`, `synqc_redis_connected == 1`, and a bounded `synqc_budget_session_keys` value.

Run this against multiple workers (e.g., `uvicorn --workers 4`) while pointing all instances at the same Redis URL. The script surfaces warnings if the queue fails to drain or Redis disconnects during the test so you can catch regressions early.

The helper now defaults to `--strict`, exiting non-zero when queues fail to drain, Redis disconnects, metrics are unreachable, or runs remain unfinished. Disable with `--no-strict` for exploratory local checks. Use higher concurrency (e.g., `--runs 60 --concurrency 15`) in staging to mirror production-like load and validate alert thresholds before rollout; feel free to bump these further in a staging-only branch to probe headroom before production rollout.

### CI coverage for Redis + queue safety

A GitHub Actions workflow (`.github/workflows/backend-load-test.yml`) provisions Redis, boots the backend with a multi-worker queue, and runs `scripts/load_test.py --strict` against the live metrics exporter. This ensures queue depth returns to zero and Redis stays connected under concurrent submissions on every push and pull request that touches the backend. Use it as a template for your own CI pipeline if you mirror this repository internally. Adjust the environment variables and load-test flags there to run at higher concurrency (matching the staging example above) before promoting alert thresholds to production. Set `ALERTMANAGER_CONFIG_TEMPLATE` to `backend/ops/alertmanager-staging.yml` (rendered via `envsubst` inside the workflow) when you want the workflow to exercise real paging receivers instead of the CI webhook sink.

Repository variables `LOAD_TEST_RUNS` and `LOAD_TEST_CONCURRENCY` can be used to raise the default pressure in the workflow without editing the YAML. Pair these with the staging Alertmanager template to probe headroom under paging-connected runs in staging branches.

---

This backend is versioned as:

> **SynQc TDS Backend v0.1 (2025-12-11, America/Chicago)**

and matches the SynQc TDS frontend console v0.1 you currently have.
