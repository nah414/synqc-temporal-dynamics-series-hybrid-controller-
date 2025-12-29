# Zip package analysis

Summary of the three archived packages referenced in the repository.

## synqc_shor_addon_v2
- Provides a Shor’s Algorithm RSA panel with FastAPI router endpoints for factoring, RSA key generation, encryption/decryption, run logs, and optional Qiskit-backed execution including hardware providers.【F:archives/addons/synqc_shor_addon_v2/synqc_shor_addon_v2/README.md†L1-L136】
- Includes front-end assets (`shor-panel.html/css/js`) that auto-mount into a provided host div and expect existing bearer tokens for hardware runs; guardrails enforce small modulus sizes and limit shots by default.【F:archives/addons/synqc_shor_addon_v2/synqc_shor_addon_v2/README.md†L109-L137】
- Backend integration is drop-in: copy the `synqc_shor` package, install FastAPI/Pydantic (optional Qiskit extras), and mount the router at `/api/shor`; optional logging knobs emit step timelines and JSONL run logs.【F:archives/addons/synqc_shor_addon_v2/synqc_shor_addon_v2/README.md†L57-L145】

## synqc_hosted_pack_v2
- Documents and composes a hosted deployment that exposes only an nginx edge while keeping API and Redis internal; oauth2-proxy handles OIDC login and injects identity headers for upstreams.【F:archives/hosted/synqc_hosted_pack_v2/docs/Hosted_Mode.md†L1-L30】【F:archives/hosted/synqc_hosted_pack_v2/docker-compose.hosted.yml†L1-L114】
- Provides operational quick-start steps (env template, secret generation, compose command) plus production hardening guidance such as HTTPS, secure cookies, and disabling URL-based tokens in the UI.【F:archives/hosted/synqc_hosted_pack_v2/docs/Hosted_Mode.md†L31-L64】
- Codex instructions emphasize disabling query-string credential ingestion, ensuring only the edge publishes ports, and configuring nginx to protect `/` and `/api/*` with oauth2-proxy-backed auth, SSE/WS support, and rate limiting.【F:archives/hosted/synqc_hosted_pack_v2/docs/Codex_Hosted_Instructions.md†L1-L135】

## synqc_hosted_overlays_root
- Supplies a task checklist for hosted hardening: add deployment overlays (hosted compose, nginx config, env template, scripts), support nginx config overrides in the web image, disable URL credential seeding in hosted UI mode, add GHCR release workflow, and verify login-gated runtime behavior.【F:archives/hosted/synqc_hosted_overlays_root/docs/codex_tasks_hosted.md†L1-L61】
- Includes a concrete UI patch recommending token/query-param ingestion only for local/file:// contexts while stripping secrets in hosted mode, highlighting risks of URL/localStorage leakage.【F:archives/hosted/synqc_hosted_overlays_root/docs/ui_hosted_security_patch.md†L1-L68】

## Suggested next steps
- Add automated smoke tests or CI workflow that boots the hosted compose, exercises `/api/health`, and validates oauth2-proxy-gated flows to prevent regressions in edge hardening.【F:archives/hosted/synqc_hosted_pack_v2/docs/Codex_Hosted_Instructions.md†L104-L135】
- Implement the hosted UI token guard described in both the Codex instructions and overlay patch to remove URL-based credential ingestion by default, improving hosted security posture.【F:archives/hosted/synqc_hosted_pack_v2/docs/Codex_Hosted_Instructions.md†L52-L71】【F:archives/hosted/synqc_hosted_overlays_root/docs/ui_hosted_security_patch.md†L13-L58】
- Extend backend logging/tests around the Shor add-on to cover real-hardware provider flows and ensure guardrails remain enforced when caps are raised for experimentation.【F:archives/addons/synqc_shor_addon_v2/synqc_shor_addon_v2/README.md†L20-L145】
