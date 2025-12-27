from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class HttpCallSpec:
    method: str
    url: str
    json: Optional[Dict[str, Any]] = None
    retries: int = 0
    timeout_seconds: float = 10.0
    headers: Dict[str, str] = field(default_factory=dict)
