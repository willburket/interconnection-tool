# src/screening.py — preliminary interconnection screening
# Flags potential thermal overloads and radial exposure before a full study.
# This is the core engineering module — the logic mirrors what engineers
# check manually in the first pass of an interconnection evaluation.

from dataclasses import dataclass, field
from enum import Enum
import networkx as nx
import logging

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from config import THERMAL_WARNING_PCT, THERMAL_HIGH_PCT, MIN_TRANSMISSION_PATHS

log = logging.getLogger(__name__)


class RiskLevel(str, Enum):
    LOW    = "LOW"
    MEDIUM = "MEDIUM"
    HIGH   = "HIGH"
    UNKNOWN = "UNKNOWN"


@dataclass
class ScreeningResult:
    substation:           str
    project_mw:           float
    risk_level:           RiskLevel = RiskLevel.UNKNOWN
    thermal_limit_mw:     float = 0.0
    existing_queue_mw:    float = 0.0
    total_proposed_mw:    float = 0.0
    utilization_pct:      float = 0.0
    transmission_paths:   int   = 0
    flags:                list  = field(default_factory=list)
    recommendations:      list  = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "substation":         self.substation,
            "project_mw":         self.project_mw,
            "risk_level":         self.risk_level.value,
            "thermal_limit_mw":   self.thermal_limit_mw,
            "existing_queue_mw":  self.existing_queue_mw,
            "total_proposed_mw":  self.total_proposed_mw,
            "utilization_pct":    round(self.utilization_pct, 1),
            "transmission_paths": self.transmission_paths,
            "flags":              self.flags,
            "recommendations":    self.recommendations,
        }

    def __str__(self) -> str:
        lines = [
            f"\n{'='*55}",
            f"  Screening Result: {self.substation}",
            f"{'='*55}",
            f"  Proposed capacity  : {self.project_mw:,.0f} MW",
            f"  Thermal limit      : {self.thermal_limit_mw:,.0f} MW",
            f"  Existing queue     : {self.existing_queue_mw:,.0f} MW",
            f"  Total proposed     : {self.total_proposed_mw:,.0f} MW",
            f"  Utilization        : {self.utilization_pct:.1f}%",
            f"  Transmission paths : {self.transmission_paths}",
            f"  Risk level         : {self.risk_level.value}",
        ]
        if self.flags:
            lines.append(f"\n  ⚠  Flags:")
            for flag in self.flags:
                lines.append(f"     • {flag}")
        if self.recommendations:
            lines.append(f"\n  ✓  Recommendations:")
            for rec in self.recommendations:
                lines.append(f"     • {rec}")
        lines.append(f"{'='*55}\n")
        return "\n".join(lines)


