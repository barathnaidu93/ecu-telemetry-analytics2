import pandas as pd
import io
import sys
import os

# Resolve paths relative to this file, not the CWD.
# This ensures the script works whether run from backend/ or the project root.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from main import parse_csv

sample_csv = """# ECU Log
"Time [s]","Engine RPM [1/min]","Throttle Position [%]","Manifold Pressure [mbar]","Vehicle Speed [km/h]","Wideband O2 [AFR]"
0.00,800.0,10.0,350.0,0.0,14.7
0.10,1200.0,15.0,400.0,5.0,14.5
0.20,2500.0,45.0,850.0,25.0,12.5
"""

try:
    result = parse_csv(sample_csv.encode(), "test.csv")
    print("\n[VERIFICATION RESULTS]")
    print(f"SUCCESS: CSV parsed. Rows: {result.get('rows')}")
    
    # Check Master Plot keys
    master = result.get("chart_master", [])
    if master:
        point = master[0]
        print(f"Sample point keys: {list(point.keys())}")
        if "RPM" in point and "Throttle" in point and "Speed" in point:
            print("[OK] VERIFIED: chart_master contains RPM, Throttle, and Speed")
        else:
            print(f"[FAIL] FAILED: missing keys in chart_master.")
            
    # Check Heatmap
    heatmap = result.get("afr_heatmap", {})
    if "cells" in heatmap:
        print(f"[OK] VERIFIED: Heatmap cells present ({len(heatmap['cells'])} cells)")
    else:
        print(f"[FAIL] FAILED: Heatmap error: {heatmap.get('error', 'Unknown')}")

    # Check Diagnostics
    diag = result.get("diagnostics", {})
    if diag.get("status") != "Undetermined":
        print(f"[OK] VERIFIED: Diagnostics status is '{diag.get('status')}'")
    else:
        print(f"[FAIL] FAILED: Diagnostics undetermined: {diag.get('alerts')}")

except Exception as e:
    import traceback
    traceback.print_exc()
    print(f"ERROR: {e}")
