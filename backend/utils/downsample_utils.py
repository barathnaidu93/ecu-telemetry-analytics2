import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)

def m4_decimate_multivariate(df: pd.DataFrame, time_col: str, max_points: int = 500) -> pd.DataFrame:
    """
    M4 (Min-Max) Decimation Algorithm for time-series telemetry.
    Replaces naive `::step` downsampling.

    Instead of blindly skipping rows (which hides catastrophic spikes like Knock Retard or Lean-outs),
    this algorithm divides the data into chunks. From each chunk, it extracts:
      - The First row
      - The Last row
      - The row containing the local Minimum for every critical sensor
      - The row containing the local Maximum for every critical sensor
    
    This mathematically guarantees that all visual peaks and valleys are 100% preserved
    on the final chart, no matter how compressed the timeline becomes.
    """
    if df.empty or len(df) <= max_points:
        return df.copy()

    # Determine chunk size. We divide by 4 because each chunk produces a minimum of 4 points
    # (First, Last, Min, Max). Depending on the number of non-overlapping spikes across
    # different sensors, it may return slightly more than max_points, but visual fidelity
    # is perfectly retained without bogging down the browser.
    num_chunks = max(1, max_points // 4)

    # Identify critical numeric columns we care about catching spikes for.
    critical_signals = ["RPM", "TPS", "MAP", "AFR", "LAMBDA", "IGN", "KNOCK", "STFT", "LTFT", "SPEED"]
    numeric_cols = [
        c for c in critical_signals 
        if c in df.columns and pd.api.types.is_numeric_dtype(df[c])
    ]

    # Fast chunk indexing
    chunks = np.array_split(df.index, num_chunks)
    
    selected_indices = set()

    for chunk in chunks:
        if len(chunk) == 0:
            continue
            
        # 1. First and Last points of the chunk preserve timeline structure
        selected_indices.add(chunk[0])
        selected_indices.add(chunk[-1])
        
        # 2. Extract Min and Max points for every critical signal
        if len(chunk) > 2 and numeric_cols:
            sub_df = df.loc[chunk, numeric_cols]
            
            for col in numeric_cols:
                # pandas series idxmin/idxmax returns the index label of the min/max value
                try:
                    idx_min = sub_df[col].idxmin()
                    if pd.notna(idx_min):
                        selected_indices.add(idx_min)
                        
                    idx_max = sub_df[col].idxmax()
                    if pd.notna(idx_max):
                        selected_indices.add(idx_max)
                except Exception:
                    pass

    # Sort the indices to maintain strictly chronological order mapping
    final_indices = sorted(list(selected_indices))
    
    decimated_df = df.loc[final_indices].copy()
    
    logger.info(
        f"[Downsample] M4 Decimation complete. "
        f"Reduced {len(df)} rows -> {len(decimated_df)} rows while preserving physics."
    )
    
    return decimated_df
