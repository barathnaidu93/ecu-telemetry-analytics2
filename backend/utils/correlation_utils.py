import pandas as pd
import numpy as np
from typing import List, Dict, Any

def get_temporal_snapshot(df: pd.DataFrame, timestamp: float, sensors: List[str], window: int = 0) -> Dict[str, Any]:
    """
    Finds the row closest to 'timestamp' and extracts values for 'sensors'.
    If window > 0, it can average over a small range (optional).
    """
    if df.empty or not sensors:
        return {}

    # Standardize time column
    time_col = "TIME" if "TIME" in df.columns else df.columns[0]
    
    # 1. Find nearest row
    # Use absolute diff to find the exact or closest point
    abs_diff = (df[time_col] - timestamp).abs()
    idx = abs_diff.idxmin()
    row = df.loc[idx]

    # 2. Extract sensor values
    snapshot = {"time": round(float(row[time_col]), 3)}
    for s in sensors:
        if s in df.columns:
            val = row[s]
            snapshot[s] = round(float(val), 2) if pd.notna(val) and isinstance(val, (int, float, np.number)) else val
        else:
            snapshot[s] = "N/A"
            
    return snapshot

def identify_critical_events(df: pd.DataFrame, sensor: str, threshold: float, top_n: int = 3) -> List[float]:
    """
    Identifies timestamps where 'sensor' exceeds 'threshold', 
    prioritizing the peaks of the events.
    Returns: List of timestamps sorted by severity.
    """
    if df.empty or sensor not in df.columns:
        return []

    # Filter for values above threshold
    critical = df[df[sensor] > threshold].copy()
    if critical.empty:
        return []

    # Sort by value descending and take top N
    # To avoid taking 3 points from the same 0.1s event, we sort by time and deduplicate spikes
    # Simple logic: sort by value, then only take if it's not within 0.5s of an already taken point
    sorted_df = critical.sort_values(by=sensor, ascending=False)
    
    event_times = []
    for _, row in sorted_df.iterrows():
        t = row["TIME"] if "TIME" in df.columns else row.iloc[0]
        # Check if we already have an event within 0.5 seconds
        if not any(abs(t - taken_t) < 0.5 for taken_t in event_times):
            event_times.append(t)
        
        if len(event_times) >= top_n:
            break
            
    return event_times
