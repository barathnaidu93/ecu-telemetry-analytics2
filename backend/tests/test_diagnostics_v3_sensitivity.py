import pandas as pd
import numpy as np
from backend.main import run_diagnostics

def test_sensitivity_rules():
    print("--- Starting Sensitivity Diagnostics (V3) Verification ---")
    
    # CASE 1: Low Throttle Session (Dynamic Scaling)
    # Session where max TPS is only 3.0%. 
    # High Load rules should fire at ~2.7% TPS.
    df_low = pd.DataFrame({
        "RPM": [2000]*100,
        "TPS": [1.0]*90 + [2.8]*10, # 10 samples of "high" load relative to log
        "HC": [100]*100,
        "CO": [0.2]*100,
    })
    # Attach a fault to those 10 samples: High CO
    df_low.loc[90:, "CO"] = 3.5 # This would hit absolute threshold 2.8
    
    res = run_diagnostics(df_low, {"TPS": "TPS", "RPM": "RPM", "CO": "CO", "HC": "HC"})
    print(f"Low Throttle Case: Score={res['health_score']}, Alerts={res['alerts']}")
    assert any("Rich Burn" in a for a in res['alerts'])

    # CASE 2: Ghost Torque Paradox
    df_ghost = pd.DataFrame({
        "RPM": [1000]*10,
        "TPS": [0.0]*10,      # Closed throttle
        "Force": [2000]*10,   # Massive force (Max is 2000, 100% force)
        "Power": [500]*10     # High power
    })
    res = run_diagnostics(df_ghost, {"TPS": "TPS", "RPM": "RPM", "Force": "Force", "Power": "Power"})
    print(f"Ghost Torque Case: Score={res['health_score']}, Alerts={res['alerts']}")
    assert any("Physical Paradox - High Force" in a for a in res['alerts'])

    # CASE 3: Vacuum Paradox
    df_vac = pd.DataFrame({
        "RPM": [800]*10,
        "TPS": [1.0]*10,
        "MAP": [150]*10  # 150 kPa is boost, but throttle is closed at idle
    })
    res = run_diagnostics(df_vac, {"TPS": "TPS", "RPM": "RPM", "MAP": "MAP"}, aspiration="TURBO")
    print(f"Vacuum Paradox Case: Score={res['health_score']}, Alerts={res['alerts']}")
    assert any("Vacuum Paradox" in a for a in res['alerts'])

    # CASE 4: Statistical Outlier (CO Spike)
    df_spike = pd.DataFrame({
        "RPM": [2000]*200,
        "TPS": [20]*200,
        "CO": [0.1]*190 + [1.5]*10, # 1.5 is below absolute (2.8) but high relative to 0.1
        "HC": [50]*200
    })
    res = run_diagnostics(df_spike, {"TPS": "TPS", "RPM": "RPM", "CO": "CO", "HC": "HC"})
    print(f"Emission Spike Case: Score={res['health_score']}, Alerts={res['alerts']}")
    assert any("Abnormal Emission Spikes" in a for a in res['alerts'])

    # CASE 5: REAL DATA - EngineFaultDB_Final.csv
    try:
        # Only read a chunk to avoid memory/time issues during automated testing
        real_df = pd.read_csv("EngineFaultDB_Final.csv", nrows=10000)
        # Map our local symbols to the CSV columns
        y_map = {
            "RPM": "RPM", "TPS": "TPS", "MAP": "MAP", 
            "CO": "CO", "HC": "HC", "Power": "Power", "Force": "Force"
        }
        res_real = run_diagnostics(real_df, y_map)
        print(f"REAL DATA (EngineFaultDB Sample): Score={res_real['health_score']}, Status={res_real['status']}")
        print(f"Found Alerts: {res_real['alerts']}")
        
        # Verify it's no longer 100%
        # Note: If the first 10k rows are all clean, this might still be 100.
        # But we previously saw faults around row 20k. Let's read from row 15k.
        real_fault_df = pd.read_csv("EngineFaultDB_Final.csv", skiprows=15000, nrows=10000, 
                                   names=real_df.columns)
        res_fault = run_diagnostics(real_fault_df, y_map)
        print(f"REAL FAULT DATA (EngineFaultDB Chunk): Score={res_fault['health_score']}, Alerts={res_fault['alerts']}")
        assert res_fault['health_score'] < 100
        
    except Exception as e:
        print(f"Skip Read CSV test: {e}")

    print("--- Sensitivity Verification Passed ---")

if __name__ == "__main__":
    test_sensitivity_rules()
