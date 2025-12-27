# SynQc Shor / RSA Add‑On (real-hardware capable)

This add‑on drops a **Shor’s Algorithm RSA** panel into the SynQc Temporal Dynamics Series (TDS) console UI (the large empty console area you circled), and exposes matching backend endpoints.

A key point: **Shor doesn’t “encrypt/decrypt”** — it **factors** the RSA modulus `N = p·q`. Once you have `p` and `q`, you can compute the RSA private exponent `d` and then decrypt.  
This feature is implemented as a **separate module** (feature‑flagged) so it won’t interfere with the existing temporal dynamics workflows unless you use it.

## What you get

### Front end
- A panel (pure HTML/CSS/JS, no framework assumptions) that mounts into a host `<div>` you place in the console area.
- Controls for:
  - Generate a demo-friendly RSA keypair (defaults capped for safety; raise limits intentionally if you want larger instances)
  - Encrypt (RSA)
  - Decrypt **via factoring** (Shor if available, otherwise classical fallback)
  - Factor `N` directly
- Output area with structured results + timing.

### Back end
- A FastAPI router you can mount under: `GET/POST /api/shor/*`
- Endpoints:
- `POST /api/shor/factor` → factor `N` (auto/qiskit/classical; aer/ibm)
- `POST /api/shor/estimate` → heuristic resource estimate (qubits + scaling notes)
- `POST /api/shor/rsa/generate` → generate guard-railed RSA keypair
  - `POST /api/shor/rsa/encrypt` → encrypt integer or short UTF‑8 text
  - `POST /api/shor/rsa/decrypt` → decrypt using recovered private key (factors `N`)
  - `GET /api/shor/runs` → recent run summaries (so you can populate "Experiment Runs")
  - `GET /api/shor/runs/{run_id}` → full run record
- Optional use of **Qiskit’s Shor implementation** when Qiskit is installed.
- Hard safety limits (bit‑length caps) to avoid accidental crypto‑breaking runs. You can raise them intentionally for real hardware experiments.
- `backend_mode` includes `custom` so you can attach any Qiskit-compatible hardware provider (IonQ, Rigetti via Braket, etc.).

## Files

```
synqc_shor_addon/
  backend/
    synqc_shor/
      __init__.py
      api.py
      estimate.py
      factor.py
      run_store.py
      rsa.py
      qiskit_shor.py
      classical_factor.py
      config.py
    tests/
      test_rsa_roundtrip.py
  frontend/
    shor-panel.css
    shor-panel.js
    shor-panel.html   # copy/paste snippet
  INTEGRATION_NOTES.md
```

## Backend integration (FastAPI)

1) Copy `backend/synqc_shor/` into your backend source tree (or add it as a package).

2) Install requirements (minimum):

```bash
pip install fastapi pydantic
```

Optional (for Qiskit Shor support):

```bash
pip install qiskit qiskit-aer qiskit-ibm-runtime qiskit-algorithms
```

Optional (to run on **non-IBM real hardware** via Qiskit providers):

```bash
# Pick the provider package that matches your hardware, e.g.:
pip install qiskit-braket-provider    # Amazon Braket
pip install qiskit-ionq               # IonQ
```

Then set one of the provider loader env vars and backend name (examples):

```
SYNQC_SHOR_PROVIDER_CLASS=qiskit_braket_provider.BraketProvider
SYNQC_SHOR_PROVIDER_BACKEND=SV1  # or your physical device name
```

For providers that expect a token/constructor args you can add:

```
SYNQC_SHOR_PROVIDER_TOKEN=...            # injected as token kwarg when supported
SYNQC_SHOR_PROVIDER_KWARGS='{"region": "us-east-1"}'
```

3) Mount the router in your FastAPI app (your file might be `main.py`, `app.py`, etc.):

```python
from synqc_shor.api import router as shor_router

app.include_router(shor_router, prefix="/api/shor", tags=["shor"])
```

4) (If needed) allow your front end origin via CORS, same as your other endpoints.

5) Run your backend on the same port the UI expects (your screenshot showed `http://localhost:8001`).

## Frontend integration

1) In the **console content area you circled**, add a mount point:

```html
<div id="shor-panel-host"></div>
```

2) Include the CSS + JS (or import them via your build system):

```html
<link rel="stylesheet" href="./shor-panel.css" />
<script type="module" src="./shor-panel.js"></script>
```

3) For **hardware runs** (IBM Runtime or custom Qiskit providers) the panel expects a bearer token already present in `localStorage` (keys it checks: `synqc_bearer_token`, `synqc_api_key`, `api_key`). The UI blocks dispatch when no token is present to avoid backend 401s.

4) The JS auto-mounts into `#shor-panel-host` (and safely does nothing if it doesn’t exist).

### Panel controls

- **Execution profile** exposes simulator (Aer), IBM Runtime, and **custom Qiskit providers**. For custom/hardware modes, supply the provider loader (e.g. `qiskit_braket_provider.BraketProvider`) and the backend name your hardware advertises.
- **Guardrails stay on**: the front end keeps classical fallback available, enforces shots caps, and reminds you that credentials/config must already be present for IBM or third-party providers.
- **RSA inputs** accept integer or text plaintext (text is converted to int under the hood) so you can exercise encrypt/decrypt flows while targeting the backend you select.

## Safety / guardrails

- This module **rejects large RSA moduli** by default (`SYNQC_SHOR_MAX_N_BITS`, default 20) as a guardrail.
- Quantum resources are still limited, but the Shor path can target simulators **and** real hardware providers.
- If you want to raise the cap for experiments, do it intentionally and accept the compute cost.

## Optional run logging + step timings

These are the knobs that make the feature feel "native" inside SynQc:

- `SYNQC_SHOR_INCLUDE_STEPS=1` (default) adds a `steps` field to responses so you can render a temporal sequence/timeline.
- `SYNQC_SHOR_RUN_LOG_MAX=200` controls the in-memory run buffer for `GET /api/shor/runs`.
- `SYNQC_SHOR_RUN_LOG_PATH=/path/to/file.jsonl` appends JSONL run records to disk (optional).

## Running tests

```bash
pytest backend/tests -q
```

### Enabling the RSA tests (`synqc_shor` import)

The RSA roundtrip tests in `backend/tests/test_rsa_roundtrip.py` are skipped when the optional `synqc_shor` package is missing. To exercise them locally:

1) Create/activate a virtual environment.

2) Make sure your environment has the `wheel` build helper available (avoids the missing `wheel` command during editable installs):

```bash
python -m pip install --upgrade pip wheel
```

3) Install the add-on in editable mode (this wires up `synqc_shor` without PYTHONPATH hacks):

```bash
pip install -e './synqc_shor_addon_v2[tests]'
```

4) (Optional) Install quantum/hardware extras if you want to run Qiskit-backed Shor:

```bash
pip install 'synqc_shor[qiskit]'  # plus [braket] or [ionq] if needed
```

5) Run the targeted test file to confirm imports resolve:

```bash
pytest synqc_shor_addon_v2/backend/tests/test_rsa_roundtrip.py -q
```
