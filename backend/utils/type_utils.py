import pandas as pd

def coerce_numeric(df: pd.DataFrame) -> pd.DataFrame:
    """
    Rigorous type inference for ECU telemetry.
    Forces all columns to numeric, coercing '--', 'N/A', or text to NaN.
    Includes deep whitespace normalization.
    """
    print("[INFO] Normalizing whitespace and coercing numeric types...")
    
    # Deep Whitespace Normalization (Headers & Values)
    df.columns = [c.strip() for c in df.columns]
    df = df.applymap(lambda x: x.strip() if isinstance(x, str) else x)
    
    # Coercion Loop
    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors='coerce')
        
    return df
