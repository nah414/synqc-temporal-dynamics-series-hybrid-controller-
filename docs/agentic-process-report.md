# Agentic Process Report for SynQc TDS

## Source Materials Reviewed
- `gpt/SynQc_GPT_Pro_Context_Instructions_v0_1.md`
- `docs/SynQc_Temporal_Dynamics_Series_Technical_Archive_v0_1.md`
- `web/index.html` (agent panel UI and intent interpretation logic)

## Agent Role and Knowledge Base
- The SynQc Guide agent’s mission is to help users understand Temporal Dynamics Series concepts and operate the console by mapping goals to presets, hardware targets, and KPIs.【F:gpt/SynQc_GPT_Pro_Context_Instructions_v0_1.md†L3-L37】
- Its primary reference is the technical archive. When data is missing from the archive, the agent should explicitly say so and avoid fabricating results.【F:gpt/SynQc_GPT_Pro_Context_Instructions_v0_1.md†L8-L17】

## Operating Rules and Guardrails
- The agent defaults to the Drive → Probe → Drive/Feedback mental model and must highlight latency and backaction trade-offs in suggestions.【F:gpt/SynQc_GPT_Pro_Context_Instructions_v0_1.md†L13-L17】
- Guardrails include honoring shot caps, depth/duration limits, drift triggers, and refusing strong claims without multiple signatures; these protect scientific integrity.【F:gpt/SynQc_GPT_Pro_Context_Instructions_v0_1.md†L39-L42】【F:docs/SynQc_Temporal_Dynamics_Series_Technical_Archive_v0_1.md†L249-L261】

## Intent Mapping and Required Inputs
- Preset mapping: Health Diagnostics, Latency Characterization, Backend A/B Comparison, and Guided DPD Demo.【F:gpt/SynQc_GPT_Pro_Context_Instructions_v0_1.md†L19-L25】
- Minimum inputs the agent requests when missing: hardware target, goal category, and shot-budget sensitivity.【F:gpt/SynQc_GPT_Pro_Context_Instructions_v0_1.md†L26-L29】
- The archive confirms these presets as canonical bundles the agent should select when interpreting user language.【F:docs/SynQc_Temporal_Dynamics_Series_Technical_Archive_v0_1.md†L231-L245】

## UI Implementation of Agentic Flow
- The console exposes an “Agent” tab with chat, preset selection, hardware target dropdown, shot budget, notes, and API-key handling. Grover-specific callouts highlight the ability to dispatch real Qiskit/Aer runs.【F:web/index.html†L1224-L1317】
- Chat rendering avoids `innerHTML`, and user text is routed through `interpretIntent`, which auto-selects presets based on keywords (health, latency, compare, demo) and updates the scene labels and agent reply accordingly.【F:web/index.html†L4326-L4412】
- API-key messaging warns about URL/localStorage leakage and cleans query parameters after seeding local storage, underscoring safety considerations around credentials.【F:web/index.html†L1295-L1304】

## Current Coverage vs. Gaps
- Conceptual definitions, simulator trade-off exploration, and high-level scheduling exist, but full QPU integration, hardened data pipelines, and automated calibration routines remain pending per the roadmap snapshot.【F:docs/SynQc_Temporal_Dynamics_Series_Technical_Archive_v0_1.md†L264-L305】
- Frontend intent mapping is deterministic and keyword-based; it lacks the richer context handling described in the GPT Pro guide (e.g., explicit latency/backaction framing or querying missing inputs).

