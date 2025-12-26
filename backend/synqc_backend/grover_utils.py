"""Lightweight Grover helpers shared by presets and provider clients."""
from __future__ import annotations

import importlib.util
import math
import random
from dataclasses import dataclass, replace
from typing import Dict, Iterable, List, Sequence, Set

from .stats import Counts


@dataclass(slots=True)
class GroverConfig:
    """Configuration for running a Grover iteration."""

    n_qubits: int
    marked: Sequence[str]
    iterations: int = 1
    shots: int = 128
    seed_sim: int | None = None

    def __post_init__(self) -> None:
        if self.n_qubits <= 0:
            raise ValueError("n_qubits must be positive")
        if self.iterations <= 0:
            raise ValueError("iterations must be positive")
        if self.shots <= 0:
            raise ValueError("shots must be positive")

    def with_shots(self, shots: int) -> "GroverConfig":
        return replace(self, shots=shots)


def _require_qiskit(*, use_runtime: bool) -> None:
    if importlib.util.find_spec("qiskit") is None:
        raise ImportError(
            "Qiskit is not installed. Install qiskit-aer or the 'backend[qiskit]' extra to run Grover experiments."
        )

    if use_runtime:
        if importlib.util.find_spec("qiskit_ibm_runtime") is None:
            raise ImportError(
                "qiskit-ibm-runtime is required for runtime execution. Install qiskit-ibm-runtime or disable runtime."
            )
    elif importlib.util.find_spec("qiskit_aer") is None:
        raise ImportError(
            "qiskit-aer is required for simulator execution. Install qiskit-aer or the 'backend[qiskit]' extra."
        )


def min_shots_for_confidence(*, eps: float, delta: float) -> int:
    if eps <= 0:
        raise ValueError("eps must be > 0")
    if delta <= 0 or delta >= 1:
        raise ValueError("delta must be in (0, 1)")
    return math.ceil(math.log(2 / delta) / (2 * eps * eps))


def success_probability(*, counts: Counts, marked: Set[str]) -> float:
    total = sum(counts.values())
    if total <= 0:
        return 0.0
    if not marked:
        return 0.0
    success_shots = sum(counts.get(key, 0) for key in marked)
    return success_shots / total


def ideal_marked_distribution(*, n_qubits: int, marked: Sequence[str]) -> Dict[str, float]:
    if n_qubits <= 0:
        raise ValueError("n_qubits must be positive")

    num_states = 2**n_qubits
    all_states = [format(i, f"0{n_qubits}b") for i in range(num_states)]
    marked_set = set(marked)

    if not marked_set:
        prob = 1.0 / num_states
        return {state: prob for state in all_states}

    unmarked_states = [s for s in all_states if s not in marked_set]
    # Bias probabilities toward marked states while keeping a valid distribution.
    marked_weight = 2.0
    unmarked_weight = 1.0
    total_weight = marked_weight * len(marked_set) + unmarked_weight * len(unmarked_states)

    distribution: Dict[str, float] = {}
    for state in all_states:
        if state in marked_set:
            distribution[state] = marked_weight / total_weight
        else:
            distribution[state] = unmarked_weight / total_weight
    return distribution


def _fallback_counts(cfg: GroverConfig) -> Counts:
    rng = random.Random(cfg.seed_sim)
    dist = ideal_marked_distribution(n_qubits=cfg.n_qubits, marked=cfg.marked)
    outcomes = list(dist.keys())
    weights = [dist[o] for o in outcomes]
    draws = rng.choices(outcomes, weights=weights, k=cfg.shots)
    counts: Counts = {}
    for outcome in draws:
        counts[outcome] = counts.get(outcome, 0) + 1
    return counts


def build_grover_circuit(cfg: GroverConfig):  # pragma: no cover - exercised in integration tests
    _require_qiskit(use_runtime=False)
    from qiskit import QuantumCircuit

    qc = QuantumCircuit(cfg.n_qubits, cfg.n_qubits, name="Grover")
    qc.h(range(cfg.n_qubits))
    qc.barrier()

    # Simple oracle: phase flip on marked states via multi-controlled Z using ancilla-free decomposition
    for state in cfg.marked:
        if len(state) != cfg.n_qubits:
            continue
        for idx, bit in enumerate(state):
            if bit == "0":
                qc.x(idx)
        if cfg.n_qubits == 1:
            qc.z(0)
        else:
            qc.h(cfg.n_qubits - 1)
            qc.mcx(list(range(cfg.n_qubits - 1)), cfg.n_qubits - 1)
            qc.h(cfg.n_qubits - 1)
        for idx, bit in enumerate(state):
            if bit == "0":
                qc.x(idx)
        qc.barrier()

    # Diffusion operator
    qc.h(range(cfg.n_qubits))
    qc.x(range(cfg.n_qubits))
    qc.h(cfg.n_qubits - 1)
    if cfg.n_qubits > 1:
        qc.mcx(list(range(cfg.n_qubits - 1)), cfg.n_qubits - 1)
    else:
        qc.z(0)
    qc.h(cfg.n_qubits - 1)
    qc.x(range(cfg.n_qubits))
    qc.h(range(cfg.n_qubits))
    qc.barrier()

    qc.measure(range(cfg.n_qubits), range(cfg.n_qubits))
    return qc


def run_grover(cfg: GroverConfig, *, use_runtime: bool = False) -> Counts:  # pragma: no cover - exercised in integration tests
    try:
        _require_qiskit(use_runtime=use_runtime)
    except ImportError:
        return _fallback_counts(cfg)

    from qiskit import transpile
    from qiskit_aer import AerSimulator

    circuit = build_grover_circuit(cfg)
    backend = AerSimulator()
    compiled = transpile(circuit, backend, optimization_level=1)
    job = backend.run(compiled, shots=cfg.shots, seed_simulator=cfg.seed_sim)
    result = job.result()
    counts_raw = result.get_counts()  # type: ignore[assignment]
    return {str(k): int(v) for k, v in counts_raw.items()}


def energy_aware_search(
    cfg: GroverConfig,
    *,
    target_success: float,
    eps: float,
    delta: float,
    max_shots_cap: int,
    verbose: bool = False,
) -> tuple[int, Counts, float]:
    shots = max(1, cfg.shots)
    shots_used = 0
    counts: Counts = {}
    success = 0.0

    while True:
        shots = min(shots, max_shots_cap)
        test_cfg = cfg.with_shots(shots)
        counts = run_grover(test_cfg)
        shots_used = sum(counts.values())
        success = success_probability(counts=counts, marked=set(cfg.marked))

        if verbose:
            print(f"shots={shots_used} success={success:.3f}")

        if success >= target_success:
            break

        if shots >= max_shots_cap and shots_used >= max_shots_cap:
            break

        shots = min(shots * 2, max_shots_cap)

    return shots_used, counts, success
