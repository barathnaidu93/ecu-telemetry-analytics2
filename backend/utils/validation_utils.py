import pandas as pd
from typing import List

# Physical Limits Sanity Rules (keys are lowercase for case-insensitive matching)
SANITY_RULES = {
    "rpm":  (0, 15000),
    "afr":  (7, 25),
    "tps":  (-1, 101),   # throttle duplicate removed — TPS is the canonical name post-mapping
    "map":  (0, 400),
}

def validate_log(df: pd.DataFrame) -> List[str]:
    """
    Validation layer for high-fidelity diagnostics.
    Flags rows that violate physical engine constraints.
    NOTE: Runs AFTER map_columns(), so column names are uppercase (RPM, MAP, TPS, AFR).
    Uses case-insensitive substring matching to handle both raw and mapped column names.
    """
    print("[INFO] Running sanity check validation...")
    warnings = []

    for col in df.columns:
        col_lower = col.lower()
        for key, (min_v, max_v) in SANITY_RULES.items():
            if key in col_lower:
                numeric_col = pd.to_numeric(df[col], errors="coerce")
                outliers = ((numeric_col < min_v) | (numeric_col > max_v)).sum()
                if outliers > 0:
                    warnings.append(
                        f"Sanity Check: {col} has {outliers} values outside "
                        f"({min_v}–{max_v}) range."
                    )

    return warnings
