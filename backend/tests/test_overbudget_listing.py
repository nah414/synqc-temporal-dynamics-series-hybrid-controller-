from pathlib import Path
import sys

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

try:
    from fastapi.testclient import TestClient
except RuntimeError:
    TestClient = None  # type: ignore

from synqc_backend.api import app, settings  # noqa: E402


@pytest.mark.skipif(TestClient is None, reason="httpx not installed for TestClient")
def test_overbudget_run_persists_failure_for_listing(monkeypatch):
    # Force small budget so submission fails and is persisted
    monkeypatch.setattr(settings, "allow_remote_hardware", True, raising=False)
    monkeypatch.setattr(settings, "max_shots_per_session", 1, raising=False)
    monkeypatch.setattr(settings, "max_shots_per_experiment", 1, raising=False)
    monkeypatch.setattr(settings, "require_api_key", False, raising=False)

    client = TestClient(app)

    resp = client.post("/runs", json={"preset": "health", "hardware_target": "sim_local", "shot_budget": 2})
    assert resp.status_code == 202
    run_id = resp.json()["id"]

    status = client.get(f"/runs/{run_id}").json()
    assert status["status"] == "failed"

    listing = client.get("/experiments/recent?limit=10").json()
    found = next((r for r in listing if r["id"] == run_id), None)
    assert found is not None
    assert found.get("error_detail", {}).get("code") == "session_budget_exhausted"
