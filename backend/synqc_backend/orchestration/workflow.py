from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional

from ..logging_utils import get_logger
from ..models import ExperimentStatus, KpiBundle, WorkflowStep
from .call_client import HttpCallSpec
from .event_store import EventStore, get_event_store

logger = get_logger(__name__)


@dataclass
class WorkflowContext:
    experiment_id: str
    event_store: EventStore
    state: Dict[str, Any]
    trace: List[WorkflowStep]

    def record_event(self, name: str, payload: Dict[str, Any]) -> dict[str, Any]:
        event_payload = {"name": name, "payload": payload}
        stored = self.event_store.append(self.experiment_id, event_payload)
        return stored

    def add_trace(self, step: WorkflowStep) -> None:
        self.trace.append(step)


class PollHttpStep:
    def __init__(
        self,
        *,
        name: str,
        start_spec: HttpCallSpec,
        poll_spec_fn: Callable[[WorkflowContext], HttpCallSpec],
        is_done_fn: Callable[[Dict[str, Any]], bool],
        interval_seconds: float,
        timeout_seconds: float,
        save_as: Optional[str] = None,
    ) -> None:
        self.name = name
        self.start_spec = start_spec
        self.poll_spec_fn = poll_spec_fn
        self.is_done_fn = is_done_fn
        self.interval_seconds = interval_seconds
        self.timeout_seconds = timeout_seconds
        self.save_as = save_as or name

    async def run(self, ctx: WorkflowContext) -> Dict[str, Any]:
        logger.info("Workflow step start", extra={"step": self.name, "experiment_id": ctx.experiment_id})
        start_payload = self._simulate_http(self.start_spec)
        ctx.state[f"{self.name}.start"] = start_payload
        ctx.record_event(f"{self.name}.start", start_payload)
        ctx.add_trace(
            WorkflowStep(
                id=f"{self.name}_start",
                label=f"{self.name} start",
                description=f"Started {self.name} call to {self.start_spec.url}",
                percent_complete=10,
            )
        )

        deadline = time.time() + self.timeout_seconds
        last_payload = start_payload
        attempt = 0
        while time.time() < deadline:
            poll_spec = self.poll_spec_fn(ctx)
            response = self._simulate_http(poll_spec, attempt=attempt, prior_payload=last_payload)
            ctx.state[f"{self.name}.poll.{attempt}"] = response
            ctx.record_event(f"{self.name}.poll", response)
            attempt += 1
            if self.is_done_fn(response):
                ctx.state[self.save_as] = response
                ctx.add_trace(
                    WorkflowStep(
                        id=f"{self.name}_done",
                        label=f"{self.name} done",
                        description=f"{self.name} finished with status={response.get('status')}",
                        percent_complete=85,
                    )
                )
                return response
            await asyncio.sleep(self.interval_seconds)
            last_payload = response

        raise TimeoutError(f"Workflow step {self.name} timed out")

    def _simulate_http(
        self,
        spec: HttpCallSpec,
        *,
        attempt: int = 0,
        prior_payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "url": spec.url,
            "method": spec.method,
            "attempt": attempt,
        }
        if prior_payload and "job_id" in prior_payload:
            payload["job_id"] = prior_payload["job_id"]
        else:
            payload["job_id"] = str(uuid.uuid4())

        # Basic state machine: first poll returns RUNNING, second returns SUCCEEDED.
        if attempt == 0:
            payload["status"] = "RUNNING"
        else:
            payload["status"] = "SUCCEEDED"
            payload["result"] = {"shots_consumed": (spec.json or {}).get("shots", 0)}

        return payload


class Workflow:
    def __init__(self, *, steps: Iterable[PollHttpStep]) -> None:
        self.steps = list(steps)

    async def run(self, ctx: WorkflowContext) -> WorkflowContext:
        for step in self.steps:
            await step.run(ctx)
        return ctx

    @staticmethod
    def kpi_bundle_from_trace(ctx: WorkflowContext, shot_budget: int) -> KpiBundle:
        # Use recorded events to build lightweight KPIs.
        status_payload = ctx.state.get("provider_job_status", {})
        latency_us = None
        if ctx.trace:
            latency_us = float(len(ctx.trace)) * 500_000.0
        backaction = 0.18 if status_payload else 0.22
        fidelity = 0.94 if status_payload else 0.9
        return KpiBundle(
            fidelity=fidelity,
            latency_us=latency_us,
            backaction=backaction,
            raw_counts={"00": shot_budget // 2, "11": shot_budget // 2},
            expected_distribution={"00": 0.5, "11": 0.5},
            shots_used=shot_budget,
            shot_budget=shot_budget,
            status=ExperimentStatus.OK,
        )


def build_workflow_context(experiment_id: str, *, event_store: EventStore | None = None) -> WorkflowContext:
    return WorkflowContext(
        experiment_id=experiment_id,
        event_store=event_store or get_event_store(),
        state={},
        trace=[],
    )
