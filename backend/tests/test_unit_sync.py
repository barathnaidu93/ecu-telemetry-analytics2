"""
Unit Normalization V2 - Core Tests
Updated to validate: multi-signal detection, confidence scoring,
anomaly logging, original stats preservation, and idempotency flag.
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
from utils.unit_utils import normalize_units


def test_unit_normalization():
    print("\n--- Running Unit Normalization V2 Tests ---")

    # ================================================================
    # 1. MAP: Already kPa (boosted engine, typical values ~101-250)
    # ================================================================
    df_kpa = pd.DataFrame({"MAP": [101.3, 102.0, 100.5, 101.8, 180.0, 220.0]})
    df_kpa = normalize_units(df_kpa)
    assert np.isclose(df_kpa["MAP"].iloc[0], 101.3), "Already kPa should not be scaled"
    assert df_kpa.attrs["unit_confidence"]["MAP"] >= 0.5, "kPa detection should have reasonable confidence"
    assert df_kpa.attrs["original_units"]["MAP"]["unit"] == "kPa", "Should detect kPa"
    print("[PASS] Already kPa - no conversion, confidence stored")

    # ================================================================
    # 2. MAP: BAR -> kPa (atmospheric ~1.0, boosted ~1.5-3.0)
    # ================================================================
    df_bar = pd.DataFrame({"MAP": [1.0, 1.2, 0.9, 1.1, 2.5, 3.0]})
    df_bar = normalize_units(df_bar)
    assert df_bar["MAP"].median() > 50, f"BAR->kPa failed. Median: {df_bar['MAP'].median()}"
    assert df_bar.attrs["unit_info"]["MAP"] == "BAR -> kPa"
    assert df_bar.attrs["original_units"]["MAP"]["stats"]["median"] < 5, \
        "Original stats should reflect BAR values"
    print("[PASS] BAR -> kPa conversion with original stats preserved")

    # ================================================================
    # 3. MAP: PSI -> kPa (atmospheric ~14.7, boosted ~20-50)
    # ================================================================
    df_psi = pd.DataFrame({"MAP": [14.0, 15.0, 14.7, 25.0, 35.0, 45.0]})
    df_psi = normalize_units(df_psi)
    assert df_psi["MAP"].min() > 90, f"PSI->kPa min too low: {df_psi['MAP'].min()}"
    assert df_psi.attrs["unit_info"]["MAP"] == "PSI -> kPa"
    print("[PASS] PSI -> kPa conversion")

    # ================================================================
    # 4. Idempotency via normalization flag
    # ================================================================
    df_repeat = pd.DataFrame({"MAP": [1.0, 1.1, 1.05, 2.0, 2.5]})
    df_repeat = normalize_units(df_repeat)   # First pass: BAR -> kPa
    first_pass_median = df_repeat["MAP"].median()
    assert df_repeat.attrs["_units_normalized"] is True, "Flag should be set"
    df_repeat = normalize_units(df_repeat)   # Second pass: should skip entirely
    assert df_repeat["MAP"].median() == first_pass_median, "Double processing must be idempotent"
    print("[PASS] Idempotency via _units_normalized flag")

    # ================================================================
    # 5. Anomaly detection BEFORE clamping
    # ================================================================
    df_glitch = pd.DataFrame({
        "MAP": [100, 600, -50, 150, 200],
        "AFR": [14.7, 30, 5, 12.5, 13.0],
        "TPS": [50, 150, -10, 80, 95]
    })
    df_glitch = normalize_units(df_glitch)

    # Values should be clamped
    assert df_glitch["MAP"].max() == 400, "MAP not clamped at 400"
    assert df_glitch["MAP"].min() == 0,   "MAP not clamped at 0"
    assert df_glitch["AFR"].max() == 25,  "AFR not clamped at 25"
    assert df_glitch["AFR"].min() == 8,   "AFR not clamped at 8"
    assert df_glitch["TPS"].max() == 100, "TPS not clamped at 100"
    assert df_glitch["TPS"].min() == 0,   "TPS not clamped at 0"

    # But anomalies should be recorded
    anomalies = df_glitch.attrs.get("anomalies_detected", {})
    assert "MAP" in anomalies, "MAP anomalies should be logged"
    assert anomalies["MAP"]["count"] >= 1, "Should count MAP violations"
    assert "AFR" in anomalies, "AFR anomalies should be logged"
    assert "TPS" in anomalies, "TPS anomalies should be logged"
    print("[PASS] Anomaly detection before clamping - violations logged")

    # ================================================================
    # 6. Lambda -> AFR conversion (gasoline stoich 14.7)
    # ================================================================
    df_lam = pd.DataFrame({"AFR": [1.0, 0.85, 1.1, 0.95, 1.05]})
    df_lam = normalize_units(df_lam)
    assert np.isclose(df_lam["AFR"].iloc[0], 14.7, atol=0.01), \
        "Lambda 1.0 should -> 14.7"
    assert df_lam.attrs["original_units"]["AFR"]["unit"] == "Lambda"
    print("[PASS] Lambda -> AFR conversion (gasoline)")

    # ================================================================
    # 7. TPS: 0-1 fractional -> 0-100%
    # ================================================================
    df_tps_frac = pd.DataFrame({"TPS": [0.0, 0.25, 0.5, 0.75, 1.0]})
    df_tps_frac = normalize_units(df_tps_frac)
    assert df_tps_frac["TPS"].max() == 100, "TPS 0-1 scale should become 100"
    assert df_tps_frac["TPS"].min() == 0,   "TPS 0-1 scale min should stay 0"
    assert df_tps_frac.attrs["original_units"]["TPS"]["unit"] == "0-1_fraction"
    print("[PASS] TPS 0-1 fraction -> 0-100%")

    # ================================================================
    # 8. TPS: 0-5V voltage -> 0-100%
    # ================================================================
    df_tps_volt = pd.DataFrame({"TPS": [0.5, 1.2, 2.5, 3.8, 4.9]})
    df_tps_volt = normalize_units(df_tps_volt)
    assert np.isclose(df_tps_volt["TPS"].max(), 98.0, atol=0.01), \
        f"5V TPS max should be ~98, got {df_tps_volt['TPS'].max()}"
    assert df_tps_volt.attrs["original_units"]["TPS"]["unit"] == "voltage_0-5V"
    print("[PASS] TPS 0-5V -> 0-100%")

    # ================================================================
    # 9. Confidence scores are numeric 0.0-1.0
    # ================================================================
    df_conf = pd.DataFrame({
        "MAP": [101, 102, 103],
        "AFR": [14.5, 14.7, 14.8],
        "TPS": [50, 60, 70]
    })
    df_conf = normalize_units(df_conf)
    for signal in ["MAP", "AFR", "TPS"]:
        conf = df_conf.attrs["unit_confidence"][signal]
        assert isinstance(conf, float), \
            f"{signal} confidence should be float, got {type(conf)}"
        assert 0.0 <= conf <= 1.0, \
            f"{signal} confidence {conf} out of [0, 1]"
    print("[PASS] All confidence scores are numeric 0.0-1.0")

    # ================================================================
    # 10. Original unit stats preserved (no extra columns)
    # ================================================================
    df_orig = pd.DataFrame({"MAP": [1.0, 1.5, 2.0, 2.5, 3.0]})
    original_cols = set(df_orig.columns)
    df_orig = normalize_units(df_orig)
    new_cols = set(df_orig.columns) - original_cols
    assert not any("_original" in c for c in new_cols), \
        "Should not create _original_ columns"
    assert "stats" in df_orig.attrs["original_units"]["MAP"]
    assert "median" in df_orig.attrs["original_units"]["MAP"]["stats"]
    print("[PASS] Original stats in attrs, no extra columns")

    print("--- All Unit Normalization V2 Tests Passed! ---\n")


if __name__ == "__main__":
    test_unit_normalization()
