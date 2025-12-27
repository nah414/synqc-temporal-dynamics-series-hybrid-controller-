from __future__ import annotations

from .base import AgentMetadata, AgentRunInput, AgentRunOutput, BaseAgent, AgentSelfTestResult


class EchoAgent(BaseAgent):
    metadata = AgentMetadata(
        name="echo",
        version="1.0.0",
        description="Returns whatever you send it. Useful for smoke tests and demos.",
        requires=[],
    )

    def run(self, run_input: AgentRunInput) -> AgentRunOutput:
        return AgentRunOutput(
            agent=self.metadata.name,
            ok=True,
            kpis={"latency_ms": 0},
            data={"echo": {"shots": run_input.shots, "target": run_input.target, "seed": run_input.seed, "params": run_input.params}},
            warnings=[],
        )

    def self_test(self) -> AgentSelfTestResult:
        return AgentSelfTestResult(agent=self.metadata.name, ok=True, details={"echo": "ok"})
