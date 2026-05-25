# src/screening.py — preliminary interconnection screening
# Updated: CAISO offshore wind flagging, 500kV voltage class, multi-ISO support

from dataclasses import dataclass, field
from enum import Enum
import networkx as nx
import logging

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from config import (
    ISO, ISO_CONFIG,
    THERMAL_WARNING_PCT, THERMAL_HIGH_PCT, MIN_TRANSMISSION_PATHS,
)

log = logging.getLogger(__name__)


class RiskLevel(str, Enum):
    LOW     = "LOW"
    MEDIUM  = "MEDIUM"
    HIGH    = "HIGH"
    UNKNOWN = "UNKNOWN"


@dataclass
class ScreeningResult:
    substation:           str
    project_mw:           float
    iso:                  ISO = ISO.ERCOT
    fuel_type:            str = "Unknown"
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
            "iso":                self.iso.value,
            "fuel_type":          self.fuel_type,
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
            f"\n{'='*58}",
            f"  [{self.iso.value}] Screening: {self.substation}",
            f"{'='*58}",
            f"  Fuel type          : {self.fuel_type}",
            f"  Proposed capacity  : {self.project_mw:,.0f} MW",
            f"  Thermal limit      : {self.thermal_limit_mw:,.0f} MW",
            f"  Existing queue     : {self.existing_queue_mw:,.0f} MW",
            f"  Total proposed     : {self.total_proposed_mw:,.0f} MW",
            f"  Utilization        : {self.utilization_pct:.1f}%",
            f"  Transmission paths : {self.transmission_paths}",
            f"  Risk level         : {self.risk_level.value}",
        ]
        if self.flags:
            lines.append("\n  ⚠  Flags:")
            for flag in self.flags:
                lines.append(f"     • {flag}")
        if self.recommendations:
            lines.append("\n  ✓  Recommendations:")
            for rec in self.recommendations:
                lines.append(f"     • {rec}")
        lines.append(f"{'='*58}\n")
        return "\n".join(lines)


def screen_interconnection_point(
    substation_name: str,
    project_mw:      float,
    G:               nx.Graph,
    iso:             ISO = ISO.ERCOT,
    fuel_type:       str = "Unknown",
) -> ScreeningResult:
    """
    Run a preliminary screening check for a new interconnection request.

    Checks:
      1. Thermal utilization — existing queue + proposed vs. rated limit
      2. Network radialness — number of transmission paths
      3. Voltage class suitability for the project size
      4. ISO-specific flags — CAISO offshore wind, CAISO 500kV considerations,
         PJM capacity market implications
    """
    result = ScreeningResult(
        substation=substation_name,
        project_mw=project_mw,
        iso=iso,
        fuel_type=fuel_type,
    )
    name_upper = substation_name.upper().strip()

    # ── Substation lookup ────────────────────────────────────────────────────
    if name_upper not in G.nodes:
        matches = [n for n in G.nodes if name_upper in n]
        if not matches:
            result.flags.append(
                f"Substation '{substation_name}' not found in network model. "
                "Verify the POI name against the ISO's published substation list."
            )
            result.risk_level = RiskLevel.UNKNOWN
            return result
        name_upper = matches[0]
        result.substation = name_upper

    node = G.nodes[name_upper]

    # ── Thermal screening ────────────────────────────────────────────────────
    thermal_limit  = node.get("thermal_limit_mw", 0)
    existing_queue = node.get("queued_capacity_mw", 0)
    total_proposed = existing_queue + project_mw

    result.thermal_limit_mw  = thermal_limit
    result.existing_queue_mw = existing_queue
    result.total_proposed_mw = total_proposed

    if thermal_limit > 0:
        util = total_proposed / thermal_limit
        result.utilization_pct = util * 100

        if util >= THERMAL_HIGH_PCT:
            result.flags.append(
                f"HIGH thermal utilization ({util:.0%}). "
                "Network upgrades very likely — expect significant cost allocation."
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
                f"Consider requesting a pre-application meeting with {iso.value}."
            )
        else:
            result.recommendations.append(
                f"Thermal headroom looks adequate ({util:.0%} utilized). "
                "Confirm with a full steady-state study."
            )
    else:
        result.flags.append("Thermal limit not available — check substation data.")

    # ── Radial / path screening ──────────────────────────────────────────────
    n_paths = G.degree(name_upper)
    result.transmission_paths = n_paths

    if n_paths < MIN_TRANSMISSION_PATHS:
        result.flags.append(
            f"Only {n_paths} transmission path(s) detected. "
            "Radial or weakly-meshed connections may require expensive reactive support "
            "and additional stability studies."
        )
        result.recommendations.append(
            "Evaluate voltage stability and reactive compensation (SVCs, STATCOMs)."
        )

    # ── Voltage class suitability ────────────────────────────────────────────
    max_volt = node.get("max_volt", 0)
    if max_volt > 0:
        min_mw, max_mw = _voltage_to_mw_range(max_volt)
        if project_mw > max_mw:
            result.flags.append(
                f"Project ({project_mw:.0f} MW) may be oversized for a "
                f"{max_volt:.0f} kV bus (typical: {min_mw:.0f}–{max_mw:.0f} MW). "
                "Consider a higher-voltage POI."
            )
        elif project_mw < min_mw * 0.1:
            result.recommendations.append(
                f"Project may be undersized for a {max_volt:.0f} kV POI — "
                "a lower-voltage interconnection could reduce cost."
            )

    # ── ISO-specific flags ───────────────────────────────────────────────────
    _apply_iso_flags(result, node, iso, fuel_type)

    # ── Overall risk rating ──────────────────────────────────────────────────
    high_count = sum(1 for f in result.flags if any(
        kw in f.upper() for kw in ["HIGH", "RADIAL", "OVERSIZED"]
    ))
    med_count = sum(1 for f in result.flags if "MODERATE" in f.upper())

    if high_count >= 2:
        result.risk_level = RiskLevel.HIGH
    elif high_count == 1 or med_count >= 2:
        result.risk_level = RiskLevel.MEDIUM
    elif result.flags:
        result.risk_level = RiskLevel.MEDIUM
    else:
        result.risk_level = RiskLevel.LOW

    return result


