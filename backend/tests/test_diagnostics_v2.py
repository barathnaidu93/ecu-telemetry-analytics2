import pandas as pd
import numpy as np
import sys
import os
import traceback

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), "backend"))

from main import run_diagnostics

def test_diagnostics_suite():
    print("--- Starting Diagnostics V2 Verification ---")
    
    # 1. Base Case: Perfect Health
    df_perfect = pd.DataFrame({
        "RPM": [800.0, 2000.0, 5000.0],
        "TPS": [0.0, 20.0, 100.0],
        "MAP": [30.0, 60.0, 101.3],
        "AFR": [14.7, 14.3, 12.5],
        "KNOCK": [0.0, 0.0, 0.0],
        "IDC": [2.0, 10.0, 60.0],
        "DELTA_LAMBDA": [0.0, 0.0, 0.0]
    })
    res = run_diagnostics(df_perfect, {}, metadata={}, aspiration="NA")
    print(f"Perfect Case: Score={res['health_score']}, Status={res['status']}, Alerts={res['alerts']}")
    assert res['health_score'] == 100
    
    # 2. Case: High Knock under Load
    df_knock = df_perfect.copy()
    df_knock.loc[2, "KNOCK"] = 4.5 # 4.5 degrees retard
    df_knock.loc[2, "TPS"] = 95
    res = run_diagnostics(df_knock, {}, metadata={}, aspiration="NA")
    print(f"Knock Case: Alerts={res['alerts']}, Score={res['health_score']}")
    assert len(res['alerts']) > 0
    assert any("Knock Retard" in a for a in res['alerts'])
    assert res['health_score'] < 100
    
    # 3. Case: Injector Saturation
    df_idc = df_perfect.copy()
    df_idc.loc[2, "IDC"] = 105
    res = run_diagnostics(df_idc, {}, metadata={}, aspiration="NA")
    print(f"IDC Case: Alerts={res['alerts']}, Score={res['health_score']}")
    assert len(res['alerts']) > 0
    assert any("Injector" in a for a in res['alerts'])
    
    # 4. Case: Data Integrity (Anomalies)
    meta_anomaly = {
        "unit_normalization": {
            "anomalies": {
                "AFR": {"percentage": 15, "count": 10}
            }
        }
    }
    res = run_diagnostics(df_perfect, {}, metadata=meta_anomaly, aspiration="NA")
    print(f"Anomaly Case: Score={res['health_score']}, Status={res['status']}, Alerts={res['alerts']}")
    assert "Data Integrity" in res['alerts'][0]
    assert res['health_score'] < 100

    # 5. Case: Boost Leak (Turbo only)
    df_leak = pd.DataFrame({
        "RPM": [3000]*10,
        "TPS": [100]*10,
        "MAP": [150]*10,      # Actual
        "BOOST_SPEC": [200]*10 # Target (50kPa diff)
    })
    # Test NA (should not alert)
    res_na = run_diagnostics(df_leak, {}, metadata={}, aspiration="NA")
    assert len(res_na['alerts']) == 0
    # Test Turbo (should alert)
    res_turbo = run_diagnostics(df_leak, {}, metadata={}, aspiration="TURBO")
    print(f"Boost Leak Case: Score={res_turbo['health_score']}, Status={res_turbo['status']}, Alerts={res_turbo['alerts']}")
    assert "Boost Leak" in res_turbo['alerts'][0]

    print("--- Diagnostics Verification Passed ---")

if __name__ == "__main__":
    try:
        test_diagnostics_suite()
    except Exception as e:
        print(f"Verification Failed: {e}")
        traceback.print_exc()
        sys.exit(1)
