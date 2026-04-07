import pandas as pd
import sys
import os

# Add backend to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.mapping import map_columns

def test_mapping_robustness():
    print("\n--- Testing Mapping Robustness ---")
    
    # Mock DataFrame with complex, real-world headers from various loggers
    data = {
        "Time": [0.1, 0.2, 0.3],
        "Engine RPM [RPM]": [800, 900, 1000],
        "Intake Manifold Absolute Pressure [kPa]": [100, 101, 102],
        "Coolant Temp (C)": [80, 81, 82],
        "Accelerator Pedal Position E [%]": [10, 20, 30],
        "Ignition Advance (deg)": [10, 12, 14],
        "Mass Air Flow (g/s)": [5, 6, 7]
    }
    df = pd.DataFrame(data)
    
    print("Original Columns:", df.columns.tolist())
    
    mapped_df = map_columns(df)
    
    mapped_cols = mapped_df.columns.tolist()
    print("Mapped Columns:", mapped_cols)
    
    # Expected mappings based on ALIAS_MAP in mapping.py
    expected = {
        "RPM": "Engine RPM [RPM]",
        "MAP": "Intake Manifold Absolute Pressure [kPa]",
        "CLT": "Coolant Temp (C)",
        "TPS": "Accelerator Pedal Position E [%]",
        "IGN": "Ignition Advance (deg)",
        "MAF": "Mass Air Flow (g/s)"
    }
    
    for standard, original in expected.items():
        assert standard in mapped_cols, f"Failed to map '{original}' to '{standard}'"
        print(f" [PASS] '{original}' -> '{standard}'")

    print("\n--- Mapping Robustness Verified! ---")

if __name__ == "__main__":
    try:
        test_mapping_robustness()
    except Exception as e:
        print(f"\n[FAIL] Test failed: {e}")
        sys.exit(1)
