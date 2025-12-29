# SynQc TDS process and system instructions

Use this guide to run SynQc TDS in each supported mode and to operate the optional add-ons that ship with the repository.

## Core components
- **Frontend console** (`web/index.html`): single-file UI that talks to the API and renders KPIs, experiments, and hardware targets.
- **API service** (`synqc_backend.api`): FastAPI application that enforces guardrails, queues jobs, and serves health/metrics.
- **Worker** (`synqc-worker`): separate process/compose service that drains the run queue so the API remains responsive.

## Local development (Python 3.12)
1. Create and activate a virtual environment in the repo root.
2. Install the backend in editable mode: `pip install -e ./backend`.
3. Start the API with live reload: `uvicorn synqc_backend.api:app --host 127.0.0.1 --port 8001 --reload`.
4. Open `web/index.html` directly or serve it with `python -m http.server 8080` and point the UI at the API via `?api=http://127.0.0.1:8001` when needed.

## Docker Desktop demo stack
1. Copy `.env.example` to `.env` so Compose picks up your overrides.
2. Run `docker compose up --build` from the repo root to start the API, Redis, worker, and Nginx-served UI.
3. Confirm the stack with `docker compose ps` and `curl -sf http://127.0.0.1:8001/health`.
4. Open the UI at `http://127.0.0.1:8080/` and the interactive docs at `http://127.0.0.1:8001/docs`.

## Hosted deployment bundle (nginx + oauth2-proxy)
1. Navigate to `archives/hosted/synqc_hosted_pack_v2/docs/Hosted_Mode.md` for the full playbook.
2. Copy the provided environment template, generate the required secrets, and export them into your deployment `.env`.
3. Use `docker compose -f docker-compose.hosted.yml --env-file .env up --build` to launch the hardened edge (nginx) with internal-only API and Redis.
4. Keep oauth2-proxy in front of both `/` and `/api/*`, enable HTTPS + secure cookies, and disable URL token ingestion in the UI for hosted origins.

## Hosted overlays and UI hardening
1. Review `archives/hosted/synqc_hosted_overlays_root/docs/codex_tasks_hosted.md` for the checklist of overlays to apply (compose additions, nginx overrides, GHCR release workflow, and runtime verification).
2. Apply the UI security patch described in `archives/hosted/synqc_hosted_overlays_root/docs/ui_hosted_security_patch.md` to strip token/query seeding in hosted mode while keeping local/file:// overrides available.

## Shor RSA add-on
1. Open `archives/addons/synqc_shor_addon_v2/synqc_shor_addon_v2/README.md` for capabilities and guardrails.
2. Install the package in editable mode (optional `[tests]` extras) and mount the FastAPI router at `/api/shor` to expose factoring, RSA keygen, and encryption/decryption endpoints.
3. Drop the front-end assets (`shor-panel.html/css/js`) into a host div; they auto-mount and respect existing bearer tokens for hardware runs.

## Dual-Clocking-Qubits integration
1. Use `docs/Dual_Clocking_Qubits_Integration.md` to run the sidecar toolkit stored under `tools/dual-clocking-qubits`.
2. Fetch or update the toolkit with `./scripts/fetch_dual_clocking_tool.sh` when network access is available, then follow the document to run the integration alongside SynQc TDS.

## GPT context and knowledge transfer
- Configure a SynQc Guide assistant with the instructions in `gpt/SynQc_GPT_Pro_Context_Instructions_v0_1.md` and point it at the technical archive `docs/SynQc_Temporal_Dynamics_Series_Technical_Archive_v0_1.md` for end-to-end context.

## Health checks and testing
- Run the smoke check script with `SYNQC_API_URL=http://127.0.0.1:8001 python backend/scripts/quickstart_health_check.py` (optionally set `SYNQC_API_KEY`).
- Use the load test harness in `backend/scripts/load_test.py` to stress API, Redis, and the queue with strict drain checks.
- For static verification, compile the backend module tree via `python -m compileall backend/synqc_backend`.
