import pandas as pd
import logging
import re
from typing import Dict

# ... [ALIAS_MAP remains the same] ...
ALIAS_MAP = {
    "RPM":   ["nmot", "engine_speed", "revs", "engine_rpm", "rpm"],
    "AFR":   ["afr", "lam", "lambda", "wbo2", "air_fuel", "actual_afr", "wideband", "o2"],
    "MAP":   ["map", "p_manifold", "boost", "manifold_pressure", "mbar", "kpa"],
    "MAF":   ["maf", "airflow", "mass_air", "air_mass", "mq", "g_air"],
    "TPS":   ["tps", "throttle", "pedal_pos", "pedal", "position"],
    "SPEED": ["speed", "velocity", "kmh", "mph", "v_wheel"],
    "IGN":   ["ign", "timing", "ignition", "advance", "ign_ang", "zwout", "spark"],
    "KNOCK": ["knock", "retard", "dzw", "knk"],
    "STFT":          ["stft", "short_term", "shrtft", "st_trim"],
    "LTFT":          ["ltft", "long_term", "longft", "lt_trim"],
    "PULSE_WIDTH":   ["pw", "inj_pw", "injection_time", "inj_ms", "injector_pulse", "pulse_width"],
    "TARGET_LAMBDA": ["target_lambda", "lambda_req", "cmd_lam", "cmd_lambda"],
    "TARGET_AFR":    ["afr_target", "target_afr", "cmd_afr", "afr_req"],
    "IAT":           ["iat", "intake_air", "mat", "act", "air_temp", "manifold_air_temp"],
    "BARO":          ["baro", "ambient", "bap", "barometric"],
    "BOOST_SPEC":     ["boost_spec", "spec_boost", "target_boost", "ldsp", "boost_target", "p_sol", "boost_req"],
    "HPFP_SPEC":      ["hpfp_spec", "spec_hpfp", "target_rail", "rail_pressure_req", "target_hpfp", "f_pressure_target"],
    "HPFP":           ["hpfp", "rail_pressure", "fuel_pressure", "f_press", "fpr"],
    "CLT":            ["clt", "coolant", "engine_temp", "ect", "tstat"]
}

logger = logging.getLogger(__name__)


def sanitize_header(s: str) -> str:
    """Strips all non-alphanumeric characters and lowercases the string."""
    return re.sub(r'[^a-zA-Z0-9]', '', s).lower()


def map_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Maps complex CSV headers to standard internal symbols (RPM, MAP, etc.)
    using Recursive String Normalization to strip noise (brackets, units, spaces).
    """
    print("[INFO] Mapping telemetry aliases (Recursive String Normalizer)...")

    mapping: Dict[str, str] = {}
    claimed_targets: Dict[str, str] = {}

    # 1. Build Comparison Map (Original -> Sanitized)
    # This prevents redundant regex calls and simplifies matching.
    clean_cols = {col: sanitize_header(col) for col in df.columns}

    # 2. Iterate through standards and find the best match
    for standard, aliases in ALIAS_MAP.items():
        best_match = None
        
        # Priority 1: Exact sanitized match (e.g. "rpm" == "rpm")
        for col, c_clean in clean_cols.items():
            if col in mapping: continue
            
            for alias in aliases:
                a_clean = sanitize_header(alias)
                if c_clean == a_clean:
                    best_match = col
                    break
            if best_match: break
            
        # Priority 2: Substring match (e.g. "rpm" in "enginermprpm")
        if not best_match:
            for col, c_clean in clean_cols.items():
                if col in mapping: continue
                
                for alias in aliases:
                    a_clean = sanitize_header(alias)
                    # Use length guard to prevent 'o2' matching 'coolant'
                    if a_clean in c_clean and (len(a_clean) >= 3 or a_clean == c_clean):
                        best_match = col
                        break
                if best_match: break

        if best_match:
            if standard in claimed_targets:
                logger.warning(f"[Mapping] Collision: '{best_match}' skipped for '{standard}' (already held by {claimed_targets[standard]})")
            else:
                mapping[best_match] = standard
                claimed_targets[standard] = best_match

    mapped_list = list(mapping.values())
    if mapped_list:
        print(f"[INFO] Mapped {len(mapped_list)} sensors: {mapped_list}")
    else:
        print("[WARN] No sensors identified in CSV!")
        
    return df.rename(columns=mapping)
