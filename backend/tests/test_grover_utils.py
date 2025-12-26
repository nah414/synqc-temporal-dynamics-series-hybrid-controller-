import pytest

from synqc_backend import grover_utils as grover
from synqc_backend.grover_utils import GroverConfig


def test_min_shots_for_confidence_invalid_args():
    # eps must be > 0
    with pytest.raises(ValueError):
        grover.min_shots_for_confidence(eps=0.0, delta=0.1)
    with pytest.raises(ValueError):
        grover.min_shots_for_confidence(eps=-1.0, delta=0.1)

    # delta must be in (0, 1)
    with pytest.raises(ValueError):
        grover.min_shots_for_confidence(eps=0.1, delta=0.0)
    with pytest.raises(ValueError):
        grover.min_shots_for_confidence(eps=0.1, delta=1.0)
    with pytest.raises(ValueError):
        grover.min_shots_for_confidence(eps=0.1, delta=1.5)


def test_success_probability_empty_counts_and_no_marked():
    counts: dict[str, int] = {}
    marked: set[str] = set()

    prob = grover.success_probability(counts=counts, marked=marked)

    assert prob == 0.0


def test_ideal_marked_distribution_invalid_qubits():
    with pytest.raises(ValueError):
        grover.ideal_marked_distribution(n_qubits=0, marked=[])
    with pytest.raises(ValueError):
        grover.ideal_marked_distribution(n_qubits=-1, marked=["0"])


def test_ideal_marked_distribution_empty_marked_uniform():
    n_qubits = 2
    marked: list[str] = []

    dist = grover.ideal_marked_distribution(n_qubits=n_qubits, marked=marked)

    # All computational basis states for n_qubits should be present
    expected_states = {format(i, f"0{n_qubits}b") for i in range(2**n_qubits)}
    assert set(dist.keys()) == expected_states

    # Uniform distribution over all states
    for p in dist.values():
        assert p == pytest.approx(1.0 / (2**n_qubits))

    assert sum(dist.values()) == pytest.approx(1.0)


def test_ideal_marked_distribution_marked_states_have_higher_mass():
    n_qubits = 3
    marked = ["101", "010"]

    dist = grover.ideal_marked_distribution(n_qubits=n_qubits, marked=marked)

    # Probabilities form a valid distribution
    assert sum(dist.values()) == pytest.approx(1.0)
    for p in dist.values():
        assert 0.0 <= p <= 1.0

    marked_probabilities = [dist[state] for state in marked]
    unmarked_probabilities = [dist[state] for state in dist.keys() if state not in marked]

    # All marked states should have strictly higher probability than any unmarked state
    assert marked_probabilities  # sanity: non-empty
    assert unmarked_probabilities  # sanity: non-empty
    assert min(marked_probabilities) > max(unmarked_probabilities)


def test_energy_aware_hits_cap_without_success(monkeypatch):
    shot_sequence: list[int] = []
    last_counts: dict[str, int] | None = None

    def fake_run(cfg: GroverConfig):
        nonlocal last_counts
        shot_sequence.append(cfg.shots)
        last_counts = {"000": cfg.shots - 1, "101": 1}
        return last_counts

    monkeypatch.setattr(grover, "run_grover", fake_run)

    cfg = GroverConfig(
        n_qubits=3,
        marked=["101"],
        iterations=1,
        shots=16,
        seed_sim=None,
    )
    max_shots_cap = 64
    target_success = 0.9

    shots_used, counts, success = grover.energy_aware_search(
        cfg,
        target_success=target_success,
        eps=0.2,
        delta=0.05,
        max_shots_cap=max_shots_cap,
        verbose=False,
    )

    # We should exhaust the available shot budget
    assert shots_used == max_shots_cap

    # The returned counts should match those from the final Grover run
    assert last_counts is not None
    assert counts == last_counts

    # Success should remain below the requested target
    assert success < target_success

    # Sanity check: counts are consistent with the reported shots_used
    assert sum(counts.values()) == shots_used
from __future__ import annotations

import types

