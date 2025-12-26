"""Energy-aware Grover search utilities adapted from the notebook demo.

These helpers keep the Grover notebook logic close to the backend so it can be
imported in tests or future provider integrations without requiring the entire
notebook. Qiskit remains an optional dependency; informative errors are raised
when it is missing so the rest of the backend keeps working.
"""
from __future__ import annotations

import importlib.util
import math
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

from .stats import Counts


class GroverDependencyError(RuntimeError):
    """Raised when Grover utilities need Qiskit but it is not installed."""


def _require_qiskit(*, require_aer: bool = False) -> Tuple[object, object, object, object]:
    """Ensure Qiskit (and optionally qiskit-aer) is importable before use.

    Returns the imported ``QuantumCircuit``, ``Aer``, ``execute``, and
    ``Statevector`` symbols so callers can avoid redundant imports.
    """

    if importlib.util.find_spec("qiskit") is None:
        raise GroverDependencyError(
            "Qiskit is not installed. Install the 'qiskit' extra to run Grover utilities."
        )
    if require_aer and importlib.util.find_spec("qiskit_aer") is None:
        raise GroverDependencyError(
            "qiskit-aer is required for Grover simulations. Install the 'qiskit' extra."
        )

    from qiskit import Aer, QuantumCircuit, execute  # type: ignore[import-not-found]
    from qiskit.quantum_info import Statevector  # type: ignore[import-not-found]

    return QuantumCircuit, Aer, execute, Statevector


def bitstring_to_int(bitstr: str) -> int:
    """Convert a binary string into its integer value."""

    return int(bitstr, 2)


def build_oracle(num_qubits: int, marked: Iterable[str]):
    """Build a phase oracle for the provided marked states."""

    QuantumCircuit, *_ = _require_qiskit()
    oracle = QuantumCircuit(num_qubits, name="Oracle")
    marked_list = list(marked)
    if not marked_list:
        return oracle

    for bitstring in marked_list:
        if len(bitstring) != num_qubits or not set(bitstring) <= {"0", "1"}:
            raise ValueError(f"Marked string '{bitstring}' must be {num_qubits} bits of 0/1")

        for index, bit in enumerate(reversed(bitstring)):
            if bit == "0":
                oracle.x(index)

        controls = list(range(num_qubits - 1))
        target = num_qubits - 1
        oracle.h(target)
        oracle.mcx(controls, target)
        oracle.h(target)

        for index, bit in enumerate(reversed(bitstring)):
            if bit == "0":
                oracle.x(index)

    return oracle


def build_diffuser(num_qubits: int):
    """Create the Grover diffusion operator."""

    QuantumCircuit, *_ = _require_qiskit()
    diffuser = QuantumCircuit(num_qubits, name="Diffuser")

    for qubit in range(num_qubits):
        diffuser.h(qubit)
        diffuser.x(qubit)

    diffuser.h(num_qubits - 1)
    diffuser.mcx(list(range(num_qubits - 1)), num_qubits - 1)
    diffuser.h(num_qubits - 1)

    for qubit in range(num_qubits):
        diffuser.x(qubit)
        diffuser.h(qubit)

    return diffuser


def optimal_iterations(n_qubits: int, num_marked: int) -> int:
    """Compute the near-optimal Grover iteration count."""

    total_states = 2 ** n_qubits
    marked_states = max(1, num_marked)
    return max(1, int(math.floor((math.pi / 4) * math.sqrt(total_states / marked_states))))


@dataclass
class GroverConfig:
    """Configuration for running Grover's algorithm via Aer."""

    n_qubits: int
    marked: List[str]
    iterations: Optional[int] = None
    shots: int = 128
    seed_sim: Optional[int] = 1337


def build_grover_circuit(cfg: GroverConfig):
    """Assemble a full Grover circuit with oracle, diffuser, and measurement."""

    QuantumCircuit, *_ = _require_qiskit()
    circuit = QuantumCircuit(cfg.n_qubits, cfg.n_qubits, name="Grover")

    for qubit in range(cfg.n_qubits):
        circuit.h(qubit)

    oracle = build_oracle(cfg.n_qubits, cfg.marked)
    diffuser = build_diffuser(cfg.n_qubits)
    iterations = cfg.iterations if cfg.iterations is not None else optimal_iterations(cfg.n_qubits, len(cfg.marked))

    for _ in range(iterations):
        circuit.compose(oracle, inplace=True)
        circuit.compose(diffuser, inplace=True)

    circuit.measure(range(cfg.n_qubits), range(cfg.n_qubits))
    return circuit


