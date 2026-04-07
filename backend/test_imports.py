import sys
import os

# Add local paths for modular architecture
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

try:
    import fastapi
    import uvicorn
    import pandas
    import google.generativeai as genai
    from core.ingestion import process_ecu_file
    from utils.binning_utils import snap_to_bins
    print("Imports successful")
except Exception as e:
    print(f"Import failed: {e}")
    sys.exit(1)
