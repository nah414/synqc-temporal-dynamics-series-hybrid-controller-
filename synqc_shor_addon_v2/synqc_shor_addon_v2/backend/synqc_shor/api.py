"""FastAPI router exposing Shor/RSA demo endpoints.

This v2 router adds:
- run logging (/api/shor/runs) so the feature can plug into your existing
  "Experiment Runs" UI concept
- a lightweight resource estimator (/api/shor/estimate)
- optional step timing metadata to better match your "temporal sequence" UI
"""

from __future__ import annotations

from typing import Optional, Literal, Any, Dict, List

import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .config import (
    SYNQC_SHOR_ENABLE,
    SYNQC_SHOR_ALLOW_TEXT,
    SYNQC_SHOR_DEFAULT_E,
    SYNQC_SHOR_DEFAULT_KEY_BITS,
    SYNQC_SHOR_INCLUDE_STEPS,
    SYNQC_SHOR_MAX_N_BITS,
)
from .estimate import estimate_shor_resources
from .factor import factor_N
from .rsa import (
    generate_rsa_keypair,
    rsa_encrypt_int,
    rsa_decrypt_int,
    modinv,
    int_to_text,
    text_to_int,
)

from .run_store import record_run, list_runs, get_run
from .qiskit_shor import is_qiskit_available


router = APIRouter()


# ----------------------------
# Pydantic models
# ----------------------------

Method = Literal["auto", "qiskit", "classical"]
BackendMode = Literal["aer", "ibm", "custom"]


class FactorRequest(BaseModel):
    N: int = Field(..., description="Composite integer N = p*q to factor (guard-railed sizes by default).")
    method: Method = Field("auto", description="auto | qiskit | classical")
    backend_mode: BackendMode = Field("aer", description="Execution backend for Qiskit Shor: aer | ibm | custom")
    shots: int = Field(1024, ge=1, le=20000, description="Shots for quantum execution (Qiskit Shor only).")  # noqa: E501
    ibm_backend_name: Optional[str] = Field(
        None,
        description="IBM backend name (only if backend_mode=ibm). Can also be set via SYNQC_SHOR_IBM_BACKEND env var.",  # noqa: E501
    )
    provider_backend_name: Optional[str] = Field(
        None,
        description="Backend name exposed by a non-IBM Qiskit provider (backend_mode=custom).",
    )
    provider_loader: Optional[str] = Field(
        None,
        description="Dotted path or module:Class for provider instantiation (backend_mode=custom).",
    )


class FactorResponse(BaseModel):
    run_id: str
    N: int
    p: int
    q: int
    method_used: str
    runtime_ms: float
    steps: Optional[List[Dict[str, Any]]] = None


class RSAKeyGenRequest(BaseModel):
    bits: int = Field(SYNQC_SHOR_DEFAULT_KEY_BITS, ge=4, le=32, description="Bit-length for each prime (guard-railed by default).")  # noqa: E501
    e: int = Field(SYNQC_SHOR_DEFAULT_E, ge=3, description="Public exponent.")


class RSAKeyGenResponse(BaseModel):
    run_id: str
    p: int
    q: int
    N: int
    phi: int
    e: int
    d: int


class RSAEncryptRequest(BaseModel):
    N: int
    e: int
    plaintext_int: Optional[int] = None
    plaintext_text: Optional[str] = None


class RSAEncryptResponse(BaseModel):
    run_id: str
    ciphertext_int: int
    plaintext_int: int


class RSADecryptRequest(BaseModel):
    N: int
    e: int
    ciphertext_int: int
    method: Method = "auto"
    backend_mode: BackendMode = "aer"
    shots: int = Field(1024, ge=1, le=20000)
    ibm_backend_name: Optional[str] = None
    provider_backend_name: Optional[str] = None
    provider_loader: Optional[str] = None


class RSADecryptResponse(BaseModel):
    run_id: str
    plaintext_int: int
    plaintext_text: Optional[str] = None
    p: int
    q: int
    d: int
    method_used: str
    runtime_ms: float
    steps: Optional[List[Dict[str, Any]]] = None


class EstimateRequest(BaseModel):
    N: int = Field(..., description="Composite integer N = p*q to estimate resources for (toy sizes only).")


class EstimateResponse(BaseModel):
    run_id: str
    estimate: Dict[str, Any]


class RunsResponse(BaseModel):
    runs: List[Dict[str, Any]]


# ----------------------------
# Helpers
# ----------------------------


def _dump_model(m: Any) -> Dict[str, Any]:
    """Pydantic v1/v2 compatible dump."""
    if hasattr(m, "model_dump"):
        return m.model_dump()  # type: ignore[attr-defined]
    return m.dict()  # type: ignore[no-any-return]

