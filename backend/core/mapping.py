import pandas as pd
from typing import Dict

# Central Alias Database
ALIAS_MAP = {
    "RPM": ["nmot", "engine_speed", "revs", "engine_rpm"],
    "AFR": ["lam", "lambda", "wbo2", "air_fuel", "actual_afr"],
    "MAP": ["p_manifold", "boost", "manifold_pressure", "pressure", "mbar"],
    "TPS": ["throttle", "accel", "pedal_pos", "tps", "angle"],
    "TIME": ["time", "timestamp", "offset", "sec", "s"]
}

def map_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Maps cleaned headers to standard internal symbols (RPM, MAP, etc.)
    using a flexible alias database.
    """
    print("[INFO] Mapping telemetry aliases to standard symbols...")
    
    mapping = {}
    for standard, aliases in ALIAS_MAP.items():
        for col in df.columns:
            if any(alias in col for alias in aliases):
                mapping[col] = standard
                break # Move to next standard target
                
    return df.rename(columns=mapping)
