"""
Integration test: dirty/metadata-rich CSV ingestion through the full pipeline.
Verifies density-based header discovery, alias mapping, and sensor normalization.
"""
import sys
import os
import io

# Resolve backend/ as the root so all module imports work
# regardless of whether this file is run from backend/ or backend/tests/
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import pandas as pd
from utils.io_utils import read_csv_auto
from core.ingestion import process_ecu_file


def test_robust_ingestion():
    # Simulate a "Dirty" CSV from an ECU tool like MHD or COBB
    dirty_csv = """MHD Logging v1.0
Hardware: S58_G80
Date: 2026-03-31
Units: Metric
------------------------------------
"Time [s]","Engine RPM [1/min]","Accelerator Pedal [%]","Boost [psi]","Wideband O2 [AFR]"
0.00,800.0,0.0,0.5,14.7
0.10,1200.0,15.0,1.2,14.5
0.20,2500.0,100.0,18.5,11.8
"""

    print("\n[TEST] Testing Density-Based Header Discovery (two-pass)...")
    try:
        # Step 1: Raw Read
        df = read_csv_auto(dirty_csv.encode(), "dirty_log.csv")
        print(f"  [OK] read_csv_auto found {len(df.columns)} columns")
        print(f"       Columns found: {list(df.columns)}")

        # Step 2: Full Pipeline (Renaming/Mapping)
        clean_df, metadata = process_ecu_file(dirty_csv.encode(), filename="dirty_log.csv")
        print(f"  [OK] process_ecu_file mapped {len(clean_df.columns)} sensors")
        print(f"       Mapped Sensors: {list(clean_df.columns)}")

        # Verification
        expected = ["RPM", "TPS", "MAP", "AFR"]
        missing = [s for s in expected if s not in clean_df.columns]

        if not missing:
            print("\n[SUCCESS] Robust ingestion successfully bypassed metadata and mapped sensors!")
        else:
            print(f"\n[FAILURE] Missing mapped sensors: {missing}")
            sys.exit(1)

    except Exception as e:
        print(f"\n[ERROR] Ingestion failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    test_robust_ingestion()
