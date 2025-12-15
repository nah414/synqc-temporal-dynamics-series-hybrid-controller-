# SynQc Temporal Dynamics Series — Technical Archive (v0.1)
**Date:** 2025-12-11  
**Scope:** Technical consolidation of our work on SynQc Temporal Dynamics Series (successor to Dual-Clocking Qubits), including control concepts, simulation work, KPIs, architecture, and integration with SynQc TDS.

---

## 1. Project Definition & Intent

SynQc Temporal Dynamics Series ("SynQc TDS Core") is the engineering framework for timing-aware quantum control, built around:

- Drive–Probe–Drive (DPD) sequences,
- Mid-circuit measurement and feed-forward,
- Floquet-style / periodically-driven control where applicable,
- Explicit timing, latency, and backaction modeling,
- Integration with both quantum and classical hardware stacks.

Goals:

1. Provide a hardware-agnostic control framework that works for superconducting, trapped-ion, neutral-atom, and photonic platforms.
2. Use mid-circuit probes to learn about the system in real time and adapt control.
3. Make latency, drift, and backaction visible and tunable, not invisible “implementation detail.”
4. Serve as the core engine underneath SynQc TDS and other eVision projects.

---

## 2. Historical Evolution (Condensed)

### 2.1 From Dual-Clocking Qubits to SynQc

- Original idea: "dual clocking" — exploring how two clock domains or tones influence gate implementation and stability.
- Progressed into a more general DPD view:
  - Drive: push the system into a state or manifold,
  - Probe: measure or partially interrogate,
  - Drive: adjust based on what was observed.

This abstraction is now the primary primitive in SynQc.

### 2.2 Lindblad Simulation and Probe Trade-offs

We built a conceptual Lindblad-based simulator for:

- A system qubit plus probe/ancilla,
- DPD sequences with tunable probe strength (ε) and duration (τₚ).

Results:

- Very weak probes (small ε, short τₚ) → negligible information, negligible disturbance.
- Strong probes → significant mutual information about the state but strong backaction.
- Identified a useful "sweet spot" regime where probes yield actionable information with tolerable backaction.

Conclusion: SynQc control should treat probe design as an explicit knob in the information–backaction trade-space.

### 2.3 SynQc Base Plan & Modality Choices

- Primary modality: **transmon** (ecosystem maturity, access via IBM/AWS platforms).
- Pilot modality: **fluxonium** (longer coherence, richer behavior).
- Deferred modality: **Majorana/topological**, pending robust SQI/topological diagnostics.

These decisions are consistent across dual-clocking notes, materials diagnostics, and future fusion-control concepts.

---

## 3. Control Model

### 3.1 Drive–Probe–Drive Primitive

A SynQc experiment is composed of DPD blocks:

1. **Drive D₁**  
   Apply a control Hamiltonian Hᴰ¹(t) for duration τᴰ¹ (e.g. Rabi pulse, detuned drive, shaped pulse).

2. **Probe P**  
   Couple the system to measurement channels:
   - Strong projective readout,
   - Weak measurement,
   - Ancilla-based interrogation.

   Outcomes k correspond to measurement operators Mₖ and associated post-measurement states.

3. **Drive D₂**  
   Apply further control conditioned on:
   - Direct measurement outcomes, or
   - Aggregated statistics across many runs (adaptive tuning).

Multiple DPD blocks can be chained or periodically applied (Floquet/periodic driving), giving a rich space of control sequences.

### 3.2 Open-System Evolution

We model open-system dynamics with a Lindblad master equation:

\dot{ρ} = -i[H(t), ρ] + ∑ⱼ 𝔇[Lⱼ](ρ),

where:

- H(t) includes drives and detunings,
- Lⱼ capture relaxation, dephasing, leakage,
- 𝔇[·] is the usual dissipator.

Drive segments implement specific H(t) forms; probe segments are handled as measurement superoperators and classical branching at the trajectory level.

---

## 4. Information–Backaction Trade-off

For a probe parameterized by strength ε and duration τₚ, SynQc monitors:

- Information gain (e.g., mutual information between hidden state and measurement outcome),
- Backaction (e.g., trace distance or fidelity between the evolved state with vs without the probe).

Key observations from sweeps over (ε, τₚ):

- Small ε, short τₚ → nearly invisible probe:
  - Good for gentle monitoring, poor for fast learning.
- Moderate regime → usable mutual information with acceptable disturbance:
  - Ideal for ongoing diagnostics and adaptive control.
- Strong regime → nearly projective readout:
  - Good for final measurement / explicit collapse, but destructive if used too early.

This led to qualitative probe modes:

- **Diagnostic mode** — gentle, low-backaction,
- **Characterization mode** — moderate trade-off,
- **Readout mode** — fully informative, high backaction.

---

## 5. KPIs (Key Performance Indicators)

SynQc defines and tracks multiple KPIs per experiment bundle:

1. **Fidelity F**  
   Overlap between intended state/process and realized outcome. Can be estimated via tomography, RB, or proxy metrics.

2. **Latency L**  
   End-to-end delay from control decision to classical result:
   - Includes control stack, hardware and network contributions.

3. **Backaction B**  
   Scalar summary of how much a probe disturbs the evolution relative to a reference path.

4. **Shot Usage & Efficiency**  
   - Shots used vs configured budget,
   - Information or convergence per shot.

