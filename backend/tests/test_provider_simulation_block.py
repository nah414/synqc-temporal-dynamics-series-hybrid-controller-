from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi import HTTPException

from synqc_backend.api import _enqueue_run, settings
from synqc_backend.models import ExperimentPreset, RunExperimentRequest


def test_provider_simulation_disabled_returns_403(monkeypatch):
    # Enable remote hardware, disable provider simulation, and bypass API key for the test
    monkeypatch.setattr(settings, "allow_remote_hardware", True, raising=False)
    monkeypatch.setattr(settings, "allow_provider_simulation", False, raising=False)
    monkeypatch.setattr(settings, "require_api_key", False, raising=False)

    request = RunExperimentRequest(
        preset=ExperimentPreset.HEALTH,
        hardware_target="aws_braket",
    )

    with pytest.raises(HTTPException) as exc:
        _enqueue_run(request, session_id="test-session")

    assert exc.value.status_code == 403
    detail = exc.value.detail
    assert isinstance(detail, dict)
    assert detail.get("code") == "PROVIDER_SIM_DISABLED"
    assert "Provider simulation is disabled" in detail.get("error_message", "")


def test_remote_hardware_disabled(monkeypatch):
    monkeypatch.setattr(settings, "allow_remote_hardware", False, raising=False)
    monkeypatch.setattr(settings, "require_api_key", False, raising=False)

    request = RunExperimentRequest(
        preset=ExperimentPreset.HEALTH,
        hardware_target="aws_braket",
    )

    with pytest.raises(HTTPException) as exc:
        _enqueue_run(request, session_id="test-session")

    assert exc.value.status_code == 403
    assert exc.value.detail.get("code") == "REMOTE_DISABLED"


def test_unknown_hardware_target(monkeypatch):
    monkeypatch.setattr(settings, "allow_remote_hardware", True, raising=False)
    monkeypatch.setattr(settings, "require_api_key", False, raising=False)

    request = RunExperimentRequest(
        preset=ExperimentPreset.HEALTH,
        hardware_target="nonexistent",
    )

    with pytest.raises(HTTPException) as exc:
        _enqueue_run(request, session_id="test-session")

    assert exc.value.status_code == 400
    assert exc.value.detail.get("code") == "INVALID_TARGET"
