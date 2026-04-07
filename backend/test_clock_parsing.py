import pandas as pd
import numpy as np
import sys
import os

# Add parent dir to path to import backend
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.utils.time_utils import robust_time_processing
from backend.core.mapping import map_columns

def test_clock_parsing():
    # Mock VCDS-style data
    data = {
        "Time Stamp": ["12:05:01.100", "12:05:01.200", "12:05:01.300", "Invalid", "12:05:01.400"],
        "Accelerator Pedal Position D [%]": [0.0, 10.5, 25.0, np.nan, 30.0],
        "Engine RPM": [800, 1200, 1500, 0, 1800]
    }
    print("Data defined")
    df_raw = pd.DataFrame(data)
    print("DataFrame created")
    
    # 1. Test Time Sync
    print("Starting robust_time_processing")
    df_time = robust_time_processing(df_raw.copy())
    print("robust_time_processing finished")
    
    print("Processed Time Axis:")
    print(df_time[["TIME", "dt"]])
    
    # Assertions for Time
    assert df_time["TIME"].iloc[0] == 0.0, "Time should start at 0.0"
    assert df_time["TIME"].iloc[1] == 0.1, f"Expected 0.1, got {df_time['TIME'].iloc[1]}"
    assert (df_time["TIME"].diff().dropna() > 0).all(), "Time should be strictly increasing"
    assert len(df_time) == 4, "Should have 4 rows after filtering 'Invalid' row"
    
    # 2. Test Mapping
    print("\nProcessing Column Mapping...")
    df_mapped = map_columns(df_time)
    
    print("Mapped Columns:", df_mapped.columns.tolist())
    
    # Assertions for Mapping
    assert "TPS" in df_mapped.columns, "Should have mapped 'Pedal Position' to 'TPS'"
    assert "RPM" in df_mapped.columns, "Should have mapped 'Engine RPM' to 'RPM'"
    
    print("\n[SUCCESS] Clock-based time parsing and TPS mapping verified!")

if __name__ == "__main__":
    try:
        test_clock_parsing()
    except Exception as e:
        print(f"\n[FAILURE] Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
