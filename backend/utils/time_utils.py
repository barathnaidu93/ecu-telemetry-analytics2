import pandas as pd
from typing import Optional, List

# Standard Time Aliases
TIME_ALIASES = ["time", "timestamp", "offset", "sec", "s"]

def normalize_time(df: pd.DataFrame) -> pd.DataFrame:
    """
    Identifies the time column and zero-offsets it.
    Also computes and adds sampling metadata hooks.
    """
    print("[INFO] Normalizing time series...")
    
    time_col = None
    for aliases in TIME_ALIASES:
        candidates = [c for c in df.columns if aliases in c]
        if candidates:
            time_col = candidates[0]
            break
            
    if time_col and not df[time_col].isnull().all():
        df = df.sort_values(by=time_col)
        df[time_col] = df[time_col] - df[time_col].min()
    
    return df
