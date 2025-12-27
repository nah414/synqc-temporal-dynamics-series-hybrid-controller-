# Optional Dual-Clocking-Qubits Integration Guide

This guide shows how to run the external [Dual-Clocking-Qubits](https://github.com/nah414/Dual-Clocking-Qubits) toolkit **alongside** SynQc TDS without changing the core codebase. The integration stays opt-in and isolated so the existing roadmap (simulator-first demos, provider registry, hosted proof milestones) remains stable.

## Why keep it sidecar-only?

- Avoids dependency collisions with the FastAPI/worker stack and pinned `backend` extras.
- Makes roll-forward/rollback trivial (remove the submodule or override file to detach).
- Preserves the single-file UI and backend guardrails while still giving curious users an advanced option.

## Add the repository as a submodule (recommended)

From the repo root:

```bash
git submodule add https://github.com/nah414/Dual-Clocking-Qubits tools/dual-clocking-qubits
# If the submodule already exists (from a fresh clone):
git submodule update --init --recursive
```

Tips:
- Keep Dual-Clocking-Qubits in a dedicated virtual environment to avoid package clashes with `backend[dev,qiskit,braket,ionq]`.
- If you do not want to track the submodule in your fork, clone it manually into `tools/dual-clocking-qubits/` and add it to `.git/info/exclude` locally.

## Run SynQc TDS as usual

Bring up the baseline stack (API + worker + Redis + static UI):

```bash
docker compose up --build
```

This starts the API at `http://localhost:8001` and the UI at `http://localhost:8000` (served by Nginx). You can also run the backend locally via `uvicorn` if you prefer.

## Run Dual-Clocking-Qubits alongside the stack

In a separate terminal:

```bash
cd tools/dual-clocking-qubits
python -m venv .venv
source .venv/bin/activate
pip install -e .
# Replace the next line with the project-specific entry point or scripts
python path/to/dual_clocking_entrypoint.py
```

Because Dual-Clocking-Qubits runs independently, it will not interfere with SynQc TDS services. Use its configuration to point any outbound calls to the SynQc API endpoints below.

## Point Dual-Clocking-Qubits at SynQc APIs

Key endpoints (served by `synqc-api`):

- Submit a run: `POST http://localhost:8001/experiments/run`
- Recent experiments: `GET http://localhost:8001/experiments/recent`
- Experiment details: `GET http://localhost:8001/experiments/{id}`
- Hardware targets: `GET http://localhost:8001/hardware/targets`
- Health and guardrails: `GET http://localhost:8001/health`

You can also steer the UI to a different API host using a query string, e.g. `web/index.html?api=http://localhost:8001`.

## Sample `docker-compose.override.yml` (optional, non-tracked)

To containerize Dual-Clocking-Qubits alongside SynQc without touching `docker-compose.yml`, create a local `docker-compose.override.yml` (do **not** commit it) such as:

```yaml
version: "3.9"
services:
  dual-clocking-qubits:
    build: ./tools/dual-clocking-qubits  # or replace with a published image
    command: ["bash", "-lc", "python path/to/dual_clocking_entrypoint.py --api http://api:8001"]
    depends_on:
      - api
    networks:
      - synqc_default
    environment:
      SYNQC_API_URL: http://api:8001
networks:
  synqc_default:
    external: false
```

Notes:
- Compose automatically merges overrides; the snippet above shares the default network so `api:8001` resolves from the Dual-Clocking-Qubits container.
- Replace the `command` with the actual entry point used by Dual-Clocking-Qubits.
- Keep the override file local if you do not want to track the integration.

## Safety and performance tips

- **Isolation first:** run Dual-Clocking-Qubits in its own virtualenv or container to avoid altering the backend dependencies.
- **Resource budgeting:** if you add long-running jobs via `POST /experiments/run`, monitor Redis queue depth and tune worker counts via environment variables before scaling up.
- **Version pinning:** align Python versions between the two projects when possible to reduce wheel rebuild time.
- **Cleanup:** removing the submodule directory or deleting the override file cleanly detaches the integration without touching SynQc TDS code.

## Next steps (optional)

- Add automation in your fork to build a container image for Dual-Clocking-Qubits so the override file can `image:` pull instead of `build:`.
- Create a small API bridge script in `tools/dual-clocking-qubits/` that converts its outputs into SynQc run payloads, keeping it out of the main repository history.
- Share a short demo script in your fork showing how Dual-Clocking-Qubits can feed `POST /experiments/run` and visualize results in the SynQc UI.
