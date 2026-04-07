import pandas as pd
import sys
import os

# Add backend to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.mapping import map_columns

def verify_seat_log_mapping():
    csv_path = "./csv_logs/2017-07-05_Seat_Leon_S_KA_Normal.csv"
    if not os.path.exists(csv_path):
        print(f"File not found: {csv_path}")
        return

    print(f"\n--- Verifying mapping for: {csv_path} ---")
    
    # Read only the header
    df = pd.read_csv(csv_path, nrows=5)
    print("Original Columns:", df.columns.tolist())
    
    mapped_df = map_columns(df)
    
    mapped_cols = [c for c in mapped_df.columns if c in ["RPM", "MAP", "AFR", "TPS", "SPEED", "IGN", "IAT", "CLT"]]
    print("\nVerified Mapped Sensors:", mapped_cols)
    
    # Check for specific sensors we know are in VCDS/Seat logs
    important_sensors = ["CLT", "MAP", "TPS"]
    for sensor in important_sensors:
        if sensor in mapped_df.columns:
            print(f" [PASS] '{sensor}' found")
        else:
            print(f" [WARNING] '{sensor}' NOT found in mapped columns")

if __name__ == "__main__":
    verify_seat_log_mapping()
