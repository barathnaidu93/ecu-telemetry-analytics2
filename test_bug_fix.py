import pandas as pd
from backend.core.ingestion import process_ecu_file
from backend.main import parse_csv

print("------------------------------------------")
print("TEST 1: Honda Dyno Pull (Boost/TPS Logic)")
with open("honda  test files/Dyno_Pull_K20A2_Stock_NA_20260327.csv", "rb") as f:
    contents = f.read()

res = parse_csv(contents, "Dyno.csv")
print("Master chart points:", len(res["chart_master"]))
if len(res["chart_master"]) > 0:
    print("Sample Master Point:", res["chart_master"][50])
    
print("\n------------------------------------------")
print("TEST 2: EngineFaultDB (Synthetic Time axis)")
with open("EngineFaultDB_Final.csv", "rb") as f:
    fault = f.read()

res_fault = parse_csv(fault[:100000], "Fault.csv")
print("Fault chart points:", len(res_fault["chart_master"]))
if len(res_fault["chart_master"]) > 0:
    print("Sample Fault Point:", res_fault["chart_master"][20])
