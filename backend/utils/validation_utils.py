import pandas as pd
from typing import List

# Physical Limits Sanity Rules
SANITY_RULES = {
    "rpm": (0, 15000),
    "afr": (7, 25),
    "throttle": (-1, 101),
    "tps": (-1, 101)
}

def validate_log(df: pd.DataFrame) -> List[str]:
    """
    Validation layer for high-fidelity diagnostics.
    Flags rows that violate physical engine constraints.
    """
    print("[INFO] Running sanity check validation...")
    warnings = []
    
    for col in df.columns:
        for key, (min_v, max_v) in SANITY_RULES.items():
            if key in col:
                outliers = ((df[col] < min_v) | (df[col] > max_v)).sum()
                if outliers > 0:
                    warnings.append(f"Sanity Check: {col} has {outliers} values outside ({min_v}-{max_v}) range.")
                    
    return warnings
