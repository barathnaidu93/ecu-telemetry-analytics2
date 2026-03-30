import logging
from typing import Union, Tuple, Dict, Any
import io

# Import modular layers
from utils.io_utils import read_csv_auto
from utils.header_utils import clean_headers
from utils.type_utils import coerce_numeric
from utils.time_utils import normalize_time
from utils.validation_utils import validate_log
from core.mapping import map_columns
from models.metadata import build_metadata

logger = logging.getLogger(__name__)

def process_ecu_file(file_input: Union[str, bytes], filename: str = "telemetry.csv") -> Tuple[Any, Dict[str, Any]]:
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
        
        # 4. Time Normalization
        df = normalize_time(df)
        
        # 5. Alias Mapping (Standardizing Symbols)
        df = map_columns(df)
        
        # 6. Physical Validation Pass
        warnings = validate_log(df)
        
        # 7. Metadata Construction (Sampling, Units, Warnings)
        metadata = build_metadata(df, units, warnings)
        
        print(f"[ENGINE] Ingestion complete. Balanced {len(df)} rows across {len(df.columns)} sensors.\n")
        
        return df, metadata

    except Exception as e:
        print(f"[CRITICAL ERROR] Pipeline failed: {str(e)}")
        raise
