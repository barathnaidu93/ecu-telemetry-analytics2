import pandas as pd
import io
from core.ingestion import process_ecu_file

def verify_pipeline_traceability():
    print("\n--- Verifying Pipeline Traceability ---")
    
    # Mock CSV with BAR units for MAP and Lambda for AFR
    csv_content = """Time,nmot,p_manifold,lam,throttle
0.1,800,1.0,1.0,0.5
0.2,900,1.1,0.9,0.7
0.3,1000,1.2,0.85,1.0
"""
    
    df, metadata = process_ecu_file(csv_content, filename="test_units.csv")
    
    print("\nProcessed DataFrame Columns:", df.columns.tolist())
    print(df.head())
    
    print("\nMetadata Unit Normalization Info:")
    import json
    print(json.dumps(metadata.get("unit_normalization", {}), indent=2))
    
    import numpy as np
    assert np.isclose(df["MAP"].median(), 110.0), f"MAP should be 110 kPa. Got {df['MAP'].median()}"
    assert np.isclose(df["AFR"].median(), 13.23, atol=0.01), f"AFR should be ~13.23 (0.9 * 14.7). Got {df['AFR'].median()}"
    assert df["TPS"].max() == 100.0, "TPS should be 100%"
    
    print("\n--- Pipeline Traceability Verified! ---")

if __name__ == "__main__":
    verify_pipeline_traceability()
