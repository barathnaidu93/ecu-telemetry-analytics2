import os
import pandas as pd
import glob

# Standard target columns used by the Dashboard
TARGET_COLUMNS = {
    "RPM": ["nmot", "rpm", "engine rpm", "revs", "engine_speed"],
    "AFR": ["lam", "lambda", "wbo2", "air fuel", "afr"],
    "Throttle": ["tps", "throttle", "accel", "pedal_pos"],
    "MAP": ["map", "boost", "manifold_pressure", "load", "mpx"],
}

def standardize_headers(df):
    """
    Cleans headers and maps fuzzy aliases to standard names.
    """
    df.columns = [str(c).strip().lower() for c in df.columns]
    
    mapping = {}
    for standard, aliases in TARGET_COLUMNS.items():
        found = False
        # Try exact match first
        for col in df.columns:
            if col == standard.lower():
                mapping[col] = standard
                found = True
                break
        
        if found: continue
            
        # Try alias match
        for col in df.columns:
            if any(alias in col for alias in aliases):
                mapping[col] = standard
                break # Move to next standard target
                
    return df.rename(columns=mapping)

def merge_logs(input_dir=".", output_file="merged_calibration_data.csv"):
    """
    Merges all CSV files in the directory into a single high-fidelity database.
    """
    # Normalize input_dir to handle spaces and trailing slashes
    input_dir = os.path.normpath(input_dir)
    
    csv_files = glob.glob(os.path.join(input_dir, "*.csv"))
    # Filter out the output file if it already exists
    csv_files = [f for f in csv_files if os.path.basename(f).lower() != output_file.lower()]
    
    if not csv_files:
        print(f"No CSV logs found in: {input_dir}")
        return

    all_data = []
    print(f"Found {len(csv_files)} logs in '{input_dir}'. Proceeding with seamless integration...")

    for f in csv_files:
        try:
            # Read CSV with comment='#' to skip metadata lines
            df = pd.read_csv(f, comment='#', skipinitialspace=True)
            
            if df.empty:
                print(f"  [!] Skipping empty file: {f}")
                continue

            # 1. Scenario Tagging
            scenario_name = os.path.splitext(os.path.basename(f))[0]
            df["Scenario"] = scenario_name
            
            # 2. Header Standardization
            df = standardize_headers(df)
            
            # 3. Numerical Cleanup (Ensure critical columns are float)
            for col in ["RPM", "AFR", "MAP", "Throttle"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
            
            # Clean up rows where critical data is totally missing
            critical_cols = [c for c in ["RPM", "MAP"] if c in df.columns]
            if critical_cols:
                df = df.dropna(subset=critical_cols)

            all_data.append(df)
            print(f"  [✓] Integrated: {scenario_name} ({len(df)} rows)")
            
        except Exception as e:
            print(f"  [!] Failed to read {f}: {e}")

    if not all_data:
        print("No valid data extracted from logs.")
        return

    # 4. Outer-Join Concatenation (Preserves all unique columns across scenarios)
    print("\nFinalizing global database merge...")
    master_df = pd.concat(all_data, axis=0, sort=False, ignore_index=True)
    
    # Optional: Fill NaNs in numeric columns with 0 or a flag if needed? 
    # For now, leaving as NaN is better for the Heatmap filter (it will drop them).
    
    master_df.to_csv(output_file, index=False)
    print(f"\nSUCCESS: Global Calibration Database generated.")
    print(f"  Path: {os.path.abspath(output_file)}")
    print(f"  Total Rows: {len(master_df):,}")
    print(f"  Total Scenarios: {len(all_data)}")

if __name__ == "__main__":
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else "."
    merge_logs(target)
