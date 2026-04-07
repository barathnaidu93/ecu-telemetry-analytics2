"""
Unit Normalization V2 - Edge Case & Integration Tests (No Pytest Version)
Covers boundary conditions, degenerate inputs, and real-world edge cases.
"""
import sys
import os

# Resolve backend/ as the root so all module imports work
# regardless of whether this file is run from backend/ or backend/tests/
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import pandas as pd
import numpy as np
from utils.unit_utils import (
    normalize_units,
    _detect_map_unit,
    _detect_afr_unit,
    _detect_tps_unit,
    _detect_anomalies,
    _capture_original_stats,
)


def test_map_detection():
    print("  Testing MAP Detection...")
    # NA engine
    series = pd.Series([35, 45, 55, 65, 80, 95, 100])
    unit, conf = _detect_map_unit(series)
    assert unit == "kPa", f"NA engine MAP misclassified as {unit}"

    # PSI typical
    series = pd.Series([14.7, 14.7, 15.0, 18.0, 22.0, 28.0, 35.0, 40.0])
    unit, conf = _detect_map_unit(series)
    assert unit == "PSI", f"PSI log misclassified as {unit}"
    print("  [PASS] MAP Detection")


def test_afr_detection():
    print("  Testing AFR Detection...")
    # Lambda stoich
    series = pd.Series([0.99, 1.0, 1.01, 0.98, 1.02])
    unit, conf = _detect_afr_unit(series)
    assert unit == "Lambda"

    # Already AFR
    series = pd.Series([11.5, 12.0, 14.7, 13.8, 14.2])
    unit, conf = _detect_afr_unit(series)
    assert unit == "AFR"
    print("  [PASS] AFR Detection")


def test_tps_detection():
    print("  Testing TPS Detection...")
    # Voltage 0-5V
    series = pd.Series([0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 4.8])
    unit, conf = _detect_tps_unit(series)
    assert unit == "voltage_0-5V", f"5V sensor misclassified as {unit}"

    # Percent partial
    series = pd.Series([42, 55, 60, 68, 75, 78])
    unit, conf = _detect_tps_unit(series)
    assert unit == "percent"
    print("  [PASS] TPS Detection")


def test_integration():
    print("  Testing Full Integration...")
    # Mixed signals
    df = pd.DataFrame({"MAP": [1.0, 1.5, 2.0], "TPS": [0.3, 0.5, 0.8]})
    result = normalize_units(df)
    assert "MAP" in result.attrs["unit_info"]
    assert "TPS" in result.attrs["unit_info"]
    assert "AFR" not in result.attrs["unit_info"]

    # E85 conversion
    df = pd.DataFrame({"AFR": [1.0, 0.9, 1.1]})
    result = normalize_units(df, fuel_type="e85")
    assert np.isclose(result["AFR"].iloc[0], 9.8, atol=0.01)
    print("  [PASS] Full Integration")


if __name__ == "__main__":
    print("\n--- Running Unit Normalization V2 Edge Tests ---")
    test_map_detection()
    test_afr_detection()
    test_tps_detection()
    test_integration()
    print("--- All V2 Edge Case Tests Passed! ---\n")
