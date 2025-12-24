import pathlib

from synqc_backend.budget import BudgetTracker
from synqc_backend.control_profiles import ControlProfileStore
from synqc_backend.engine import SynQcEngine
from synqc_backend.models import ExperimentPreset, RunExperimentRequest
from synqc_backend.storage import ExperimentStore


def test_fidelity_detail_includes_ci_from_counts(tmp_path: pathlib.Path) -> None:
    store = ExperimentStore(max_entries=8)
    budget = BudgetTracker(redis_url=None, session_ttl_seconds=3600, fail_open_on_redis_error=True)
    control_store = ControlProfileStore(persist_path=tmp_path / "controls.json")
    engine = SynQcEngine(store=store, budget_tracker=budget, control_store=control_store)

    req = RunExperimentRequest(
        preset=ExperimentPreset.HEALTH,
        hardware_target="sim_local",
        shot_budget=400,
    )

    result = engine.run_experiment(req, session_id="test-session-ci")

    fidelity_detail = next(d for d in result.kpi_details or [] if d.name == "fidelity")

    assert fidelity_detail.ci95 is not None
    assert len(fidelity_detail.ci95) == 2
    assert result.kpis.raw_counts
    assert sum(result.kpis.raw_counts.values()) == result.kpis.shots_used
    assert result.physics_contract.sampling.shots_executed == result.kpis.shots_used