def _ensure_enabled():
    if not SYNQC_SHOR_ENABLE:
        raise HTTPException(status_code=404, detail="Shor demo feature is disabled.")


def _bad_request(msg: str):
    raise HTTPException(status_code=400, detail=msg)


# ----------------------------
# Helpers
# ----------------------------

def _default_guardrails() -> Dict[str, Any]:
    """Server-advertised guardrails for the UI to mirror."""

    guardrails: Dict[str, Dict[str, Any]] = {
        "auto": {"max": 32000, "label": "auto/aer guardrail ~32,000"},
        "aer": {"max": 32000, "label": "auto/aer guardrail ~32,000"},
        "ibm": {"max": 4096, "label": "IBM Runtime guardrail ~4,096"},
        "custom": {"max": 4096, "label": "custom provider guardrail ~4,096"},
        "classical": {"max": 5_000_000, "label": "classical guardrail ~5,000,000"},
    }

    if SYNQC_SHOR_MAX_N_BITS > 0:
        max_n_cap = (1 << SYNQC_SHOR_MAX_N_BITS) - 1
        for v in guardrails.values():
            if isinstance(v.get("max"), (int, float)):
                v["max"] = min(int(v["max"]), max_n_cap)

    return guardrails


# ----------------------------
# Routes
# ----------------------------

@router.get("/health")
def shor_health():
    _ensure_enabled()
    guardrails = _default_guardrails()
    return {
        "ok": True,
        "feature": "shor_rsa_demo",
        "qiskit_available": is_qiskit_available(),
        "limits": {
            "max_n_bits": SYNQC_SHOR_MAX_N_BITS,
            "guardrails": guardrails,
        },
    }


@router.post("/factor", response_model=FactorResponse)
def shor_factor(req: FactorRequest):
    _ensure_enabled()
    t0 = time.perf_counter()
    req_d = _dump_model(req)
    try:
        res = factor_N(
            req.N,
            method=req.method,
            backend_mode=req.backend_mode,
            shots=req.shots,
            ibm_backend_name=req.ibm_backend_name,
            provider_backend_name=req.provider_backend_name,
            provider_loader=req.provider_loader,
        )

        steps = (
            [
                {"name": s.name, "ms": s.ms, "ok": s.ok, "detail": s.detail}
                for s in (res.steps or [])
            ]
            if SYNQC_SHOR_INCLUDE_STEPS
            else None
        )

        resp_payload: Dict[str, Any] = {
            "N": res.N,
            "p": res.p,
            "q": res.q,
            "method_used": res.method_used,
            "runtime_ms": res.runtime_ms,
            "steps": steps,
        }
        rec = record_run(
            kind="shor_factor",
            ok=True,
            runtime_ms=res.runtime_ms,
            request=req_d,
            response=resp_payload,
        )
        return FactorResponse(run_id=rec.run_id, **resp_payload)
    except Exception as e:
        t1 = time.perf_counter()
        record_run(
            kind="shor_factor",
            ok=False,
            runtime_ms=(t1 - t0) * 1000,
            request=req_d,
            response=None,
            error=str(e),
        )
        _bad_request(str(e))


@router.post("/rsa/generate", response_model=RSAKeyGenResponse)
def rsa_generate(req: RSAKeyGenRequest):
    _ensure_enabled()
    t0 = time.perf_counter()
    req_d = _dump_model(req)
    try:
        kp = generate_rsa_keypair(prime_bits=req.bits, e=req.e)
        t1 = time.perf_counter()
        resp_payload = {"p": kp.p, "q": kp.q, "N": kp.N, "phi": kp.phi, "e": kp.e, "d": kp.d}
        rec = record_run(
            kind="rsa_generate",
            ok=True,
            runtime_ms=(t1 - t0) * 1000,
            request=req_d,
            response=resp_payload,
        )
        return RSAKeyGenResponse(run_id=rec.run_id, **resp_payload)
    except Exception as e:
        t1 = time.perf_counter()
        record_run(
            kind="rsa_generate",
            ok=False,
            runtime_ms=(t1 - t0) * 1000,
            request=req_d,
            response=None,
            error=str(e),
        )
        _bad_request(str(e))


