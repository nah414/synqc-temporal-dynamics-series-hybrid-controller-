"""Configuration for the Shor/RSA demo feature.

This module is intentionally tiny and dependency-free so it can be imported anywhere.
"""

from __future__ import annotations

import os


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)).strip())
    except Exception:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    raw = raw.strip().lower()
    return raw in {"1", "true", "yes", "y", "on"}


SYNQC_SHOR_ENABLE: bool = _env_bool("SYNQC_SHOR_ENABLE", True)

# Bit-length safety limit for RSA modulus N.
# Keeping this small prevents turning this demo into a practical crypto attack tool.
SYNQC_SHOR_MAX_N_BITS: int = _env_int("SYNQC_SHOR_MAX_N_BITS", 20)

# Allow UTF-8 text <-> int conversions. If disabled, integer-only RSA is allowed.
SYNQC_SHOR_ALLOW_TEXT: bool = _env_bool("SYNQC_SHOR_ALLOW_TEXT", True)

# Default public exponent (user can override per request).
SYNQC_SHOR_DEFAULT_E: int = _env_int("SYNQC_SHOR_DEFAULT_E", 65537)

# For toy keys, keep bits small; default 12 yields N ~ 24 bits (roughly).
SYNQC_SHOR_DEFAULT_KEY_BITS: int = _env_int("SYNQC_SHOR_DEFAULT_KEY_BITS", 12)

# ----------------------------
# Optional run logging
# ----------------------------

# If set, runs are appended as JSONL lines to this path.
# Example: SYNQC_SHOR_RUN_LOG_PATH=/var/log/synqc_shor_runs.jsonl
SYNQC_SHOR_RUN_LOG_PATH: str = os.getenv("SYNQC_SHOR_RUN_LOG_PATH", "").strip()

# Maximum number of run records to keep in-memory (for /api/shor/runs).
SYNQC_SHOR_RUN_LOG_MAX: int = _env_int("SYNQC_SHOR_RUN_LOG_MAX", 200)

# Include step-by-step timing in responses (useful for your "temporal sequence" UI).
SYNQC_SHOR_INCLUDE_STEPS: bool = _env_bool("SYNQC_SHOR_INCLUDE_STEPS", True)
