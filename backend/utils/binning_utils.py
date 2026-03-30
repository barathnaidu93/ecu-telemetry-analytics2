import numpy as np
import pandas as pd
from typing import List

def snap_to_bins(series: pd.Series, bins: List[float], mode: str = 'nearest') -> pd.Series:
    """
    Vectorized O(N log K) bin snapping.
    Modes: nearest, floor, ceil. Preserves NaNs.
    """
    print(f"[INFO] Snapping to bins (mode: {mode})...")
    
    if series.empty: return series
    bins = sorted(np.asarray(bins))
    vals = series.values
    
    mask = ~np.isnan(vals)
    valid_vals = vals[mask]
    
    if len(valid_vals) == 0: return series

    if mode == 'floor':
        idx = np.searchsorted(bins, valid_vals, side='right') - 1
        idx = np.clip(idx, 0, len(bins) - 1)
        snapped = np.array(bins)[idx]
    elif mode == 'ceil':
        idx = np.searchsorted(bins, valid_vals, side='left')
        idx = np.clip(idx, 0, len(bins) - 1)
        snapped = np.array(bins)[idx]
    else: # nearest
        idx = np.searchsorted(bins, valid_vals, side='left')
        idx = np.clip(idx, 0, len(bins) - 1)
        prev_idx = np.clip(idx - 1, 0, len(bins) - 1)
        d1 = np.abs(valid_vals - np.array(bins)[idx])
        d2 = np.abs(valid_vals - np.array(bins)[prev_idx])
        snapped = np.where(d1 <= d2, np.array(bins)[idx], np.array(bins)[prev_idx])

    result = np.full_like(vals, np.nan)
    result[mask] = snapped
    return pd.Series(result, index=series.index)