def _apply_iso_flags(
    result:    ScreeningResult,
    node:      dict,
    iso:       ISO,
    fuel_type: str,
) -> None:
    """Apply ISO-specific screening flags."""

    if iso == ISO.CAISO:
        _caiso_flags(result, node, fuel_type)
    elif iso == ISO.ERCOT:
        _ercot_flags(result, node, fuel_type)
    elif iso == ISO.PJM:
        _pjm_flags(result, node, fuel_type)


def _caiso_flags(result: ScreeningResult, node: dict, fuel_type: str) -> None:
    """CAISO-specific screening flags."""

    # Offshore wind — California's fastest-growing interconnection category
    if fuel_type.lower() == "offshore wind":
        result.flags.append(
            "OFFSHORE WIND: California has no existing offshore wind "
            "transmission infrastructure. Expect CPUC/CAISO coordinated "
            "transmission planning studies and potential new 500kV collector lines."
        )
        result.recommendations.append(
            "Monitor CAISO's Offshore Wind Integration Study and "
            "CPUC's Integrated Resource Planning (IRP) docket for cost allocation rules."
        )
        result.recommendations.append(
            "Consider Humboldt Bay or Morro Bay POI areas per CAISO's "
            "preferred offshore wind landing zones."
        )

    # 500kV consideration — unique to CAISO vs ERCOT
    max_volt = node.get("max_volt", 0)
    if max_volt >= 500 and result.project_mw >= 500:
        result.recommendations.append(
            f"500kV POI available. Large projects (≥500 MW) in CAISO often "
            "benefit from 500kV interconnection to minimize losses and upgrade costs."
        )

    # CAISO's large queue backlog — context flag
    result.recommendations.append(
        "CAISO queue currently exceeds 100 GW. Cluster study timelines "
        "have been 3–5 years — factor this into project schedule."
    )

    # Deliverability vs. energy-only
    result.flags.append(
        "CAISO NOTE: Confirm whether project is seeking Full Capacity "
        "Deliverability Status (FCDS) or Energy Only (EO). "
        "FCDS requires additional network upgrade cost allocation."
    )


def _ercot_flags(result: ScreeningResult, node: dict, fuel_type: str) -> None:
    """ERCOT-specific screening flags."""

    # West Texas congestion — common pain point
    state = node.get("state", "")
    city  = str(node.get("city", "")).upper()
    WEST_TX_CITIES = {"MIDLAND", "ODESSA", "SAN ANGELO", "ABILENE", "SWEETWATER", "SNYDER"}
    if any(c in city for c in WEST_TX_CITIES):
        result.flags.append(
            "West Texas POI: high transmission congestion zone. "
            "Expect significant curtailment risk and potential high network upgrade costs."
        )
        result.recommendations.append(
            "Review ERCOT's Competitive Renewable Energy Zone (CREZ) transmission "
            "capacity data before committing to this POI."
        )

    # ERCOT weather risk (post-Uri)
    if fuel_type.lower() in ("gas", "nuclear"):
        result.recommendations.append(
            "ERCOT requires winterization compliance under SB 3 (2021) "
            "for thermal generators. Confirm weatherization plan is in scope."
        )


def _pjm_flags(result: ScreeningResult, node: dict, fuel_type: str) -> None:
    """PJM-specific screening flags."""

    result.recommendations.append(
        "PJM operates a capacity market (RPM). Confirm whether project "
        "will participate — capacity revenues significantly affect project economics."
    )
    result.recommendations.append(
        "PJM's FERC Order 2023 compliance transition is ongoing. "
        "Study timelines are in flux — confirm current cluster cycle dates."
    )


def _voltage_to_mw_range(voltage_kv: float) -> tuple[float, float]:
    """Typical project size ranges by voltage class."""
    if voltage_kv >= 500:
        return (500, 5000)
    elif voltage_kv >= 345:
        return (300, 3000)
    elif voltage_kv >= 230:
        return (150, 1500)
    elif voltage_kv >= 138:
        return (100, 600)
    elif voltage_kv >= 69:
        return (20, 200)
    else:
        return (1, 50)


def batch_screen(
    substation_names: list[str],
    project_mw:       float,
    G:                nx.Graph,
    iso:              ISO = ISO.ERCOT,
    fuel_type:        str = "Unknown",
) -> list[ScreeningResult]:
    """Screen multiple candidate POIs for the same project."""
    results = [
        screen_interconnection_point(s, project_mw, G, iso, fuel_type)
        for s in substation_names
    ]
    results.sort(key=lambda r: (r.risk_level.value, -r.utilization_pct))
    return results