@router.post("/rsa/encrypt", response_model=RSAEncryptResponse)
def rsa_encrypt(req: RSAEncryptRequest):
    _ensure_enabled()

    if req.plaintext_int is None and (req.plaintext_text is None or req.plaintext_text == ""):
        _bad_request("Provide plaintext_int or plaintext_text.")

    t0 = time.perf_counter()
    req_d = _dump_model(req)
    try:
        if req.plaintext_int is not None:
            m = int(req.plaintext_int)
        else:
            if not SYNQC_SHOR_ALLOW_TEXT:
                _bad_request("Text mode disabled by SYNQC_SHOR_ALLOW_TEXT=0.")
            m = text_to_int(req.plaintext_text or "")
        c = rsa_encrypt_int(m, req.N, req.e)
        t1 = time.perf_counter()
        resp_payload = {"ciphertext_int": c, "plaintext_int": m}
        rec = record_run(
            kind="rsa_encrypt",
            ok=True,
            runtime_ms=(t1 - t0) * 1000,
            request=req_d,
            response=resp_payload,
        )
        return RSAEncryptResponse(run_id=rec.run_id, **resp_payload)
    except Exception as e:
        t1 = time.perf_counter()
        record_run(
            kind="rsa_encrypt",
            ok=False,
            runtime_ms=(t1 - t0) * 1000,
            request=req_d,
            response=None,
            error=str(e),
        )
        _bad_request(str(e))


@router.post("/rsa/decrypt", response_model=RSADecryptResponse)
def rsa_decrypt(req: RSADecryptRequest):
    _ensure_enabled()
    t0 = time.perf_counter()
    req_d = _dump_model(req)
    steps: List[Dict[str, Any]] = []
    try:
        # Factor N (Shor auto/fallback)
        fres = factor_N(
            req.N,
            method=req.method,
            backend_mode=req.backend_mode,
            shots=req.shots,
            ibm_backend_name=req.ibm_backend_name,
            provider_backend_name=req.provider_backend_name,
            provider_loader=req.provider_loader,
        )

        if SYNQC_SHOR_INCLUDE_STEPS:
            for s in fres.steps or []:
                steps.append({"name": s.name, "ms": s.ms, "ok": s.ok, "detail": s.detail})

        t_phi0 = time.perf_counter()
        phi = (fres.p - 1) * (fres.q - 1)
        d = modinv(req.e, phi)
        m = rsa_decrypt_int(req.ciphertext_int, req.N, d)
        t_phi1 = time.perf_counter()

        if SYNQC_SHOR_INCLUDE_STEPS:
            steps.append({"name": "derive_private_key+decrypt", "ms": (t_phi1 - t_phi0) * 1000, "ok": True, "detail": None})

        text_out = int_to_text(m) if SYNQC_SHOR_ALLOW_TEXT else None

        t1 = time.perf_counter()
        resp_payload = {
            "plaintext_int": m,
            "plaintext_text": text_out,
            "p": fres.p,
            "q": fres.q,
            "d": d,
            "method_used": fres.method_used,
            "runtime_ms": (t1 - t0) * 1000,
            "steps": steps if SYNQC_SHOR_INCLUDE_STEPS else None,
        }
        rec = record_run(
            kind="rsa_decrypt",
            ok=True,
            runtime_ms=resp_payload["runtime_ms"],
            request=req_d,
            response=resp_payload,
        )
        return RSADecryptResponse(run_id=rec.run_id, **resp_payload)
    except Exception as e:
        t1 = time.perf_counter()
        record_run(
            kind="rsa_decrypt",
            ok=False,
            runtime_ms=(t1 - t0) * 1000,
            request=req_d,
            response=None,
            error=str(e),
        )
        _bad_request(str(e))


@router.post("/estimate", response_model=EstimateResponse)
def shor_estimate(req: EstimateRequest):
    _ensure_enabled()
    t0 = time.perf_counter()
    req_d = _dump_model(req)
    try:
        est = estimate_shor_resources(req.N)
        t1 = time.perf_counter()
        resp_payload = {"estimate": est.as_dict()}
        rec = record_run(
            kind="shor_estimate",
            ok=True,
            runtime_ms=(t1 - t0) * 1000,
            request=req_d,
            response=resp_payload,
        )
        return EstimateResponse(run_id=rec.run_id, estimate=resp_payload["estimate"])
    except Exception as e:
        t1 = time.perf_counter()
        record_run(
            kind="shor_estimate",
            ok=False,
            runtime_ms=(t1 - t0) * 1000,
            request=req_d,
            response=None,
            error=str(e),
        )
        _bad_request(str(e))


@router.get("/runs", response_model=RunsResponse)
def shor_runs(limit: int = 50):
    _ensure_enabled()
    return RunsResponse(runs=list_runs(limit=limit))


@router.get("/runs/{run_id}")
def shor_run_detail(run_id: str):
    _ensure_enabled()
    rec = get_run(run_id)
    if not rec:
        raise HTTPException(status_code=404, detail="run not found")
    return rec
