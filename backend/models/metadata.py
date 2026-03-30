from typing import List, Dict, Optional, Any
import pandas as pd

def build_metadata(df: pd.DataFrame, units: Dict[str, str], warnings: List[str]) -> Dict[str, Any]:
    """
    Constructs a standardized metadata dictionary for the processed log.
    Includes sampling rate diagnostics and unit mapping.
    """
    print("[INFO] Building unified metadata schema...")
    
    # 1. Sampling Rate Diagnostics
    sampling = {}
    time_col = None
    # Look for Time column (usually normalized by now)
    for col in df.columns:
        if "time" in col or "timestamp" in col:
            time_col = col
            break
            
    if time_col and not df[time_col].isnull().all():
        dt = df[time_col].diff().dropna()
        if not dt.empty and dt.mean() > 0:
            sampling = {
                "mean_dt": round(float(dt.mean()), 4),
                "std_dt": round(float(dt.std()), 4),
                "is_irregular": bool(dt.std() > (dt.mean() * 0.15)),
                "mean_freq_hz": round(1.0 / dt.mean(), 2)
            }

    # 2. Final Schema
    return {
        "units": units,
        "sampling_rate": sampling,
        "warnings": warnings,
        "rows_parsed": len(df)
    }
