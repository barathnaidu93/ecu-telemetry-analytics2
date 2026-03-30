import re
import pandas as pd
from typing import Dict, Tuple

def clean_headers(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, str]]:
    """
    Strict regex cleaning of ECU headers with unit extraction.
    Returns (cleaned_df, units_map)
    Example: "RPM [1/min]" -> ("rpm", "1_min")
    """
    print("[INFO] Cleaning headers and extracting units...")
    
    orig_cols = list(df.columns)
    cleaned_names = []
    units = {}
    
    for i, col in enumerate(orig_cols):
        name, unit = _extract_and_clean(col)
        
        # Deduplication
        if name in cleaned_names:
            suffix = 1
            while f"{name}_{suffix}" in cleaned_names:
                suffix += 1
            name = f"{name}_{suffix}"
            
        cleaned_names.append(name)
        if unit:
            units[name] = unit

    df.columns = cleaned_names
    return df, units

def _extract_and_clean(col: str) -> Tuple[str, str]:
    """Helper for header cleaning logic."""
    col = str(col).strip()
    
    # 1. Extract Unit
    unit = ""
    unit_match = re.search(r'\[(.*?)\]', col)
    if unit_match:
        unit = unit_match.group(1).replace('/', '_per_').replace(' ', '_')
        col = re.sub(r'\[.*?\]', '', col)
        
    # 2. Strict Regex Sanitization
    col = col.lower()
    col = col.replace('%', '_pct').replace('°', '_deg').replace('/', '_per_')
    col = re.sub(r'[^a-zA-Z0-9]+', '_', col)
    col = re.sub(r'_+', '_', col).strip('_')
    
    if not col and unit:
        col = unit
        unit = ""
        
    return col, unit