from synqc_backend import grover
from synqc_backend.hardware_backends import get_backend
from synqc_backend.models import ExperimentPreset


def test_build_and_run_grover_with_mocked_qiskit(monkeypatch):
    operations: dict[str, object] = {}

    class FakeQuantumCircuit:
        def __init__(self, n_qubits: int, classical_bits: int | None = None, name: str | None = None):
            self.n_qubits = n_qubits
            self.classical_bits = classical_bits
            self.name = name or "qc"
            self.ops: list[tuple[object, ...]] = []

        def h(self, idx: int):
            self.ops.append(("h", idx))

        def x(self, idx: int):
            self.ops.append(("x", idx))

        def mcx(self, controls, target):
            self.ops.append(("mcx", tuple(controls), target))

        def compose(self, other, inplace: bool = False):
            self.ops.append(("compose", other.name))
            return self

        def measure(self, qubits, clbits):
            self.ops.append(("measure", tuple(qubits), tuple(clbits)))

    class FakeBackend:
        def __init__(self):
            self.options = {}

        def set_options(self, **kwargs):
            self.options.update(kwargs)

    fake_backend = FakeBackend()

    class FakeResult:
        def __init__(self, shots: int):
            self.shots = shots

        def get_counts(self, _circuit):
            return {"101": self.shots // 2, "010": self.shots - (self.shots // 2)}

    class FakeJob:
        def __init__(self, shots: int):
            self._shots = shots

        def result(self):
            return FakeResult(self._shots)

    def fake_execute(circuit, backend, shots):
        operations["circuit"] = circuit
        return FakeJob(shots)

    class FakeAer:
        @staticmethod
        def get_backend(name: str):
            assert name == "qasm_simulator"
            return fake_backend

    def fake_require_qiskit(require_aer: bool = False):
        return FakeQuantumCircuit, FakeAer, fake_execute, types.SimpleNamespace()

    monkeypatch.setattr(grover, "_require_qiskit", fake_require_qiskit)

    cfg = grover.GroverConfig(n_qubits=3, marked=["101", "010"], iterations=1, shots=24, seed_sim=13)
    circuit = grover.build_grover_circuit(cfg)
    assert any(op[0] == "measure" for op in circuit.ops)

    counts = grover.run_grover(cfg)

    assert sum(counts.values()) == cfg.shots
    assert fake_backend.options.get("seed_simulator") == cfg.seed_sim
    assert operations["circuit"].ops  # build path executed


def test_energy_aware_respects_cap(monkeypatch):
    shot_sequence: list[int] = []

    def fake_run(cfg: grover.GroverConfig):
        shot_sequence.append(cfg.shots)
        if cfg.shots < 40:
            return {"000": cfg.shots}
        return {"101": cfg.shots}

    monkeypatch.setattr(grover, "run_grover", fake_run)

    cfg = grover.GroverConfig(n_qubits=3, marked=["101"], iterations=1, shots=16, seed_sim=None)
    shots_used, counts, success = grover.energy_aware_search(
        cfg, target_success=0.9, eps=0.2, delta=0.05, max_shots_cap=64, verbose=False
    )

    assert shot_sequence[0] >= 16
    assert shots_used <= 64
    assert success >= 0.9
    assert sum(counts.values()) == shots_used


def test_local_simulator_grover_preset_obeys_budget(monkeypatch):
    monkeypatch_calls: list[int] = []

    def fake_run_grover(cfg: grover.GroverConfig):
        # Minimal stand-in so the Grover preset exercises the real shot budgeting logic
        monkeypatch_calls.append(cfg.shots)
        return {"10101": cfg.shots // 2, "01010": cfg.shots - (cfg.shots // 2)}

    monkeypatch.setattr(grover, "run_grover", fake_run_grover)

    backend = get_backend("sim_local")
    result = backend.run_experiment(ExperimentPreset.GROVER_DEMO, shot_budget=128)

    assert result.shots_used <= 128
    assert result.raw_counts
    assert result.expected_distribution
    assert result.shot_budget == 128
    assert monkeypatch_calls  # ensure our stub executed
