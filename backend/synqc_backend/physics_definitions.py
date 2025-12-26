"""Physics KPI definitions registry for SynQc.

This module is intentionally lightweight: it's a single source of truth for:
  - KPI definition IDs
  - what each KPI means
  - what data + estimator are required
  - whether it's SIM-only or hardware-valid

The goal is to prevent "decorative nouns" in dashboards by giving every KPI
a computable contract.

Add new KPIs by:
  1) defining a new <id> entry in KPI_DEFINITIONS
  2) making sure experiment code references the id in results
  3) (optional) adding CI/uncertainty logic if sampling-based
"""

from __future__ import annotations

from typing import Any, Dict

# Stable IDs are important. Don't rename lightly.
KPI_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "fidelity_dist_v1": {
        "name": "fidelity",
        "kind": "distribution",
        "unit": "unitless",
        "summary": "Classical (distribution) fidelity between measured bitstring distribution and an expected reference distribution.",
        "math": r"F_dist(\hat p, q) = (\sum_x \sqrt{\hat p(x) q(x)})^2",
        "requires": {
            "data": ["counts (bitstring->count) OR probabilities", "shots_executed", "expected_distribution q(x)"],
            "estimator": r"Plug-in estimator using \hat p from counts; optionally bootstrap CI via multinomial resampling.",
        },
        "uncertainty": {
            "type": "bootstrap",
            "notes": "Bootstrap CI width should shrink approximately like N^{-1/2} when shot-noise limited.",
        },
        "simulator_only": False,
        "notes": [
            "This is NOT quantum state fidelity unless you can certify state/process on hardware.",
            "Hardware-valid because it depends only on classical outcome distributions.",
        ],
    },
    "latency_us_v1": {
        "name": "latency_us",
        "kind": "system",
        "unit": "us",
        "summary": "Wall-clock latency measured by the backend for a single experiment execution (microseconds).",
        "math": r"\Delta t = t_\mathrm{done} - t_\mathrm{start}",
        "requires": {"data": ["timestamps or duration measurements"], "estimator": "direct measurement"},
        "uncertainty": {"type": "none", "notes": "Latency variability is typically dominated by system/hardware scheduling, not shot noise."},
        "simulator_only": False,
    },
    "backaction_proxy_v1": {
        "name": "backaction",
        "kind": "proxy",
        "unit": "unitless",
        "summary": "A proxy for measurement disturbance. NOT a true quantum backaction measure unless you specify a measurement instrument model and a protocol that can estimate it on hardware.",
        "math": "N/A (proxy; protocol-defined)",
        "requires": {
            "data": ["protocol-specific repeated measurements or paired runs"],
            "estimator": "protocol-specific; must be documented at preset level",
        },
        "uncertainty": {"type": "depends", "notes": "If computed from shot-sampled distributions, attach CI like other sampling-based KPIs."},
        "simulator_only": True,
        "notes": [
            "Mark as SIM_ONLY unless you implement a hardware protocol (e.g., weak measurement, tomography, or certified disturbance bounds)."
        ],
    },
    "unknown_kpi_v1": {
        "name": "unknown_metric",
        "kind": "system",
        "unit": "arbitrary",
        "summary": "Placeholder for unmapped KPI fields so consumers can handle them explicitly.",
        "math": "N/A",
        "requires": {
            "data": ["metric-specific"],
            "estimator": "metric-specific",
        },
        "uncertainty": {"type": "none", "notes": "Attach appropriate CI if sampling-based once definition is known."},
        "simulator_only": False,
    },
}

def get_kpi_definition(definition_id: str) -> Dict[str, Any]:
    if definition_id not in KPI_DEFINITIONS:
        raise KeyError(f"Unknown KPI definition_id: {definition_id}")
    return KPI_DEFINITIONS[definition_id]

def all_kpi_definitions() -> Dict[str, Dict[str, Any]]:
    return KPI_DEFINITIONS
