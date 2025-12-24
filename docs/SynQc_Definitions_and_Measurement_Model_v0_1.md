# SynQc TDS — Definitions & Measurement Model (Physics Contract) v0.1

**Status:** draft spec for making SynQc KPIs *physics-tethered*, reproducible, and testable.

This document is the missing “physics glue” between:
- a **controller** that schedules/adjusts experiments, and
- the **measurements** (shot-sampled outcomes) it receives back.

It is explicitly **not** a claim that SynQc is “automatically correct physics.” It’s a contract: *if* the backend says it computed a KPI, it must be computable from a stated model + stated data + stated estimator.

---

## 0) The short reality check (why this doc exists)

Infrastructure (Docker, UI, endpoints, logging) makes SynQc runnable, not correct.

To be physics-correct **at the level of what SynQc reports**, we must define:
1) **What state/model is being controlled** (what is the plant? what is the controller state?),
2) **How measurement is produced** (Born rule / POVM / sampling),
3) **How noise/decoherence is modeled** (channels / Lindblad / readout error),
4) **What KPIs mean mathematically** (definition + estimator + uncertainty).

If any KPI doesn’t converge with increased shots the way sampling theory predicts, it’s either:
- not tied to sampling, or
- tied, but implemented wrong, or
- dominated by non-statistical noise (drift, calibration changes, queue batching, etc.).

---

## 1) System-of-interest vs SynQc controller (what is being “controlled”?)

### 1.1 The plant (quantum system / device / simulator)

We model the “plant” as a quantum process that maps:
- a **configuration** (circuit/pulse program + target hardware + runtime options)
to
- **classical measurement outcomes** (bitstrings, analog samples, counts, etc.)

In idealized theory:
- the plant state at measurement time is a **density matrix** \(\rho\) (or statevector \(|\psi\rangle\) as the special pure-state case).

In the product:
- SynQc does **not** directly observe \(\rho\).
- SynQc observes sampled outcomes \(y\) produced by measurements.

### 1.2 The controller (SynQc TDS hybrid controller)

SynQc is an **orchestrator + estimator**:
- It chooses experiment settings \(u_t\) (preset + shot budget + target + knobs),
- It receives outcomes \(y_t\) (counts / histograms / timings),
- It updates internal summaries (KPIs, trend lines, “stability” measures),
- It optionally chooses the next \(u_{t+1}\) based on rules/optimization.

This repo explicitly exposes that flow as an API-driven console:
- `POST /experiments/run` executes a preset and returns KPIs,
- history and details are accessed via `GET /experiments/recent` and `GET /experiments/{id}`,
- hardware targets via `GET /hardware/targets`,
- guardrails via `GET /health`. (Repo README describes these endpoints.)  # citations added in assistant response

---

## 2) Quantum state and measurement model (what the math is)

Everything below is standard quantum measurement theory; SynQc must **name which parts it uses** per experiment.

### 2.1 State representation

SynQc supports (at least conceptually) these representations:

**(A) Statevector (pure state)**
- \(|\psi\rangle \in \mathbb{C}^{2^n}\), \(\langle\psi|\psi\rangle = 1\)
- Suitable for ideal unitary simulation.

**(B) Density matrix (mixed state)**
- \(\rho \succeq 0\), \(\mathrm{Tr}(\rho)=1\)
- Necessary for noise, decoherence, and classical uncertainty.

**(C) Classical surrogate model**
- A probability distribution \(p(x)\) over classical outcomes.
- Useful when only outcome statistics matter (common for hardware).

The **minimum requirement** is: every KPI must state which of these it assumes.

### 2.2 Measurement model (Born rule)

#### Projective measurement (PVM)
Given projectors \(\{P_k\}\) with \(P_k P_j = \delta_{kj}P_k\) and \(\sum_k P_k = I\),

- Probability of outcome \(k\):
\[
p_k = \mathrm{Tr}(P_k \rho)
\]

- Post-measurement state conditioned on outcome \(k\):
\[
\rho_k = \frac{P_k \rho P_k}{\mathrm{Tr}(P_k \rho)}
\]

