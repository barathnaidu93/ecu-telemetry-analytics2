import pandas as pd
import numpy as np
import sys
import os

# Add parent dir to path to import backend
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.main import run_diagnostics, build_file_context

def test_correlation():
    print("\n[TEST] Running Cross-Sensor Temporal Correlation Test...")
    
    # Mock data with a Knock event and a Lean event
    # t=1.0: Normal
    # t=2.0: Knock peak (2.5) with Lean AFR (13.8)
    # t=3.0: Lean peak (15.0) without knock
    data = {
        "TIME":  [1.0, 2.0, 2.1, 3.0, 4.0],
        "RPM":   [2000, 3000, 3100, 4000, 5000],
        "TPS":   [20.0, 100.0, 100.0, 80.0, 50.0],
        "MAP":   [100, 150, 150, 120, 110],
        "AFR":   [14.7, 13.8, 13.9, 15.0, 14.7],
        "IGN":   [15.0, 12.0, 12.0, 18.0, 20.0],
        "KNOCK": [0.0, 2.5, 2.3, 0.0, 0.0],
        "DELTA_LAMBDA": [0.0, 5.0, 5.2, 12.0, 0.0]  # Positive = Lean
    }
    df = pd.DataFrame(data)
    y_map = {col: col for col in df.columns}
    
    print("Running diagnostics...")
    diag = run_diagnostics(df, y_map, aspiration="TURBO")
    
    snaps = diag.get("correlation_snapshots", [])
    print(f"Captured {len(snaps)} snapshots.")
    
    for s in snaps:
        print(f"Event: {s['_event_type']} at {s['time']}s -> RPM={s.get('RPM')}, AFR={s.get('AFR')}, KNOCK={s.get('KNOCK')}")

    # Assertions
    assert any(s["_event_type"] == "Knock Retard" for s in snaps), "Should have captured Knock snapshot"
    assert any(s["_event_type"] == "Fueling Error (Lean)" for s in snaps), "Should have captured Lean snapshot"
    
    # Check if the AI context builder works
    print("\nBuilding AI context...")
    store = {
        "type": "csv",
        "data": {
            "filename": "test.csv",
            "rows": 5,
            "all_columns": list(df.columns),
            "diagnostics": diag,
            "scenario_summary": {},
            "column_stats": {}
        }
    }
    context = build_file_context(store)
    print("AI Context Preview:")
    print(context)
    
    assert "=== CRITICAL TEMPORAL CORRELATIONS (SNAPSHOTS) ===" in context
    assert "2.0s" in context
    assert "3.0s" in context
    
    print("\n[SUCCESS] Temporal Correlation logic verified!")

if __name__ == "__main__":
    try:
        test_correlation()
    except Exception as e:
        print(f"\n[FAILURE] Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
