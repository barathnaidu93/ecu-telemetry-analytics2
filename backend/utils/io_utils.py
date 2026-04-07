import pandas as pd
import csv
import io
import logging
from typing import Union

logger = logging.getLogger(__name__)

def read_csv_auto(file_content: Union[str, bytes], filename: str = "telemetry.csv") -> pd.DataFrame:
    """
    Robust CSV reader optimized for speed.
    Uses deterministic encoding and C-engine by default.

    Header detection algorithm (two-pass):
      Pass 1 — Determine the best separator by finding the one with the highest
               consistent field count across candidate lines. This is stable
               because we track the per-separator maximum, not a running update.
      Pass 2 — Find the FIRST non-comment line that achieves the maximum field
               count for that separator. This ensures we land on the actual header
               row (column names) rather than a dense data row further down.
    """
    print(f"[INFO] Initializing ingestion for: {filename}")

    # 1. Standardize Input to Bytes
    if isinstance(file_content, str):
        raw_data = file_content.encode('utf-8')
    else:
        raw_data = file_content

    if not raw_data:
        raise ValueError(f"File '{filename}' is empty.")

    # 2. Fast Deterministic Encoding
    decoded_text = None
    for enc in ['utf-8', 'cp1252']:
        try:
            decoded_text = raw_data.decode(enc)
            print(f"[INFO] Decoded using {enc}")
            break
        except UnicodeDecodeError:
            continue

    if not decoded_text:
        # Final fallback with replacement
        decoded_text = raw_data.decode('utf-8', errors='replace')
        print("[WARN] Using utf-8 fallback with replacements.")

    # 3. Robust Header Discovery (Two-Pass Algorithm)
    lines = decoded_text.splitlines()
    seps = [',', ';', '\t']

    # --- Pass 1: Determine best separator ---
    # For each separator, track the maximum field count seen across first 100 lines.
    sep_max_fields = {s: 0 for s in seps}
    candidate_lines = []  # (line_index, stripped_line) for non-empty, non-comment lines

    print(f"[INFO] Scanning first 100 lines for header density (two-pass)...")
    for i, line in enumerate(lines[:100]):
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        candidate_lines.append((i, stripped))
        for s in seps:
            count = stripped.count(s)
            if count > sep_max_fields[s]:
                sep_max_fields[s] = count

    # Select the separator with the highest max field count
    best_sep = max(sep_max_fields, key=sep_max_fields.get)
    if sep_max_fields[best_sep] == 0:
        best_sep = ','  # fallback for single-column files

    # --- Pass 2: Find the FIRST line that hits the max field count ---
    # This anchors us to the header row, not a later dense data row.
    max_fields = sep_max_fields[best_sep]
    header_idx = candidate_lines[0][0] if candidate_lines else 0  # safe default

    for line_idx, stripped in candidate_lines:
        if stripped.count(best_sep) >= max_fields:
            header_idx = line_idx
            break  # Stop at FIRST match — this is the header

    print(f"[INFO] Detected header at line {header_idx + 1} using separator '{best_sep}'")

    # 4. Extract data starting from detected header
    data_lines = lines[header_idx:]

    # 5. Read to DataFrame (C engine optimized)
    df = pd.read_csv(
        io.StringIO("\n".join(data_lines)),
        sep=best_sep,
        skipinitialspace=True,
        on_bad_lines='skip',
        engine='c' if best_sep != '\t' else 'python'
    )

    if df.empty:
        raise ValueError("Critical Error: DataFrame is empty after parsing.")

    return df