- Non-selective post-measurement (state after measurement if you ignore the outcome):
\[
\rho' = \sum_k P_k \rho P_k
\]

#### Generalized measurement (POVM + measurement operators)
A POVM is \(\{E_k\}\) with \(E_k \succeq 0\) and \(\sum_k E_k = I\).
Outcome probabilities:
\[
p_k = \mathrm{Tr}(E_k \rho)
\]
To describe post-measurement states you must specify **measurement operators** \(\{M_k\}\) such that:
\[
E_k = M_k^\dagger M_k
\]
and then:
\[
\rho_k = \frac{M_k \rho M_k^\dagger}{\mathrm{Tr}(M_k \rho M_k^\dagger)}
\]

**SynQc rule:** if you claim to compute “backaction”, you must specify \(M_k\) (or an equivalent instrument). A POVM alone does not uniquely define backaction.

### 2.3 Sampling model (what “shots” actually mean)

A **shot** is one independent measurement sample from the same configured experiment.

If the measurement outcomes form a discrete set \(\Omega\) (bitstrings, symbols, bins), then:

- True outcome probabilities: \(p(x)\) for \(x\in\Omega\)
- Observed counts: \(c(x)\)
- Total shots: \(N = \sum_x c(x)\)

Then:
\[
(c(x))_{x\in\Omega} \sim \mathrm{Multinomial}(N, (p(x))_{x\in\Omega})
\]

A common special case is a binary outcome (Bernoulli):
\[
k \sim \mathrm{Binomial}(N,p),\quad \hat p = k/N
\]

---

## 3) Noise and decoherence models (simulator vs hardware)

### 3.1 Discrete-time noise as quantum channels (Kraus form)

A completely positive (CP) quantum operation \(\mathcal{E}\) can be written:
\[
\mathcal{E}(\rho) = \sum_i A_i \rho A_i^\dagger
\]
If it is trace-preserving (CPTP), the Kraus operators satisfy:
\[
\sum_i A_i^\dagger A_i = I
\]

**Typical channel options SynQc can expose:**
- Depolarizing noise
- Phase damping / dephasing
- Amplitude damping (T1-like)
- Pauli channel approximations
- Readout error (classical confusion matrix after measurement)

### 3.2 Continuous-time noise (Lindblad / GKLS master equation)

For open quantum systems with Markovian dynamics, the density matrix evolves as:
\[
\frac{d\rho}{dt} = -i[H,\rho] + \sum_k \left(L_k\rho L_k^\dagger - \tfrac12\{L_k^\dagger L_k, \rho\}\right)
\]
This is the standard Lindblad/GKLS form.

**SynQc rule:** if you use “decoherence” language in KPIs, you must specify whether you used:
- a **channel model** (Kraus / gate-level noise),
- a **master equation** (Lindblad),
- or **hardware-only empirical data** (no internal \(\rho\), only counts).

### 3.3 Simulator-only vs hardware-real assumptions

**Simulator can know:** \(\rho\), \(|\psi\rangle\), noiseless targets, intermediate states, exact channels.

**Hardware can usually know:** outcome samples, limited calibration metadata, queue timings, sometimes per-shot readout assignments, sometimes mid-circuit measurement.

**Hardware usually cannot know without extra protocols:** full \(\rho\), full channel parameters, exact backaction.

So: any KPI that uses \(\rho\) must be marked:
- **SIM-ONLY**, or
- **HARDWARE (requires tomography / characterization protocol)**.

---

## 4) KPI definitions (what your dashboard words mean)

SynQc currently surfaces (at minimum) **fidelity**, **backaction**, **latency** (and may show “stability” trends).

Below are definitions that are implementable and auditable.

### 4.1 Latency (measurable everywhere)

**Definition (total latency):**
\[
\mathrm{latency\_total} = t_{\mathrm{result}} - t_{\mathrm{request}}
\]

Optionally decompose:
- \(t_{\mathrm{queue}}\) (provider queue + scheduling),
- \(t_{\mathrm{exec}}\) (hardware execution / simulator compute),
- \(t_{\mathrm{backend}}\) (SynQc processing and storage).

