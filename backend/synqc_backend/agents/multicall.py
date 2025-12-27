from __future__ import annotations

import asyncio
import time
from typing import Any, Dict

from ..config import settings
from ..physics_contract import infer_contract
from ..models import (
    ExperimentPreset,
    MeasurementDescriptor,
    NoiseDescriptor,
    RunExperimentResponse,
    ShotUsage,
)
from ..orchestration import (
    HttpCallSpec,
    PollHttpStep,
    Workflow,
    WorkflowContext,
    build_workflow_context,
    get_event_store,
)


async def run_multicall_agent(experiment_id: str, run_input: Dict[str, Any]) -> RunExperimentResponse:
    """Execute a multi-call workflow and return a run bundle."""

    event_store = get_event_store()
    ctx: WorkflowContext = build_workflow_context(experiment_id, event_store=event_store)

    provider_base = "https://provider.example.com"
    workflow = Workflow(
        steps=[
            PollHttpStep(
                name="provider_job",
                start_spec=HttpCallSpec(
                    method="POST",
                    url=f"{provider_base}/jobs",
                    json={"program": run_input.get("program", "..."), "shots": run_input.get("shot_budget", 0)},
                    retries=2,
                    timeout_seconds=10.0,
                ),
                poll_spec_fn=lambda c: HttpCallSpec(
                    method="GET",
                    url=f"{provider_base}/jobs/{c.state['provider_job.start']['job_id']}",
                    retries=2,
                    timeout_seconds=10.0,
                ),
                is_done_fn=lambda payload: payload.get("status") in {"SUCCEEDED", "FAILED"},
                interval_seconds=1.5,
                timeout_seconds=600.0,
                save_as="provider_job_status",
            )
        ]
    )

    await workflow.run(ctx)

    shot_budget = int(run_input.get("shot_budget") or settings.default_shot_budget)
    hardware_target = run_input.get("hardware_target", "sim_local")
    contract = infer_contract(
        target=hardware_target,
        shots_requested=shot_budget,
        shots_executed=shot_budget,
        n_qubits=run_input.get("qubits_used") or 18,
        backend_id=None,
    )

    kpis = Workflow.kpi_bundle_from_trace(ctx, shot_budget)
    created_at = time.time()

    return RunExperimentResponse(
        id=experiment_id,
        preset=ExperimentPreset.MULTICALL_DUAL_CLOCKING,
        hardware_target=hardware_target,
        kpis=kpis,
        created_at=created_at,
        shots=ShotUsage(requested=shot_budget, executed=kpis.shots_used),
        measurement=MeasurementDescriptor(
            model=contract.measurement.model,
            basis=contract.measurement.basis,
            povm=contract.measurement.povm,
            descriptor=contract.measurement.notes,
        ),
        noise=NoiseDescriptor(
            model=contract.noise.model,
            params=contract.noise.params,
            descriptor=contract.noise.notes,
        ),
        assumptions=list(contract.assumptions),
        qubits_used=contract.assumptions.get("n_qubits", 18)
        if isinstance(contract.assumptions, dict)
        else 18,
        notes=run_input.get("notes"),
        control_profile=run_input.get("control_overrides"),
        physics_contract=contract,
        kpi_details=None,
        kpi_observations=None,
        artifacts={"workflow_state": ctx.state},
        workflow_trace=ctx.trace,
    )


def run_sync_multicall_agent(experiment_id: str, run_input: Dict[str, Any]) -> RunExperimentResponse:
    return asyncio.run(run_multicall_agent(experiment_id, run_input))
