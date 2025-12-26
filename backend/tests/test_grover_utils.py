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