**Estimator:** direct wall-clock measurement.  
**Uncertainty:** repeat runs; report mean ± std or quantiles.

**Units:** milliseconds (ms).

### 4.2 Fidelity (two different meanings — must label which one)

The word “fidelity” is overloaded. SynQc must pick and label.

#### (A) Quantum state fidelity (SIM-ONLY unless tomography)
For two states \(\rho\) and \(\sigma\),
\[
F_{\mathrm{state}}(\rho,\sigma)=\left(\mathrm{Tr}\sqrt{\sqrt\rho\,\sigma\,\sqrt\rho}\right)^2
\]
For pure states \(|\psi\rangle,|\phi\rangle\): \(F=|\langle\psi|\phi\rangle|^2\).

**When usable:**
- Simulator can compute exactly.
- Hardware requires state tomography or specialized certification (costly).

#### (B) Classical outcome-distribution fidelity (hardware-friendly)
Given:
- expected distribution \(q(x)\) (from simulator or theory),
- empirical \(\hat p(x)=c(x)/N\),

define:
\[
F_{\mathrm{dist}}(\hat p,q) = \left(\sum_{x\in\Omega}\sqrt{\hat p(x)\,q(x)}\right)^2
\]
This is the squared Bhattacharyya coefficient (0 to 1).

**Estimator:** plug-in estimator from counts.  
**Uncertainty:** bootstrap (recommended) or delta-method approximation.

**SynQc rule:** dashboards should display:
- `fidelity.kind = "state"` or `"dist"`
- plus the definition version.

### 4.3 Backaction (must not be a decorative noun)

Backaction is “how much the measurement (or observation process) disturbs the state.”

#### (A) Non-selective measurement disturbance (SIM-ONLY unless tomography)
Given an instrument \(\{M_k\}\), the non-selective post-measurement state is:
\[
\rho' = \sum_k M_k\rho M_k^\dagger
\]
Define backaction as trace distance:
\[
B = \tfrac12\|\rho - \rho'\|_1
\]
Range: 0 (no disturbance) to 1 (maximal, for finite dimensions).

**Estimator:**
- Simulator: compute exactly.
- Hardware: requires tomography of \(\rho\) and \(\rho'\) (or a validated witness).

#### (B) Hardware-friendly “backaction proxy” (only if labeled PROXY)
If you do **not** have \(\rho\), you cannot compute true backaction.
What you *can* compute are proxies that correlate with disturbance.

One honest proxy for some protocols is **repeatability**:
- Prepare the same state twice.
- Measure twice in the same basis.
- Compare distributions; higher drift/non-repeatability implies more disturbance + noise.

Define:
\[
B_{\mathrm{proxy}} = 1 - F_{\mathrm{dist}}(\hat p_1, \hat p_2)
\]
This measures disagreement between two measurement rounds. It conflates:
- backaction,
- drift,
- readout noise,
- and any nonstationarity.

**SynQc rule:** proxies must be labeled:
- `backaction.kind = "proxy_repeatability"` (or similar)
- plus protocol description.

---

## 5) Uncertainty bars and shot scaling (the “don’t fake it” section)

### 5.1 Binomial example (single probability)

If \(\hat p = k/N\) estimates \(p\) from \(N\) shots, then:

- \(\mathrm{Var}(\hat p) = p(1-p)/N\)
- **Standard error**:
\[
\mathrm{SE}(\hat p)=\sqrt{p(1-p)/N}
\]

So your error bars shrink like **\(1/\sqrt{N}\)** (variance shrinks like \(1/N\)).

If you ever see an alleged “probability uncertainty” shrinking like \(1/N\), that’s usually mixing up variance vs standard deviation, or doing something weird.

### 5.2 Multinomial case (distributions)

For \(\hat p(x)=c(x)/N\):
- each component has \(\mathrm{Var}(\hat p(x)) = p(x)(1-p(x))/N\)
- covariances exist between components (because probabilities must sum to 1).

**Practical SynQc solution:** use multinomial bootstrap:
1) treat observed counts \(c\) as defining \(\hat p\),
2) resample \(c^{(b)} \sim \mathrm{Multinomial}(N,\hat p)\),
3) recompute KPI for each bootstrap sample,
4) take 2.5% and 97.5% quantiles for a 95% interval.

