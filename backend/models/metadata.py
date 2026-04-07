from typing import List, Dict, Optional, Any
import pandas as pd

def build_metadata(df: pd.DataFrame, units: Dict[str, str], warnings: List[str]) -> Dict[str, Any]:
    """
    Constructs a standardized metadata dictionary for the processed log.
    Includes sampling rate diagnostics and unit mapping.
    NOTE: After normalize_time(), the time column is renamed to "TIME" (uppercase).
    Uses case-insensitive matching to handle both raw and mapped column names.
    """
    print("[INFO] Building unified metadata schema...")

    # 1. Sampling Rate Diagnostics
    sampling = {}
    time_col = None

    # Case-insensitive search — after normalize_time(), column is "TIME" not "time"
    for col in df.columns:
        if "time" in col.lower() and "stamp" not in col.lower():
            # Prefer exact "TIME" over derived columns like "dt"
            # "dt" does not contain "time" so it won't match, but be explicit
            if col.upper() == "TIME":
                time_col = col
                break
            if time_col is None:
                time_col = col  # first fuzzy match as fallback

    if time_col:
        time_data = df[time_col]
        
        # If the file has duplicate columns with the same name,
        # pandas returns a DataFrame instead of a Series.
        if isinstance(time_data, pd.DataFrame):
            time_data = time_data.iloc[:, 0]
            
        if not time_data.isnull().all():
            dt = time_data.diff().dropna()
            if not dt.empty and dt.mean() > 0:
                sampling = {
                    "mean_dt":    round(float(dt.mean()), 4),
                    "std_dt":     round(float(dt.std()), 4),
                    "is_irregular": bool(dt.std() > (dt.mean() * 0.15)),
                    "mean_freq_hz": round(1.0 / dt.mean(), 2)
                }

    # 2. Final Schema
    return {
        "units":         units,
        "sampling_rate": sampling,
        "warnings":      warnings,
        "rows_parsed":   len(df)
    }
