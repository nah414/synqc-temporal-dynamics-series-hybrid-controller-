# Integration Notes (SynQc TDS)

## UI placement (matches your screenshot)

Your screenshot shows the Console section with a large empty content area (the red rectangle).  
The intended integration is:

- Keep existing Console layout intact.
- Replace the empty content area with a *tabbed* container, or simply mount the Shor panel into that area.

Minimum change: add this inside the console content container:

```html
<div id="shor-panel-host"></div>
```

The `shor-panel.js` file will detect this host element and render the panel.

## API contract

All endpoints live under `/api/shor`.

### POST /api/shor/rsa/generate
Request:
```json
{ "bits": 12, "e": 65537 }
```

Response:
```json
{
  "run_id": "...",
  "p": 61,
  "q": 53,
  "N": 3233,
  "phi": 3120,
  "e": 17,
  "d": 2753
}
```

### POST /api/shor/rsa/encrypt
Request (integer plaintext):
```json
{ "N": 3233, "e": 17, "plaintext_int": 42 }
```

Request (text plaintext):
```json
{ "N": 3233, "e": 17, "plaintext_text": "hi" }
```

Response:
```json
{ "run_id": "...", "ciphertext_int": 2557, "plaintext_int": 42 }
```

### POST /api/shor/factor
Request:
```json
{ "N": 3233, "method": "auto", "backend_mode": "aer", "shots": 1024 }
```

Response:
```json
{
  "run_id": "...",
  "N": 3233,
  "p": 61,
  "q": 53,
  "method_used": "qiskit_shor|classical_fallback",
  "runtime_ms": 123.4,
  "steps": [
    {"name": "validate", "ms": 0.1, "ok": true, "detail": null},
    {"name": "qiskit_shor", "ms": 120.0, "ok": true, "detail": null}
  ]
}
```

To target **non-IBM hardware via a custom Qiskit provider**, set `backend_mode` to `custom` and supply your provider loader and backend name:

```json
{
  "N": 3233,
  "method": "qiskit",
  "backend_mode": "custom",
  "provider_loader": "qiskit_braket_provider.BraketProvider",
  "provider_backend_name": "SV1"
}
```

### POST /api/shor/rsa/decrypt
Request:
```json
{ "N": 3233, "e": 17, "ciphertext_int": 2557, "method": "auto", "backend_mode": "aer", "shots": 1024 }
```

Response:
```json
{
  "run_id": "...",
  "plaintext_int": 42,
  "plaintext_text": "*optional if decodes cleanly*",
  "p": 61,
  "q": 53,
  "d": 2753,
  "method_used": "qiskit_shor|classical_fallback",
  "runtime_ms": 456.7,
  "steps": [
    {"name": "validate", "ms": 0.1, "ok": true, "detail": null},
    {"name": "classical_factor", "ms": 30.0, "ok": true, "detail": null},
    {"name": "derive_private_key+decrypt", "ms": 1.2, "ok": true, "detail": null}
  ]
}
```

### POST /api/shor/estimate
Request:
```json
{ "N": 3233 }
```

Response:
```json
{
  "run_id": "...",
  "estimate": {
    "n_bits": 12,
    "max_bits_cap": 20,
    "qiskit_available": true,
    "logical_qubits_textbook": 36,
    "depth_scaling": "...",
    "gate_scaling": "..."
  }
}
```

### GET /api/shor/runs
Returns recent run summaries (newest first) so you can populate your existing
"Experiment Runs" table without inventing a separate UX pattern.

### GET /api/shor/runs/{run_id}
Returns the full run record (request/response/error).

## Feature flagging

The backend reads env vars:

- `SYNQC_SHOR_ENABLE` (default: `1`)
- `SYNQC_SHOR_MAX_N_BITS` (default: `20`)
- `SYNQC_SHOR_ALLOW_TEXT` (default: `1`)

Optional (to integrate with your run table + temporal sequence UI):

- `SYNQC_SHOR_RUN_LOG_PATH` (default: empty) — if set, append JSONL run records
- `SYNQC_SHOR_RUN_LOG_MAX` (default: `200`) — max in-memory runs for `GET /api/shor/runs`
- `SYNQC_SHOR_INCLUDE_STEPS` (default: `1`) — include per-step timing in responses

The frontend can be hidden behind your existing UI mode switch if you want.  
The simplest approach is: always mount it, but keep it collapsible.

## Auth integration

If your backend already expects `Authorization: Bearer <token>`, keep that in place.

The frontend JS includes a hook:
- It will automatically attach `Authorization` header if it finds `synqc_bearer_token` in `localStorage`.
- Hardware modes (IBM/custom) require that token to be present; the UI will block the request and prompt for it instead of letting the backend return a 401.

Adjust the key name in `shor-panel.js` if your app uses a different token key.
