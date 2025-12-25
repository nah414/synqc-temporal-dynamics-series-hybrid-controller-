from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

import pytest
try:
    from fastapi.testclient import TestClient
except Exception:  # noqa: BLE001 - allow environments without full httpx support
    TestClient = None  # type: ignore

from synqc_backend.api import app, settings  # noqa: E402


@pytest.mark.skipif(TestClient is None, reason="httpx not installed for TestClient")
def test_budget_exhaustion_http_detail(monkeypatch):
    # Force a tiny session budget so the first request exceeds it
    monkeypatch.setattr(settings, "allow_remote_hardware", True, raising=False)
    monkeypatch.setattr(settings, "max_shots_per_session", 1, raising=False)
    monkeypatch.setattr(settings, "max_shots_per_experiment", 1, raising=False)
    monkeypatch.setattr(settings, "require_api_key", False, raising=False)

    client = TestClient(app)

    resp = client.post("/runs", json={"preset": "health", "hardware_target": "sim_local", "shot_budget": 2})
    assert resp.status_code == 202
    run_id = resp.json()["id"]

    data = {}
    for _ in range(10):
        status = client.get(f"/runs/{run_id}")
        assert status.status_code == 200
        data = status.json()
        if data["status"] in {"failed", "succeeded"}:
            break
    assert data.get("status") == "failed"
    detail = data.get("error_detail") or {}
    assert detail.get("code") == "BUDGET_EXHAUSTED"
    assert data.get("error_code") == "BUDGET_EXHAUSTED"
