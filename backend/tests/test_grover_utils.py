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