5. **MCM RB-like metrics**  
   - Randomized benchmarking adapted to mid-circuit measurement scenarios.

6. **Drift and Stability Indicators**  
   - Trends in T₁/T₂-like estimates,
   - Shifts in error rates,
   - Flags for "out-of-spec" regimes.

These KPIs feed SynQc TDS visualizations (tiles and summaries) and backend decision logic (when to recalibrate, when to restrict hardware).

---

## 6. Software Architecture

SynQc TDS Core is structured as a set of modules with clean responsibilities.

### 6.1 scheduler

- Builds time-ordered sequences of DPD blocks:
  - Drive segments,
  - Probe segments,
  - Idle periods,
  - Conditional branches.
- Handles:
  - Alignment with hardware timing grids,
  - Labeling segments for later analysis,
  - Enforcing duration and resource limits.

### 6.2 probes

- Catalog of probe types:
  - Strong projective,
  - Weak continuous/pulsed,
  - Ancilla-mediated.

- Each type has metadata for:
  - Its intended information regime (diagnostic/characterization/readout),
  - Expected backaction,
  - Preferred hardware implementations.

### 6.3 demod (Demodulation & Analysis)

- IQ demodulation and feature extraction from measurement records.
- Implements:
  - Mixing, filtering, windowing,
  - Basic estimators (e.g. state probabilities, visibility, amplitude/phase offsets).

### 6.4 adapt (Adaptive Control)

- Learning layer that adjusts control based on probe results:
  - Kalman filters or Bayesian updates for drift tracking,
  - Simple regressors to tune drive amplitudes and phases,
  - Bias corrections applied between experiment runs.

### 6.5 Hardware Backends Interface

Backends implement an interface that SynQc uses to remain hardware-neutral:

- Input: abstract schedule / DPD description + hardware constraints.
- Output: measurement records, resource usage, provider logs.

This is the layer that talks to real SDKs (IBM, IonQ, Braket, etc.) or drivers (FPGA/DAQ).

---

## 7. Integration with SynQc TDS Frontend

SynQc TDS uses SynQc TDS Core as its engine.

### 7.1 API Shape

Conceptual endpoints:

- `POST /run-experiment`
  - Carries high-level description:
    - preset type (health, latency, compare, DPD demo),
    - hardware target,
    - shot budget,
    - optional parameter overrides.

- `GET /hardware/targets`
- `GET /sessions/{id}`
- `GET /experiments/{id}`

The backend translates these into DPD bundles using `scheduler`, `probes`, `demod`, `adapt` and hardware backends.

### 7.2 Use Case Mapping (Brief)

- **Health Diagnostics** (T₁/T₂*/echo/RB)
  - Evaluate coherence and gate error; update KPIs and drifting baselines.

- **Latency Characterization**
  - Run minimal DPD probes; estimate control and hardware latency.

- **Backend Comparison**
  - Replay identical bundles across two backends; compare KPIs side-by-side.

- **Guided DPD Demo**
  - Run illustrative sequences on a simulator; expose internal states for educational purposes.

The SynQc Guide agent maps user language to these well-defined bundles.

---

## 8. Safety & Guardrails

SynQc Core is designed with guardrails, including:

- Per-experiment and per-session shot caps,
- Sequence depth and duration limits per hardware target,
- Drift thresholds that can automatically:
  - Trigger recalibration sequences,
  - Restrict access to costly hardware until stability returns,
- Strong criteria for any future "topological" claims (e.g., combining SQI patterns, Shapiro-step anomalies, nonlocal signatures).

These protect both hardware and scientific integrity.

---

## 9. Implementation Status (v0.1 Snapshot)

**Conceptually defined:**
- DPD control primitive and its relation to dual-clocking ideas.
- Lindblad model with information–backaction tradeoff.
- Core module decomposition (`scheduler`, `probes`, `demod`, `adapt`).
- KPI definitions and their role in UI and decision logic.
- Hardware abstraction and modality strategy.

**Prototyped / partial:**
- Lindblad-based simulator for a qubit with probe,
- Tradeoff exploration across probe strength and duration,
- Initial scheduling and timing diagram structure.

**Pending for later versions:**
- Full integration with real QPU SDKs and lab hardware,
- Hardened data pipelines and storage,
- Automated calibration playbooks and analysis notebooks.

---

## 10. Roadmap

1. **v0.2 — Stabilized simulator + KPIs**
   - Clean reference implementation of the DPD simulator.
   - Example notebooks for health diagnostics, latency, and DPD demos.

2. **v0.3 — Pilot QPU Integration**
   - End-to-end runs of SynQc bundles on one hardware provider.
   - Comparison against simulator baselines.

3. **v0.4 — Adaptive Control**
   - Implement full `adapt` logic and drift tracking,
   - Automated parameter updates and calibration triggers.

4. **v0.5 — Cross-Project Integration**
   - Expose SynQc capabilities to Telecom Q-Interconnect, materials diagnostics, and selected fusion control tasks.

5. **v1.0 — Hardened release**
   - Fully documented, reproducible experiments,
   - Robust CI and regression tests,
   - Stable API for frontends like SynQc TDS.

---

This file is intended to be stored as:

- `docs/SynQc_Temporal_Dynamics_Series_Technical_Archive_v0_1.md`

and serves as the technical reference snapshot of SynQc TDS Core at this stage.
