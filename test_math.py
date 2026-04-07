import pandas as pd
from backend.core.ingestion import process_ecu_file
from backend.main import build_file_context

print("------------------------------------------")
print("TEST: Math Engine on Honda Dyno Pull")
with open("honda  test files/Dyno_Pull_K20A2_Stock_NA_20260327.csv", "rb") as f:
    contents = f.read()

df, meta = process_ecu_file(contents, "Dyno.csv", fuel_type="gasoline")
print("New Derived Columns Added:")
for col in ["ACCEL_RATE", "PRESSURE_RATIO", "IDC", "DELTA_LAMBDA", "CORRECTED_IGN"]:
    if col in df.columns:
        print(f"✅ {col} -> Min: {df[col].min()} | Max: {df[col].max()}")
    else:
        print(f"❌ {col} (Missing dependencies)")

print("\n------------------------------------------")
print("TEST: Verifying Context Serialization")
import json
# Simulate the context builder payload
from backend.main import parse_csv
res = parse_csv(contents, "Dyno.csv", fuel_type="gasoline", aspiration="NA")
payload = {"data": res, "type": "csv"}
context = build_file_context(payload)
if "THERMODYNAMIC ENGINE MODELS" in context:
    print("✅ Context engine successfully absorbed math limits.")
else:
    print("❌ Context engine failed to print thermodynamics block.")
