import logging
from typing import Union, Tuple, Dict, Any
import io

# Import modular layers
from utils.io_utils import read_csv_auto
from utils.header_utils import clean_headers
from utils.type_utils import coerce_numeric
from utils.time_utils import normalize_time
from utils.validation_utils import validate_log
from utils.unit_utils import normalize_units
from utils.math_utils import apply_physics_derivations
from core.mapping import map_columns
from models.metadata import build_metadata

logger = logging.getLogger(__name__)

def process_ecu_file(file_input: Union[str, bytes], filename: str = "telemetry.csv", fuel_type: str = "gasoline") -> Tuple[Any, Dict[str, Any]]:
    """
    The "Brain" orchestration layer.
    Standardizes input, chains utilities, and returns a clean (df, metadata) pair.
    """
    print(f"\n[ENGINE] Starting modular ingestion pipeline for: {filename}")
    
    try:
        # 1. Standardized IO
        df = read_csv_auto(file_input, filename=filename)
        
        # 2. Header Sanitization & Unit Extraction
        df, units = clean_headers(df)
        
        # 3. Numeric Coercion (Strict Type Inference)
        df = coerce_numeric(df)
        
        # 4. Time Normalization (detect, convert ms→s, rename to canonical 'TIME')
        df = normalize_time(df)

        # 4b. Synthetic Time Safety Net (MUST run before map_columns)
        # normalize_time() already generates TIME when it can detect/synthesize.
        # This guard covers edge cases where normalize_time silently failed.
        if "TIME" not in df.columns:
            logger.warning("[ENGINE] TIME still missing after normalize_time. Synthesizing fallback 10Hz axis.")
            df["TIME"] = [round(i * 0.1, 4) for i in range(len(df))]

        # 5. Alias Mapping (Standardizing Symbols)
        # TIME is intentionally excluded from ALIAS_MAP so it is never touched here.
        df = map_columns(df)

        # 5b. Commercial-Grade Unit Normalization (V2)
        df = normalize_units(df, fuel_type=fuel_type)

        # 5c. Advanced Thermodynamic Derivations
        # Computes IDC, Pressure Ratio, dRPM/dt, Target Lambda Error
        df = apply_physics_derivations(df, fuel_type=fuel_type)
        
        # 6. Physical Validation Pass
        warnings = validate_log(df)
        
        # 7. Metadata Construction (Sampling, Units, Warnings)
        metadata = build_metadata(df, units, warnings)
        
        # 7b. Inject Unit Normalization Metadata for Traceability
        metadata["unit_normalization"] = {
            "info": df.attrs.get("unit_info", {}),
            "confidence": df.attrs.get("unit_confidence", {}),
            "original_units": df.attrs.get("original_units", {}),
            "anomalies": df.attrs.get("anomalies_detected", {}),
            "fuel_assumption": df.attrs.get("fuel_type", "gasoline"),
        }
        
        print(f"[ENGINE] Ingestion complete. Balanced {len(df)} rows across {len(df.columns)} sensors.\n")
        
        return df, metadata

    except Exception as e:
        print(f"[CRITICAL ERROR] Pipeline failed: {str(e)}")
        raise
