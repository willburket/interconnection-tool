# tests/test_screening.py

import networkx as nx
import pytest
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from src.screening import screen_interconnection_point, RiskLevel


@pytest.fixture
def simple_graph():
    """Minimal network graph for screening tests."""
    G = nx.Graph()
    G.add_node(
        "TRAVIS 138KV",
        lat=30.25, lon=-97.75,
        thermal_limit_mw=400.0,
        queued_capacity_mw=100.0,   # 100 MW already in queue
        max_volt=138,
        min_volt=69,
        lines=4,
    )
    G.add_node("NEIGHBOR A", lat=30.3, lon=-97.8, thermal_limit_mw=400.0, queued_capacity_mw=0.0, max_volt=138, lines=3)
    G.add_node("NEIGHBOR B", lat=30.2, lon=-97.7, thermal_limit_mw=400.0, queued_capacity_mw=0.0, max_volt=138, lines=3)
    G.add_edge("TRAVIS 138KV", "NEIGHBOR A")
    G.add_edge("TRAVIS 138KV", "NEIGHBOR B")

    G.add_node(
        "RADIAL SUB",
        lat=30.5, lon=-98.0,
        thermal_limit_mw=100.0,
        queued_capacity_mw=80.0,    # already heavily loaded
        max_volt=69,
        min_volt=12,
        lines=1,
    )
    G.add_edge("RADIAL SUB", "TRAVIS 138KV")
    return G


def test_low_risk_project(simple_graph):
    result = screen_interconnection_point("TRAVIS 138KV", 50.0, simple_graph)
    # 100 existing + 50 new = 150 / 400 = 37.5% — should be LOW
    assert result.risk_level == RiskLevel.LOW
    assert result.utilization_pct == pytest.approx(37.5)


def test_high_risk_overloaded(simple_graph):
    result = screen_interconnection_point("TRAVIS 138KV", 320.0, simple_graph)
    # 100 + 320 = 420 / 400 = 105% — should be HIGH
    assert result.risk_level == RiskLevel.HIGH
    assert any("HIGH" in f for f in result.flags)


def test_radial_flag(simple_graph):
    # RADIAL SUB has only 1 path → should flag radial warning
    result = screen_interconnection_point("RADIAL SUB", 10.0, simple_graph)
    assert any("path" in f.lower() or "radial" in f.lower() for f in result.flags)


def test_unknown_substation(simple_graph):
    result = screen_interconnection_point("DOES NOT EXIST", 100.0, simple_graph)
    assert result.risk_level == RiskLevel.UNKNOWN
    assert len(result.flags) > 0