This gives a KPI-specific uncertainty without pretending everything is independent.

### 5.3 Shot-scaling sanity tests (must be in CI)

For any KPI you claim is sampling-based:
- Run the same preset with \(N\in\{100, 400, 1600, 6400\}\)
- Compute a CI width \(w(N)\)
- Check that \(w(N)\) approximately scales like \(N^{-1/2}\)

A simple check: fit \(\log w = a + b\log N\). You expect \(b\approx -0.5\).

If \(b\approx 0\), then your “uncertainty bars” are not shot noise bars.

---

## 6) Protocol requirements (what experiment produces what KPI)

This is where “decorative nouns” die and engineering begins.

### 6.1 For distribution fidelity \(F_{dist}\)

**Required inputs:**
- counts \(c(x)\) (from hardware or simulator),
- shot count \(N\),
- a reference distribution \(q(x)\) produced by:
  - an ideal simulator, or
  - a higher-precision simulator, or
  - a known analytic result.

**Output:**
- fidelity value + CI from bootstrap.

### 6.2 For state fidelity \(F_{state}\)

**Required inputs:**
- full \(\rho\) (or a way to estimate it),
- a target state \(\sigma\).

**Possible protocols:**
- simulator-only exact computation, or
- full state tomography (expensive), or
- randomized benchmarking / cross-entropy / certification variants (advanced).

**SynQc minimum:** mark as SIM-ONLY until a real protocol exists.

### 6.3 For backaction \(B\)

**True backaction requires:**
- \(\rho\) and \(\rho'\) (or a witness of their difference),
- a specified instrument \(\{M_k\}\).

**Hardware protocols (non-trivial):**
- tomography before/after measurement,
- or interference-based coherence witness.

**SynQc minimum:** implement simulator backaction; hardware backaction is PROXY or N/A.

### 6.4 For latency

**Required inputs:**
- timestamps from SynQc backend + provider (if available).

---

## 7) Data contract (what the API should return)

Because this repo is a consumer-facing console, the backend must make the physics contract explicit in the response for each experiment run.

**Add these fields to each experiment record (suggestion):**
- `shots.requested`, `shots.executed`
- `measurement.model`: `"projective"` or `"povm"`
- `measurement.basis` or POVM descriptor
- `noise.model`: `"ideal" | "kraus" | "lindblad" | "hardware_empirical"`
- `kpis[*].name`, `kpis[*].kind`, `kpis[*].value`, `kpis[*].units`
- `kpis[*].definition_ref` (string id like `F_dist_v1`)
- `kpis[*].ci_95` or `stderr` fields when applicable
- `assumptions[]` (human-readable flags like `SIM_ONLY_STATEFIDELITY`)

This keeps the UI “pretty” while keeping the science honest.

---

## 8) Minimal “physics correctness” checklist for SynQc v1

You can ship a real product if you enforce these:

1) Every KPI has:
   - a definition (math),
   - an estimator (algorithm),
   - an uncertainty method (or explicitly “none”),
   - a scope label (SIM / HW / PROXY).

2) Shots are used as sampling repetitions and recorded explicitly.

3) KPIs that are sampling-based show error bars that shrink like \(1/\sqrt{N}\).

4) If a metric is not physically measurable on hardware without extra protocols, SynQc says so.

5) The API returns enough metadata to reproduce the KPI offline.

---

## Appendix A: Glossary (fast)

- **Shot:** one measurement sample.
- **PVM:** projective measurement (orthogonal projectors).
- **POVM:** generalized measurement (positive operators summing to identity).
- **Instrument:** POVM + a rule for post-measurement states (measurement operators).
- **CPTP channel:** physically valid quantum noise/process map.
- **CI:** confidence interval (here: uncertainty interval derived from resampling or analytic approximations).