def run_grover(cfg: GroverConfig) -> Counts:
    """Simulate Grover's algorithm with Aer and return measurement counts."""

    QuantumCircuit, Aer, execute, _ = _require_qiskit(require_aer=True)
    backend = Aer.get_backend("qasm_simulator")
    if cfg.seed_sim is not None:
        backend.set_options(seed_simulator=cfg.seed_sim)

    circuit = build_grover_circuit(cfg)
    job = execute(circuit, backend=backend, shots=cfg.shots)
    result = job.result()
    return {str(key): int(value) for key, value in result.get_counts(circuit).items()}


def success_probability(counts: Dict[str, int], marked: Iterable[str]) -> float:
    """Estimate success probability from counts against marked solutions."""

    total = sum(counts.values())
    if total == 0:
        return 0.0

    marked_set = set(marked)
    success = sum(value for key, value in counts.items() if key in marked_set)
    return success / total


def min_shots_for_confidence(eps: float = 0.1, delta: float = 0.05) -> int:
    """Hoeffding-style lower bound on samples to bound error within ``eps``.

    This follows the standard additive Chernoff/Hoeffding tail bound for
    bounded Bernoulli trials and does **not** depend on the underlying success
    probability (which keeps this utility conservative for Grover success
    estimation). The caller chooses ``eps`` (half-width) and ``delta``
    (failure probability) to control the confidence interval width.
    """

    if eps <= 0 or delta <= 0 or delta >= 1:
        raise ValueError("eps must be >0 and delta in (0,1)")

    shots = 0.5 * (math.log(2.0 / delta) / (eps**2))
    return int(math.ceil(shots))


def ideal_marked_distribution(n_qubits: int, marked: Iterable[str], background: float = 0.015) -> Dict[str, float]:
    """Construct a normalized reference distribution with emphasis on marked states."""

    marked_list = list(marked)
    total_states = 2**n_qubits
    if total_states <= 0:
        raise ValueError("n_qubits must be positive")

    if not marked_list:
        uniform = 1.0 / total_states
        return {f"{i:0{n_qubits}b}": uniform for i in range(total_states)}

    support = [f"{i:0{n_qubits}b}" for i in range(total_states)]
    ambient_states = [s for s in support if s not in marked_list]
    noise_floor = max(0.0, background)
    ambient_mass = noise_floor * len(ambient_states)
    signal_mass = max(0.0, 1.0 - ambient_mass)
    signal_share = signal_mass / len(marked_list)

    dist: Dict[str, float] = {s: signal_share for s in marked_list}
    for s in ambient_states:
        dist[s] = noise_floor

    norm = sum(dist.values())
    return {k: v / norm for k, v in dist.items()}


def energy_aware_search(
    cfg: GroverConfig,
    *,
    target_success: float = 0.6,
    eps: float = 0.1,
    delta: float = 0.05,
    max_shots_cap: int = 1024,
    verbose: bool = True,
) -> Tuple[int, Counts, float]:
    """Iteratively increase shots until the target success probability is hit."""

    shots = max(16, min(min_shots_for_confidence(eps, delta), max_shots_cap))

    while shots <= max_shots_cap:
        test_cfg = GroverConfig(
            n_qubits=cfg.n_qubits,
            marked=cfg.marked,
            iterations=cfg.iterations,
            shots=shots,
            seed_sim=cfg.seed_sim,
        )
        counts = run_grover(test_cfg)
        success_estimate = success_probability(counts, cfg.marked)
        if verbose:
            print(f"[energy-aware] shots={shots}, success≈{success_estimate:.3f} (target {target_success:.2f})")
        if success_estimate >= target_success:
            return shots, counts, success_estimate

        shots = min(max_shots_cap, int(math.ceil(shots * 1.8)))

    capped_counts = run_grover(
        GroverConfig(
            n_qubits=cfg.n_qubits,
            marked=cfg.marked,
            iterations=cfg.iterations,
            shots=max_shots_cap,
            seed_sim=cfg.seed_sim,
        )
    )
    final_success = success_probability(capped_counts, cfg.marked)
    return max_shots_cap, capped_counts, final_success


def demo_single_marked(n_qubits: int = 5, target: str = "10101", max_shots: int = 128):
    """Helper demo for a single marked bitstring."""

    cfg = GroverConfig(n_qubits=n_qubits, marked=[target])
    return energy_aware_search(cfg, target_success=0.6, max_shots_cap=max_shots)


def demo_multi_marked(n_qubits: int = 5, targets: Optional[List[str]] = None, max_shots: int = 128):
    """Helper demo for multiple marked bitstrings."""

    chosen_targets = targets if targets is not None else ["00011", "10101", "11100"]
    cfg = GroverConfig(n_qubits=n_qubits, marked=list(chosen_targets))
    return energy_aware_search(cfg, target_success=0.6, max_shots_cap=max_shots)