def screen_interconnection_point(
    substation_name: str,
    project_mw:      float,
    G:               nx.Graph,
) -> ScreeningResult:
    """
    Run a preliminary screening check for a new interconnection request.

    Checks:
      1. Thermal utilization (existing queue + proposed vs. rated limit)
      2. Network radialness (number of transmission paths)
      3. Voltage class suitability for project size

    This is a first-pass filter, not a full power flow study.
    """
    result = ScreeningResult(substation=substation_name, project_mw=project_mw)
    name_upper = substation_name.upper().strip()

    # ── Substation lookup ───────────────────────────────────────────────────
    if name_upper not in G.nodes:
        # Try partial match
        matches = [n for n in G.nodes if name_upper in n]
        if not matches:
            result.flags.append(
                f"Substation '{substation_name}' not found in network model. "
                "Verify the POI name against the ERCOT substation list."
            )
            result.risk_level = RiskLevel.UNKNOWN
            return result
        name_upper = matches[0]
        result.substation = name_upper

    node = G.nodes[name_upper]

    # ── Thermal screening ───────────────────────────────────────────────────
    thermal_limit  = node.get("thermal_limit_mw", 0)
    existing_queue = node.get("queued_capacity_mw", 0)
    total_proposed = existing_queue + project_mw

    result.thermal_limit_mw   = thermal_limit
    result.existing_queue_mw  = existing_queue
    result.total_proposed_mw  = total_proposed

    if thermal_limit > 0:
        util = total_proposed / thermal_limit
        result.utilization_pct = util * 100

        if util >= THERMAL_HIGH_PCT:
            result.flags.append(
                f"HIGH thermal utilization ({util:.0%}). "
                f"Network upgrades very likely — expect significant cost allocation."
            )
            result.recommendations.append(
                "Request a detailed facility study before committing to this POI."
            )
        elif util >= THERMAL_WARNING_PCT:
            result.flags.append(
                f"MODERATE thermal utilization ({util:.0%}). "
                "Detailed power flow study required to confirm headroom."
            )
            result.recommendations.append(
                "Consider requesting a pre-application meeting with ERCOT."
            )
        else:
            result.recommendations.append(
                f"Thermal headroom looks adequate ({util:.0%} utilized). "
                "Confirm with a full steady-state study."
            )
    else:
        result.flags.append("Thermal limit not available for this substation.")

    # ── Radial / path screening ─────────────────────────────────────────────
    n_paths = G.degree(name_upper)
    result.transmission_paths = n_paths

    if n_paths < MIN_TRANSMISSION_PATHS:
        result.flags.append(
            f"Only {n_paths} transmission path(s) from this substation. "
            "Radial or weakly-meshed connections may require expensive reactive support."
        )
        result.recommendations.append(
            "Evaluate voltage stability and reactive compensation requirements."
        )

    # ── Voltage class check ─────────────────────────────────────────────────
    max_volt = node.get("max_volt", 0)
    if max_volt > 0:
        recommended_min_mw, recommended_max_mw = _voltage_to_mw_range(max_volt)
        if project_mw > recommended_max_mw:
            result.flags.append(
                f"Project size ({project_mw:.0f} MW) may be oversized for a "
                f"{max_volt:.0f} kV bus (typical range: "
                f"{recommended_min_mw:.0f}–{recommended_max_mw:.0f} MW). "
                "Consider a higher-voltage POI."
            )
        elif project_mw < recommended_min_mw * 0.1:
            result.recommendations.append(
                f"Project may be undersized for a {max_volt:.0f} kV POI — "
                "lower-voltage interconnection may be more cost-effective."
            )

    # ── Overall risk rating ─────────────────────────────────────────────────
    high_flags = sum(1 for f in result.flags if "HIGH" in f or "RADIAL" in f.upper() or "oversized" in f.lower())
    med_flags  = sum(1 for f in result.flags if "MODERATE" in f)

    if high_flags >= 2:
        result.risk_level = RiskLevel.HIGH
    elif high_flags == 1 or med_flags >= 2:
        result.risk_level = RiskLevel.MEDIUM
    elif result.flags:
        result.risk_level = RiskLevel.MEDIUM
    else:
        result.risk_level = RiskLevel.LOW

    return result


def _voltage_to_mw_range(voltage_kv: float) -> tuple[float, float]:
    """
    Rough guidance on typical project sizes by voltage class.
    Source: ERCOT planning experience / industry norms.
    """
    if voltage_kv >= 345:
        return (300, 3000)
    elif voltage_kv >= 138:
        return (100, 600)
    elif voltage_kv >= 69:
        return (20, 200)
    else:
        return (1, 50)


def batch_screen(
    substation_names: list[str],
    project_mw: float,
    G: nx.Graph,
) -> list[ScreeningResult]:
    """
    Screen multiple candidate POIs for the same project.
    Useful for comparing alternative interconnection points.
    """
    results = [screen_interconnection_point(s, project_mw, G) for s in substation_names]
    results.sort(key=lambda r: (r.risk_level.value, -r.utilization_pct))
    return results
