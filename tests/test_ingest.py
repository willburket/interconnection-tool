# tests/test_ingest.py

import pandas as pd
import pytest
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from src.ingest import clean_queue


@pytest.fixture
def raw_queue_df():
    """Minimal fake queue data that mirrors ERCOT's column structure."""
    return pd.DataFrame({
        "ins #":               ["INS-001", "INS-002", "INS-003"],
        "project name":        ["Solar Farm A", "Wind Farm B", "Battery C"],
        "fuel":                ["Solar", "Wind", "Battery"],
        "ins capacity (mw)":   [200, 300, "not a number"],
        "poi name":            ["TRAVIS 138KV", "WILLIAMSON 138KV", "HAYS 69KV"],
        "status":              ["Active", "Withdrawn", "Active"],
        "application date":    ["2023-01-15", "2022-06-01", "2023-11-30"],
    })


def test_clean_removes_withdrawn(raw_queue_df):
    result = clean_queue(raw_queue_df)
    assert "Wind Farm B" not in result["project_name"].values


def test_clean_casts_capacity(raw_queue_df):
    result = clean_queue(raw_queue_df)
    assert result["capacity_mw"].dtype in ["float64", "float32"]


def test_clean_drops_non_numeric_capacity(raw_queue_df):
    result = clean_queue(raw_queue_df)
    # "not a number" should become NaN and get dropped
    assert result["capacity_mw"].isna().sum() == 0


def test_clean_renames_columns(raw_queue_df):
    result = clean_queue(raw_queue_df)
    assert "project_name" in result.columns
    assert "fuel_type" in result.columns
    assert "capacity_mw" in result.columns
