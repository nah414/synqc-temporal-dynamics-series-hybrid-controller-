from __future__ import annotations

import os
import time
from typing import Any, Dict, Optional

from fastapi import FastAPI
from pydantic import BaseModel, Field

APP_NAME = "agent-grover"
STARTED_AT = time.time()

app = FastAPI(title=APP_NAME, version="0.1.0")


class GroverRunRequest(BaseModel):
    prompt: str = Field(..., description="User prompt/task input")
    session_id: Optional[str] = Field(None, description="Optional session identifier")
    dry_run: bool = Field(True, description="Safe mode: no external execution, returns stubbed response")


class GroverRunResponse(BaseModel):
    ok: bool
    agent: str
    latency_ms: int
    dry_run: bool
    result: Dict[str, Any]


@app.get("/health")
def health() -> Dict[str, Any]:
    return {
        "ok": True,
        "service": APP_NAME,
        "uptime_s": round(time.time() - STARTED_AT, 3),
        "mode": os.getenv("SYNQC_MODE", "local"),
    }


@app.post("/run", response_model=GroverRunResponse)
def run(req: GroverRunRequest) -> GroverRunResponse:
    t0 = time.time()

    # v0.1 sandbox behavior: deterministic and safe.
    if req.dry_run:
        payload = {
            "message": "Grover sandbox received prompt (dry_run)",
            "prompt_preview": req.prompt[:200],
            "session_id": req.session_id,
        }
    else:
        payload = {
            "message": "Non-dry-run is not wired yet in sandbox v0.1",
            "action_hint": "Set dry_run=true until model/hardware wiring is enabled",
        }

    latency_ms = int((time.time() - t0) * 1000)
    return GroverRunResponse(ok=True, agent="grover", latency_ms=latency_ms, dry_run=req.dry_run, result=payload)
