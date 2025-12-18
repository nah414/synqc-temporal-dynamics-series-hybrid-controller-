from pathlib import Path
import sys
import time

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

try:
    from fastapi.testclient import TestClient
except Exception:  # noqa: BLE001 - allow environments without full httpx support
    TestClient = None  # type: ignore

from synqc_backend.api import app, settings  # noqa: E402


@pytest.mark.skipif(TestClient is None, reason="httpx not installed for TestClient")
def test_qubit_telemetry_tracks_session(monkeypatch):
    monkeypatch.setattr(settings, "require_api_key", False, raising=False)
    monkeypatch.setattr(settings, "allow_remote_hardware", True, raising=False)

    client = TestClient(app)
    headers = {"X-Session-Id": "test-qubit-session"}

    resp = client.post("/runs", json={"preset": "health", "hardware_target": "sim_local"}, headers=headers)
    assert resp.status_code == 202
    run_id = resp.json()["id"]

    status_data = {}
    for _ in range(20):
        status = client.get(f"/runs/{run_id}", headers=headers)
        assert status.status_code == 200
        status_data = status.json()
        if status_data["status"] == "succeeded":
            break
        time.sleep(0.05)

    telemetry = client.get("/telemetry/qubits", headers=headers)
    assert telemetry.status_code == 200
    payload = telemetry.json()

    assert payload["session_total_qubits"] >= 1
    assert payload["last_run_qubits"] >= 1

    listing = client.get("/experiments/recent?limit=5", headers=headers).json()
    target = next((r for r in listing if r["id"] == run_id), None)
    assert target is not None
    assert target.get("qubits_used", 0) >= 1
