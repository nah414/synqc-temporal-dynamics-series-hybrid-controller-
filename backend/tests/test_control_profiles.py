from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from synqc_backend.budget import BudgetTracker
from synqc_backend.control_profiles import ControlProfile, ControlProfileStore, ControlProfileUpdate
from synqc_backend.engine import SynQcEngine
from synqc_backend.models import ExperimentPreset, ExperimentStatus, KpiBundle, RunExperimentRequest
from synqc_backend.storage import ExperimentStore


def test_control_profile_store_applies_partial_patch():
    store = ControlProfileStore(persist_path=None)

    updated = store.update(ControlProfileUpdate(feedback_gain=1.2))

    assert updated.feedback_gain == 1.2
    # Unspecified fields should retain defaults
    assert updated.drive_bias == 1.0
    assert updated.thermal_guard_enabled is True


def test_apply_control_profile_influences_kpis():
    engine = SynQcEngine(
        store=ExperimentStore(max_entries=4, persist_path=None),
        budget_tracker=BudgetTracker(redis_url=None),
        control_store=ControlProfileStore(persist_path=None),
    )

    kpis = KpiBundle(
        fidelity=0.9,
        latency_us=50.0,
        backaction=0.25,
        shots_used=100,
        shot_budget=200,
        status=ExperimentStatus.OK,
    )
    controls = ControlProfile(
        drive_bias=1.2,
        probe_window_ns=900,
        feedback_gain=0.8,
        safety_clamp_ns=0,
        thermal_guard_enabled=False,
        tracer_persistence_ms=800,
    )

    adjusted = engine._apply_control_profile(kpis, controls)

    assert adjusted.fidelity > kpis.fidelity
    assert adjusted.latency_us < kpis.latency_us
    assert adjusted.backaction > kpis.backaction
    assert adjusted.status == ExperimentStatus.WARN


def test_run_experiment_returns_control_profile_on_response():
    store = ExperimentStore(max_entries=4, persist_path=None)
    engine = SynQcEngine(
        store=store,
        budget_tracker=BudgetTracker(redis_url=None),
        control_store=ControlProfileStore(persist_path=None),
    )

    req = RunExperimentRequest(
        preset=ExperimentPreset.HEALTH,
        hardware_target="sim_local",
        control_overrides=ControlProfile(drive_bias=1.05, feedback_gain=0.5),
    )

    result = engine.run_experiment(req, session_id="test-session")

    assert result.control_profile is not None
    assert result.control_profile.drive_bias == 1.05
    assert result.kpis.shot_budget > 0
    assert result.workflow_trace, "Workflow trace should be included for UI orchestration"

    # The persisted summary should include the control profile for auditability.
    summaries = store.list_recent(limit=1)
    assert summaries[0].control_profile is not None
    assert summaries[0].control_profile.drive_bias == 1.05
