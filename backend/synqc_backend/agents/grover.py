from __future__ import annotations

import math
import time
from typing import Any, Dict, Optional

from .base import (
    AgentConfigError,
    AgentDependencyError,
    AgentMetadata,
    AgentRunInput,
    AgentRunOutput,
    BaseAgent,
    AgentSelfTestResult,
)


def _build_grover_circuit(n_qubits: int, marked_state: str, iterations: int):
    try:
        from qiskit import QuantumCircuit  # type: ignore
    except Exception as e:  # pragma: no cover
        raise AgentDependencyError(
            "Qiskit is not installed. Install it with `pip install -e backend[qiskit]`.",
            details={"import_error": str(e)},
        )

    if len(marked_state) != n_qubits or any(c not in "01" for c in marked_state):
        raise AgentConfigError(
            "marked_state must be a bitstring with length == n_qubits (example: n_qubits=3, marked_state='101').",
            details={"n_qubits": n_qubits, "marked_state": marked_state},
        )

    qc = QuantumCircuit(n_qubits, n_qubits)
    qc.h(range(n_qubits))

    def apply_oracle():
        for i, bit in enumerate(marked_state):
            if bit == "0":
                qc.x(i)

        qc.h(n_qubits - 1)
        if n_qubits == 1:
            qc.z(0)
        elif n_qubits == 2:
            qc.cz(0, 1)
        else:
            qc.mcx(list(range(n_qubits - 1)), n_qubits - 1)
        qc.h(n_qubits - 1)

        for i, bit in enumerate(marked_state):
            if bit == "0":
                qc.x(i)

    def apply_diffusion():
        qc.h(range(n_qubits))
        qc.x(range(n_qubits))

        qc.h(n_qubits - 1)
        if n_qubits == 1:
            qc.z(0)
        elif n_qubits == 2:
            qc.cz(0, 1)
        else:
            qc.mcx(list(range(n_qubits - 1)), n_qubits - 1)
        qc.h(n_qubits - 1)

        qc.x(range(n_qubits))
        qc.h(range(n_qubits))

    for _ in range(iterations):
        apply_oracle()
        apply_diffusion()

    qc.measure(range(n_qubits), range(n_qubits))
    return qc


def _run_counts(qc, shots: int, seed: Optional[int] = None) -> Dict[str, int]:
    try:
        from qiskit_aer import Aer  # type: ignore
    except Exception as e:
        raise AgentDependencyError(
            "qiskit-aer is not installed. Install it with `pip install -e backend[qiskit]`.",
            details={"import_error": str(e)},
        )

    backend = Aer.get_backend("aer_simulator")
    run_kwargs: Dict[str, Any] = {"shots": shots}
    if seed is not None:
        run_kwargs["seed_simulator"] = seed

    result = backend.run(qc, **run_kwargs).result()
    counts = result.get_counts()
    if isinstance(counts, list):
        counts = counts[0]
    return dict(counts)


class GroverSearchAgent(BaseAgent):
    metadata = AgentMetadata(
        name="grover_search",
        version="1.0.0",
        description="Runs a Grover search circuit (Qiskit/Aer by default; IBM runtime can be added later).",
        requires=["qiskit"],
    )

    def run(self, run_input: AgentRunInput) -> AgentRunOutput:
        n_qubits = int(run_input.params.get("n_qubits", 3))
        if n_qubits < 1 or n_qubits > 10:
            raise AgentConfigError("n_qubits must be between 1 and 10 for this preset.", details={"n_qubits": n_qubits})

        marked_state = str(run_input.params.get("marked_state", "101")).strip()
        if len(marked_state) != n_qubits:
            marked_state = ("1" * n_qubits)

        N = 2**n_qubits
        iterations = int(run_input.params.get("iterations", max(1, int(math.floor((math.pi / 4) * math.sqrt(N))))))

        started = time.perf_counter()
        qc = _build_grover_circuit(n_qubits=n_qubits, marked_state=marked_state, iterations=iterations)
        counts = _run_counts(qc, shots=run_input.shots, seed=run_input.seed)
        elapsed_ms = (time.perf_counter() - started) * 1000.0

        displayed_key = marked_state[::-1]
        hit_prob = float(counts.get(displayed_key, 0)) / float(run_input.shots)

        fidelity = hit_prob
        backaction = max(0.0, 1.0 - fidelity)

        return AgentRunOutput(
            agent=self.metadata.name,
            ok=True,
            kpis={
                "fidelity": round(fidelity, 6),
                "latency_ms": round(elapsed_ms, 2),
                "backaction": round(backaction, 6),
                "n_qubits": n_qubits,
                "iterations": iterations,
                "marked_state": marked_state,
            },
            data={"counts": counts, "displayed_marked_state_key": displayed_key},
            warnings=[],
        )

    def self_test(self) -> AgentSelfTestResult:
        try:
            out = self.run(AgentRunInput(shots=64, params={"n_qubits": 3, "marked_state": "101", "iterations": 1}))
        except Exception as e:
            return AgentSelfTestResult(agent=self.metadata.name, ok=False, details={"error": str(e)})

        fidelity = float(out.kpis.get("fidelity", 0.0))
        ok = fidelity > 0.2
        details = {"fidelity": fidelity, "kpis": out.kpis}
        warnings: list[str] = []
        if not ok:
            warnings.append("Grover self-test fidelity looked low. Qiskit install may be incomplete.")
        return AgentSelfTestResult(agent=self.metadata.name, ok=ok, details=details, warnings=warnings)
