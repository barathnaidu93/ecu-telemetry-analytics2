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

    # 3. Delimiter Detection
    lines = decoded_text.splitlines()
    clean_lines = [l.strip() for l in lines if l.strip() and not l.startswith('#')]
    
    if not clean_lines:
        raise ValueError("Critical Error: No valid data found in CSV.")

    sample = "\n".join(clean_lines[:20])
    delimiter = ','
    try:
        delimiter = csv.Sniffer().sniff(sample, delimiters=[',', ';', '\t']).delimiter
    except Exception:
        first = clean_lines[0]
        delimiter = ';' if first.count(';') > first.count(',') else ','

    print(f"[INFO] Using delimiter: '{delimiter}'")

    # 4. Read to DataFrame (C engine optimized)
    df = pd.read_csv(
        io.StringIO("\n".join(clean_lines)),
        sep=delimiter,
        skipinitialspace=True,
        on_bad_lines='skip',
        engine=None # Let pandas choose faster C engine
    )
    
    if df.empty:
        raise ValueError("Critical Error: DataFrame is empty after parsing.")
        
    return df
