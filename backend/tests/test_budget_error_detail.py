from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from synqc_backend.engine import BudgetExceeded
from synqc_backend.jobs import JobQueue, JobRecord
from synqc_backend.models import RunExperimentRequest, ExperimentPreset


def _always_budget_exceeded(req: RunExperimentRequest, session_id: str):
    raise BudgetExceeded(remaining=0)


def test_budget_exceeded_sets_structured_error():
    queue = JobQueue(_always_budget_exceeded, max_workers=1)
    record = JobRecord(job_id="t1", request=RunExperimentRequest(preset=ExperimentPreset.HEALTH, hardware_target="sim_local"))

    queue._run_job(record, session_id="s1")  # type: ignore[attr-defined] - internal use for test

    assert record.status == "failed"
    assert record.error_detail is not None
    assert record.error_detail.get("code") == "session_budget_exhausted"
    assert record.error_detail.get("remaining") == 0
