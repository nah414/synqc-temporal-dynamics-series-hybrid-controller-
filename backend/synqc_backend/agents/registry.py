from __future__ import annotations

from typing import List

from .base import AgentMetadata, BaseAgent, AgentError
from .echo import EchoAgent

_AGENT_TYPES: list[type[BaseAgent]] = [EchoAgent]

try:  # pragma: no cover
    from .grover import GroverSearchAgent
    _AGENT_TYPES.append(GroverSearchAgent)
except Exception:
    pass


def list_agents() -> List[AgentMetadata]:
    return [t.info() for t in _AGENT_TYPES]


def get_agent(name: str) -> BaseAgent:
    for t in _AGENT_TYPES:
        if t.info().name == name:
            return t()
    raise AgentError(f"Unknown agent: {name}", details={"known_agents": [t.info().name for t in _AGENT_TYPES]})
