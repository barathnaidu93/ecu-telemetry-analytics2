import pandas as pd
import numpy as np
import logging
from typing import Optional, List, Tuple

logger = logging.getLogger(__name__)

# Production-grade Time Aliases (Multi-language Support)
TIME_ALIASES = [
    "time", "timestamp", "elapsed", "offset", "sec", "s",
    "zeit", "ms", "millisecond", "t", "stamps"
]

def robust_time_processing(df: pd.DataFrame, default_dt: float = 0.05) -> pd.DataFrame:
    """
    Hardened ECU telemetry time-series synchronization.
    - Detects time axis via fuzzy matching.
    - Validates and filters (NaN, negatives).
    - Sorts BEFORE dropping duplicates to ensure physical integrity.
    - Robust unit detection via absolute median delta.
    - Guaranteed zero-offset normalization.
    - High-fidelity sampling rate estimation.
    """
    print("[ENGINE] Initializing hardened time-series synchronization...")

    target_col = None
    df = df.copy()  # Avoid side-effects

    # 1. Fuzzy Column Detection (Exact match first)
    for alias in TIME_ALIASES:
        match = next((c for c in df.columns if alias == str(c).lower()), None)
        if match:
            target_col = match
            break

    # Fuzzy match (Substring)
    if not target_col:
        for alias in TIME_ALIASES:
            match = next((c for c in df.columns if alias in str(c).lower()), None)
            if match:
                target_col = match
                break

    # 2. Heuristic Transformation or Synthetic Generation
    if target_col:
        print(f"[INFO] Synchronizing to primary time axis: '{target_col}'", flush=True)

        # 1.5 Handle Clock-Based formats (HH:MM:SS.mmm)
        if pd.api.types.is_object_dtype(df[target_col]) or pd.api.types.is_string_dtype(df[target_col]):
            sample = df[target_col].dropna().head(5).astype(str)
            if sample.str.contains(':').any():
                print(f"[INFO] Detected clock-based time format in '{target_col}'. Normalizing to relative seconds.")
                parsed_ts = pd.to_datetime(df[target_col], errors='coerce')
                
                if not parsed_ts.isna().all():
                    t0 = parsed_ts[parsed_ts.notna()].iloc[0]
                    df[target_col] = (parsed_ts - t0).dt.total_seconds()

        # Coerce to numeric
        df[target_col] = pd.to_numeric(df[target_col], errors='coerce')

        # --- Validation & Cleaning ---
        # Filter out NaNs and negatives
        df = df[df[target_col].notna() & (df[target_col] >= 0)].copy()

        if df.empty:
            print("[WARN] All time data was invalid. Falling back to synthetic.")
            return _generate_synthetic(df, default_dt)

        # --- Unit Normalization (Robust Median Δt) ---
        # Use absolute median delta to ignore pauses/gaps.
        # Renamed to raw_median_dt to avoid shadowing the later metric variable.
        raw_median_dt = df[target_col].diff().abs().median()
        if 5 <= raw_median_dt < 1000:
            print(f"[WARN] Millisecond scale detected (median dt={raw_median_dt:.2f}). Normalizing.")
            df[target_col] = df[target_col] / 1000.0

        # Rename to standardized symbol
        df = df.rename(columns={target_col: "TIME"})
        time_key = "TIME"

        # --- Monotonicity & Sorting ---
        # Sort BEFORE dropping duplicates to preserve temporal truth
        df = df.sort_values(by=time_key)
        df = df.drop_duplicates(subset=time_key, keep="first")

        # --- Strict Zero-Offsetting ---
        # Normalize everything to start at exactly 0.0s
        if not df.empty:
            df[time_key] = df[time_key] - df[time_key].iloc[0]
    else:
        return _generate_synthetic(df, default_dt)

    # Final indexing cleanup
    df = df.reset_index(drop=True)

    # 3. Delta Time & Sampling Rate Estimation
    df["dt"] = df[time_key].diff().fillna(0).round(4)

    # Calculate metadata metrics (separate variable — does not shadow raw_median_dt)
    valid_dt = df["dt"][1:]
    median_dt = valid_dt.median() if not valid_dt.empty else default_dt
    sampling_rate = round(1.0 / median_dt, 1) if median_dt > 0 else 0

    print(f"[ENGINE] Time-sync complete. Duration: {df[time_key].max():.2f}s | Sample Rate: {sampling_rate}Hz")
    return df

def _generate_synthetic(df: pd.DataFrame, dt: float) -> pd.DataFrame:
    print(f"[WARN] Generating synthetic {1/dt:.1f}Hz clock axis.")
    df = df.copy()
    # Correctly bound generated array to df length
    df["TIME"] = np.arange(0, len(df) * dt, dt)[:len(df)]
    df["dt"] = dt
    df = df.reset_index(drop=True)
    return df

def normalize_time(df: pd.DataFrame) -> pd.DataFrame:
    """Entry point for modular ingestion pipeline."""
    return robust_time_processing(df)
