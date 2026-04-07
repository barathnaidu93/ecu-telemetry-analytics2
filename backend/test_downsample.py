"""
Unit test for M4 Decimation algorithm vs Naive Downsampling.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd
import numpy as np
from utils.downsample_utils import m4_decimate_multivariate

def run():
    print("Testing M4 Decimation Algorithm...\n")
    
    # Create an artificial flat dataset of 2000 points
    times = np.linspace(0, 100, 2000)
    rpm = np.full(2000, 3000.0)
    afr = np.full(2000, 14.7)
    
    # Inject a massive Knock Retard / Lean-out spike at exactly row 105
    rpm[105] = 8000.0  # mechanical overrev
    afr[105] = 20.0    # severe lean spike

    df = pd.DataFrame({
        "TIME": times,
        "RPM": rpm,
        "AFR": afr
    })
    
    # 1. Test Naive Downsampling behavior (df.iloc[::step])
    step = max(1, len(df) // 500)
    df_naive = df.iloc[::step].copy()
    
    # Assert that row 105 was skipped and the spike is hidden
    naive_max_rpm = df_naive["RPM"].max()
    print(f"Naive Downsample Max RPM: {naive_max_rpm} (Expected: ~3000, Spy hidden)")
    assert naive_max_rpm == 3000.0, "Naive decimation unexpectedly caught the spike!"
    
    # 2. Test M4 Decimation behavior
    df_m4 = m4_decimate_multivariate(df, "TIME", max_points=500)
    
    # Assert that despite being reduced to ~500 points, the max peak is perfectly retained
    m4_max_rpm = df_m4["RPM"].max()
    m4_max_afr = df_m4["AFR"].max()
    print(f"M4 Decimation Max RPM   : {m4_max_rpm} (Expected: 8000, Spike preserved perfectly)")
    assert m4_max_rpm == 8000.0, f"M4 algorithm missed the RPM spike! Got {m4_max_rpm}"
    assert m4_max_afr == 20.0,   f"M4 algorithm missed the AFR spike! Got {m4_max_afr}"
    
    print(f"\nRow reduction: {len(df)} -> {len(df_m4)} rows.")
    print("=== All M4 Decimation assertions passed perfectly ===")

if __name__ == "__main__":
    run()
