"""Resource/latency estimation helpers.

The knapsack QTG paper emphasises evaluating quantum routines using *quantitative*
resource/cycle estimates instead of only asymptotic Big-O language.

We adopt that spirit here by providing a small, transparent estimator for the
Shor/RSA demo.

Important: these are *heuristic* estimates. If Qiskit is available, you should
prefer circuit-based counts (qubits/depth/op counts) produced by Qiskit for the
exact circuit your backend will run.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from .config import SYNQC_SHOR_MAX_N_BITS
from .qiskit_shor import is_qiskit_available


@dataclass(frozen=True)
class ShorResourceEstimate:
    n_bits: int
    max_bits_cap: int
    qiskit_available: bool
    # Heuristic logical qubit estimates (not including decomposition ancillas).
    logical_qubits_textbook: int
    logical_qubits_note: str
    # Extremely rough gate/depth scaling notes.
    depth_scaling: str
    gate_scaling: str

    def as_dict(self) -> Dict[str, Any]:
        return {
            "n_bits": self.n_bits,
            "max_bits_cap": self.max_bits_cap,
            "qiskit_available": self.qiskit_available,
            "logical_qubits_textbook": self.logical_qubits_textbook,
            "logical_qubits_note": self.logical_qubits_note,
            "depth_scaling": self.depth_scaling,
            "gate_scaling": self.gate_scaling,
        }


def estimate_shor_resources(N: int) -> ShorResourceEstimate:
    """Return a pragmatic estimate for Shor factoring resources.

    For a modulus N with n = ceil(log2 N) bits:
    - A "textbook" order-finding layout uses ~2n control qubits + n work qubits
      (so ~3n logical qubits) to get enough phase estimation precision.

    The actual constant factors depend heavily on the modular exponentiation
    construction and whether additional ancillae are used.
    """

    if N <= 0:
        raise ValueError("N must be positive")
    n = int(N).bit_length()

    # Textbook Shor: 2n (phase estimation) + n (work) ~ 3n.
    logical_qubits_textbook = 3 * n

    return ShorResourceEstimate(
        n_bits=n,
        max_bits_cap=int(SYNQC_SHOR_MAX_N_BITS),
        qiskit_available=is_qiskit_available(),
        logical_qubits_textbook=logical_qubits_textbook,
        logical_qubits_note=(
            "Heuristic: ~2n control + n work qubits (~3n) for textbook order finding. "
            "Actual circuits may use more ancillae for arithmetic or fewer with specialised constructions."
        ),
        depth_scaling=(
            "Rough: dominated by modular exponentiation; typically grows superlinearly with n (often quoted ~O(n^3) in naive constructions)."
        ),
        gate_scaling=(
            "Rough: modular exponentiation dominates; multi-controlled operations and adders inflate 2-qubit gate counts quickly as n grows."
        ),
    )
