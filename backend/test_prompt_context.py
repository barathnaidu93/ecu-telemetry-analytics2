import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from main import build_file_context

# Mock the data_store object that main.py creates
mock_store = {
    "type": "csv",
    "data": {
        "filename": "honda_pull.csv",
        "rows": 5120,
        "all_columns": ["TIME", "RPM", "MAP", "AFR", "TPS", "STFT", "KNOCK"],
        "scenario_summary": {
            "WOT Pull": {"pct": 12.5, "avg_rpm": 6200, "avg_map": 210, "avg_afr": 11.4},
            "Idle": {"pct": 40.0, "avg_rpm": 850, "avg_map": 30, "avg_afr": 14.7},
            "Unknown": {"pct": 5.0}
        },
        "afr_heatmap": {
            "load_type": "MAP",
            "wot_cells": [
                {"rpm": 6500, "load": 220, "value": 11.2, "std": 0.1, "count": 45},
                {"rpm": 6000, "load": 210, "value": 11.5, "std": 0.2, "count": 80},
                {"rpm": 5500, "load": 200, "value": 12.8, "std": 0.5, "count": 12}  # Lean spot!
            ]
        },
        "metadata": {
            "unit_normalization": {
                "anomalies": {
                    "AFR": {"count": 12, "percentage": 0.23, "min_violation": 13.5, "max_violation": 18.2},
                    "MAP": {"count": 2, "percentage": 0.05, "min_violation": 280, "max_violation": 290}
                }
            }
        },
        "column_stats": {
            "STFT": {"avg": 14.5, "min": -2.0, "max": 25.0, "count": 5120},
            "KNOCK": {"avg": 0.1, "min": 0.0, "max": 4.5, "count": 5120}
        }
    }
}

def run():
    print("Testing build_file_context() output:\n")
    print("-" * 50)
    output = build_file_context(mock_store)
    print(output)
    print("-" * 50)
    print("\nTest passed if the output contains sections for Scenarios, Heatmap, Anomalies, and Fuel Trims.")

if __name__ == "__main__":
    run()
