from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any, ClassVar, Dict, List, Optional

from pydantic import BaseModel, Field


class AgentMetadata(BaseModel):
    name: str
    version: str
    description: str
    requires: List[str] = Field(default_factory=list)


class AgentRunInput(BaseModel):
    shots: int = Field(default=256, ge=1, le=100_000)
    target: str = Field(default="simulator")
    seed: Optional[int] = None
    params: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AgentRunOutput(BaseModel):
    agent: str
    ok: bool = True
    kpis: Dict[str, Any] = Field(default_factory=dict)
    data: Dict[str, Any] = Field(default_factory=dict)
    warnings: List[str] = Field(default_factory=list)


class AgentSelfTestResult(BaseModel):
    agent: str
    ok: bool
    checked_at_unix: float = Field(default_factory=lambda: time.time())
    details: Dict[str, Any] = Field(default_factory=dict)
    warnings: List[str] = Field(default_factory=list)


class AgentError(Exception):
    """Base class for all agent errors.

    `public_message` should be safe to show to end users.
    """

    code: str = "agent_error"

    def __init__(self, public_message: str, *, details: Optional[dict[str, Any]] = None):
        super().__init__(public_message)
        self.public_message = public_message
        self.details = details or {}


class AgentDependencyError(AgentError):
    code = "missing_dependency"


class AgentConfigError(AgentError):
    code = "bad_agent_config"


class AgentRuntimeError(AgentError):
    code = "agent_runtime_error"


class BaseAgent(ABC):
    """Agents are named units of work that can be queued and executed by workers."""

    metadata: ClassVar[AgentMetadata]

    @classmethod
    def info(cls) -> AgentMetadata:
        return cls.metadata

    @abstractmethod
    def run(self, run_input: AgentRunInput) -> AgentRunOutput:
        raise NotImplementedError

    def self_test(self) -> AgentSelfTestResult:
        # Default self-test: ensure required deps import.
        warnings: list[str] = []
        missing: list[str] = []

        for pkg in self.metadata.requires:
            try:
                __import__(pkg)
            except Exception:
                missing.append(pkg)

        if missing:
            return AgentSelfTestResult(
                agent=self.metadata.name,
                ok=False,
                details={"missing_dependencies": missing},
                warnings=warnings,
            )

        return AgentSelfTestResult(agent=self.metadata.name, ok=True, details={"deps_ok": True}, warnings=warnings)
