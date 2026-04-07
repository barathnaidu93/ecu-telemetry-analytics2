"""
Quick regression test for the coerce_numeric() fix.
Run with:  backend\venv\Scripts\python.exe backend\test_coerce_fix.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd
from utils.type_utils import coerce_numeric

def run():
    # --- Case 1: Mixed numeric + categorical columns ---
    df = pd.DataFrame({
        "RPM":      [800, 1500, 3000, 4500, 6000],
        "AFR":      [14.7, 14.5, 13.2, 12.8, 13.0],
        "MAP":      [35.0, 75.0, 150.0, 200.0, 250.0],
        "Scenario": ["Idle / Decel", "City Driving", "Hard Acceleration", "WOT Pull", "WOT Pull"],
        "tag":      ["run1", "run1", "run2", "run2", "run3"],
        "Filename": ["log_a.csv"] * 5,
    })

    result = coerce_numeric(df)

    print("=== Column dtypes after coerce_numeric ===")
    for col in result.columns:
        print(f"  {col:12s}  dtype={str(result[col].dtype):<10}  sample={result[col].iloc[0]}")

    # Numeric columns must be a numeric dtype (int64/float64/float32 — all valid)
    for num_col in ["RPM", "AFR", "MAP"]:
        assert pd.api.types.is_numeric_dtype(result[num_col]), \
            f"FAIL: {num_col} dtype={result[num_col].dtype} — expected numeric"

    # String/categorical columns must be string-like (object or pandas StringDtype)
    # NOT all-NaN float64 — which was the bug.
    for str_col in ["Scenario", "tag", "Filename"]:
        assert pd.api.types.is_string_dtype(result[str_col]), \
            f"FAIL: {str_col} dtype={result[str_col].dtype} — should be string/object, not float64"
        assert result[str_col].notna().all(), \
            f"FAIL: {str_col} has unexpected NaN values — got {result[str_col].tolist()}"

    print()

    # --- Case 2: Entirely numeric CSV (no regression) ---
    df2 = pd.DataFrame({
        "TIME": [0.0, 0.1, 0.2],
        "RPM":  [900, 1200, 3000],
        "TPS":  [5.0, 20.0, 80.0],
    })
    result2 = coerce_numeric(df2)
    for col in ["TIME", "RPM", "TPS"]:
        assert pd.api.types.is_numeric_dtype(result2[col]), \
            f"FAIL: {col} dtype={result2[col].dtype} — should be numeric"

    print("=== All assertions passed. coerce_numeric() fix is CORRECT. ===")


if __name__ == "__main__":
    run()
