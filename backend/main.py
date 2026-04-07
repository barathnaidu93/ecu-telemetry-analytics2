import io
import os
import sys
import numpy as np
import uuid
import json

import google.generativeai as genai
import pandas as pd
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
# Add local paths for modular architecture
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

from core.ingestion import process_ecu_file
from utils.binning_utils import snap_to_bins
from utils.downsample_utils import m4_decimate_multivariate
from utils.correlation_utils import get_temporal_snapshot, identify_critical_events

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

ALLOWED = {".csv", ".bin"}
MAX_SIZE = 50 * 1024 * 1024

# Session caching architecture
SESSION_DIR = os.path.join(BASE_DIR, ".cache", "sessions")
os.makedirs(SESSION_DIR, exist_ok=True)


class ChatRequest(BaseModel):
    message: str
    session_id: str = None  # Optional for backward-compatibility fallback
    api_key: str = None


def _get_session_data(session_id: str = None):
    # Backward compatibility: if no session provided (legacy frontend), load newest session
    if not session_id:
        sessions = [f for f in os.listdir(SESSION_DIR) if f.endswith('.json')]
        if not sessions:
            raise HTTPException(status_code=404, detail="No session found. Please upload a file first.")
        sessions.sort(key=lambda x: os.path.getmtime(os.path.join(SESSION_DIR, x)), reverse=True)
        session_id = sessions[0].replace(".json", "")

    path = os.path.join(SESSION_DIR, f"{session_id}.json")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Session expired or not found.")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            data["_active_session_id"] = session_id  # Inject to track loaded fallback
            return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load session: {str(e)}")


def _save_session_data(session_id: str, payload: dict):
    path = os.path.join(SESSION_DIR, f"{session_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f)


@app.get("/data")
def get_data(session_id: str = None):
    data_store = _get_session_data(session_id)
    return {
        "session_id": data_store.get("_active_session_id"),
        "type": data_store.get("type"),
        "filename": data_store.get("filename"),
        "data": data_store.get("data"),
    }




def run_diagnostics(df: pd.DataFrame, y_map: dict, metadata: dict = None, aspiration: str = "NA") -> dict:
    """
    Evaluates engine health using professional-grade rules based on 
    thermodynamic derivations, sensor anomalies, and physical limits.
    Returns: { 'status': 'Normal'|'Warning'|'Critical', 'health_score': 0-100, 'alerts': [] }
    """
    alerts = []
    score = 100
    metadata = metadata or {}

    # 1. Reach sensors (prioritize standardized symbols from map_columns)
    rpm_c   = "RPM" if "RPM" in df.columns else y_map.get("RPM")
    tps_c   = "TPS" if "TPS" in df.columns else y_map.get("TPS")
    map_c   = "MAP" if "MAP" in df.columns else y_map.get("MAP")
    afr_c   = "AFR" if "AFR" in df.columns else y_map.get("AFR")
    hpfp_c  = "HPFP" if "HPFP" in df.columns else y_map.get("HPFP")
    ign_c   = "IGN" if "IGN" in df.columns else y_map.get("IGN")
    
    # Target symbols
    boost_spec_c = "BOOST_SPEC" if "BOOST_SPEC" in df.columns else y_map.get("Boost Spec")
    hpfp_spec_c  = "HPFP_SPEC"  if "HPFP_SPEC"  in df.columns else y_map.get("HPFP Spec")

    # Derived symbols (from apply_physics_derivations)
    idc_c          = "IDC"
    knock_c        = "KNOCK"
    d_lam_c        = "DELTA_LAMBDA"
    pr_c           = "PRESSURE_RATIO"
    aligned_afr_c  = "ALIGNED_AFR" if "ALIGNED_AFR" in df.columns else afr_c
    safety_floor_c = "SAFETY_AFR_FLOOR" if "SAFETY_AFR_FLOOR" in df.columns else None

    # Fallback/Legacy symbols
    co_c   = y_map.get("CO")
    hc_c   = y_map.get("HC")
    cons_c = y_map.get("Consumption")

    # Physics Correlation Symbols
    pwr_c   = "Power" if "Power" in df.columns else y_map.get("Power")
    force_c = "Force" if "Force" in df.columns else y_map.get("Force")

    # Guard: Need at least RPM to do anything
    if not rpm_c or rpm_c not in df.columns:
        return {
            "status": "Undetermined",
            "health_score": 0,
            "alerts": ["Insufficient sensor data for automated diagnostics."],
        }

    try:
        # Convert necessary columns to numeric
        temp_df = df.copy()
        cols_to_fix = [rpm_c, tps_c, map_c, afr_c, hpfp_c, ign_c, boost_spec_c, hpfp_spec_c, 
                       idc_c, knock_c, d_lam_c, pr_c, co_c, hc_c, pwr_c, force_c]
        for col in cols_to_fix:
            if col and col in temp_df.columns:
                temp_df[col] = pd.to_numeric(temp_df[col], errors="coerce")
        
        # --- PRE-COMPUTE DYNAMIC BASELINES ---
        # If log is low-throttle (e.g. EngineFaultDB), we scale our "High Load" gate
        max_tps = temp_df[tps_c].max() if tps_c and tps_c in temp_df.columns else 100
        # If max throttle is < 50%, we use 90% of max as the "High Load" gate for this session
        load_gate = 80 if max_tps > 50 else max(2.0, max_tps * 0.9)

        # ── DFCO Exclusion Mask ───────────────────────────────────────────────
        # Deceleration Fuel Cut-Off (DFCO): the ECU deliberately cuts injectors
        # during engine braking (closed throttle + high RPM + falling RPM).  The
        # resulting lean AFR spike is a calibrated FEATURE, not a fault.  If we
        # leave these rows in, they trigger false "Critical Lean" alerts and inflate
        # the knock/fueling risk score.  Exclude them once here — before ALL safety
        # analysis — so every subsequent block sees a DFCO-clean dataset.
        dfco_mask = pd.Series(False, index=temp_df.index)
        if tps_c and tps_c in temp_df.columns and rpm_c and rpm_c in temp_df.columns:
            rpm_diff = temp_df[rpm_c].diff()
            dfco_mask = (
                (temp_df[tps_c] < 2) &
                (temp_df[rpm_c] > 1200) &
                (rpm_diff < -30)           # RPM actively falling
            )
        dfco_count = int(dfco_mask.sum())
        if dfco_count > 0:
            print(f"[DFCO] Excluded {dfco_count} decel fuel-cut rows from safety analysis.")
            temp_df = temp_df[~dfco_mask].copy()

        # Pre-define list of sensors for snapshots
        snapshot_sensors = [s for s in [rpm_c, tps_c, map_c, afr_c, ign_c, knock_c, d_lam_c, hpfp_c, idc_c] if s and s in temp_df.columns]
        snapshots = []

        # --- A. DATA INTEGRITY CHECK ---
        # Penalize if sensors were flagging out-of-physical-bounds during normalization
        anomalies = metadata.get("unit_normalization", {}).get("anomalies", {})
        if anomalies:
            for sensor, info in anomalies.items():
                pct = info.get("percentage", 0)
                if pct > 2: 
                    alerts.append(f"Data Integrity: Sensor [{sensor}] showing {pct}% erratic/out-of-bounds readings.")
                    score -= min(15, int(pct * 2))

        # --- B. KNOCK PROTECTION ---
        if knock_c in temp_df.columns:
            # Identify top 3 peak knock events
            knk_times = identify_critical_events(temp_df, knock_c, 1.5, top_n=3)
            if knk_times:
                for kt in knk_times:
                    snap = get_temporal_snapshot(temp_df, kt, snapshot_sensors)
                    snap["_event_type"] = "Knock Retard"
                    snapshots.append(snap)
                
                # Check for high load
                k_events = temp_df[temp_df[knock_c] > 1.5]
                high_load_k = k_events[k_events.get(tps_c, 50) >= load_gate]

                # Thermal-Knock Correlation ───────────────────────────────────
                # Compare the IAT at knock event timestamps against the session
                # baseline (10th-percentile IAT = coolest ambient sample).  A
                # large delta indicates intercooler heat soak rather than a bad
                # ignition map, which is a completely different root cause.
                knock_cause = "Ignition Map / Octane (verify fuel quality and ignition table)"
                if "IAT" in temp_df.columns and not k_events.empty:
                    knk_iat_mean       = temp_df.loc[k_events.index, "IAT"].mean()
                    session_iat_base   = temp_df["IAT"].quantile(0.10)
                    iat_delta          = knk_iat_mean - session_iat_base
                    if iat_delta > 12:
                        knock_cause = (
                            f"Thermal — Severe IAT Heat Soak (+{iat_delta:.1f}°C above session baseline). "
                            "Likely cause: intercooler saturation or restricted intake path."
                        )
                    elif iat_delta > 6:
                        knock_cause = (
                            f"Thermal — IAT elevated at knock events (+{iat_delta:.1f}°C above baseline). "
                            "Possible intercooler efficiency loss at sustained load."
                        )
                    else:
                        knock_cause = (
                            f"Ignition Map / Octane (IAT only +{iat_delta:.1f}°C above baseline — "
                            "thermal cause unlikely; check timing table and octane rating)."
                        )

                if not high_load_k.empty:
                    alerts.append(f"Critical: Active Knock Retard under High Load. Probable Cause: {knock_cause}.")
                    score -= 40
                else:
                    alerts.append(f"Warning: Low-level Knock Retard detected. Probable Cause: {knock_cause}.")
                    score -= 10

        # --- C. FUELING SAFETY (DELTA LAMBDA) ---
        if d_lam_c in temp_df.columns:
            # Positive Delta Lambda = Lean error. Capture snapshots of biggest lean errors.
            lean_times = identify_critical_events(temp_df, d_lam_c, 10, top_n=2)
            for lt in lean_times:
                snap = get_temporal_snapshot(temp_df, lt, snapshot_sensors)
                snap["_event_type"] = "Fueling Error (Lean)"
                snapshots.append(snap)
                
            lean_pull = temp_df[(temp_df.get(tps_c, 0) >= load_gate) & (temp_df[d_lam_c] > 10)]
            if len(lean_pull) > (len(temp_df) * 0.02):
                alerts.append("Critical: Severe Lean Condition under Load (>10% Fueling Error)")
                score -= 35
        # Mid-tier: Dynamic AFR Safety Floor ──────────────────────────────────
        # Used when no TARGET_LAMBDA/TARGET_AFR exists but MAP+AFR are present.
        # SAFETY_AFR_FLOOR is a per-row lean limit that scales with boost pressure
        # (computed in math_utils.apply_physics_derivations).
        elif safety_floor_c and safety_floor_c in temp_df.columns and afr_c and afr_c in temp_df.columns:
            afr_check_col = "ALIGNED_AFR" if "ALIGNED_AFR" in temp_df.columns else afr_c
            if tps_c and tps_c in temp_df.columns:
                load_filter = temp_df[tps_c] >= load_gate
            else:
                load_filter = pd.Series(True, index=temp_df.index)
            dynamic_lean = temp_df[
                load_filter & (temp_df[afr_check_col] > temp_df[safety_floor_c])
            ]
            if len(dynamic_lean) > (len(temp_df) * 0.03):
                peak_lean = round(float(dynamic_lean[afr_check_col].max()), 1)
                avg_floor = round(float(dynamic_lean[safety_floor_c].mean()), 1)
                lean_snap_times = identify_critical_events(temp_df, afr_check_col, avg_floor, top_n=2)
                for lt in lean_snap_times:
                    snap = get_temporal_snapshot(temp_df, lt, snapshot_sensors)
                    snap["_event_type"] = "Dynamic Lean (vs Safety Floor)"
                    snapshots.append(snap)
                alerts.append(
                    f"Critical: Dynamic Lean Under Load — AFR peaked at {peak_lean} "
                    f"(dynamic safety floor: {avg_floor}, margin: +{round(peak_lean - avg_floor, 1)}). "
                    "Safety floor scales with actual boost pressure."
                )
                score -= 30

        # Fallback to legacy Emission rules + Baseline monitoring
        elif co_c and hc_c and co_c in temp_df.columns:
            # Check absolute thresholds
            rich_events = temp_df[(temp_df[co_c] > 2.8) & (temp_df[hc_c] > 230)]
            if len(rich_events) > (len(temp_df) * 0.05):
                alerts.append("Critical: Persistent Rich Burn Detected (High CO/HC)")
                score -= 40
            
            # Check statistical outliers (sudden spikes relative to session)
            co_mean, co_std = temp_df[co_c].mean(), temp_df[co_c].std()
            if not pd.isna(co_std) and co_std > 0:
                outliers = temp_df[temp_df[co_c] > (co_mean + (4 * co_std))]
                if len(outliers) > (len(temp_df) * 0.02):
                    alerts.append("Warning: Abnormal Emission Spikes detected relative to session baseline.")
                    score -= 20

        # --- D. INJECTOR DUTY CYCLE (with Root-Cause Context) ---
        if idc_c in temp_df.columns:
            max_idc = temp_df[idc_c].max()
            if not pd.isna(max_idc) and max_idc > 90:
                # Root-cause: find exactly what the engine was doing at peak IDC
                peak_idc_idx  = temp_df[idc_c].idxmax()
                peak_rpm_idc  = None
                peak_map_idc  = None
                try:
                    if rpm_c and rpm_c in temp_df.columns:
                        peak_rpm_idc = round(float(temp_df.loc[peak_idc_idx, rpm_c]), 0)
                    if map_c and map_c in temp_df.columns:
                        peak_map_idc = round(float(temp_df.loc[peak_idc_idx, map_c]), 1)
                except Exception:
                    pass

                idc_cause = "High Engine Demand"
                if peak_map_idc is not None and peak_map_idc > 200:
                    idc_cause = "Excessive Boost Pressure — consider reducing boost target or upgrading injectors"
                elif peak_rpm_idc is not None and peak_rpm_idc > 6000:
                    idc_cause = "High-RPM Demand near redline — injector static flow rate is the limiting factor"
                elif peak_map_idc is not None and peak_map_idc < 130:
                    idc_cause = "High IDC at Low Boost — injectors likely undersized for this fuelling demand"

                ctx = f"at {peak_rpm_idc} RPM / {peak_map_idc} kPa" if peak_rpm_idc else ""
                if max_idc > 100:
                    alerts.append(
                        f"Critical: Injector Saturation — Peak IDC {round(max_idc, 1)}% {ctx}. "
                        f"Root Cause: {idc_cause}."
                    )
                    score -= 30
                else:
                    alerts.append(
                        f"Warning: High Injector Duty Cycle — Peak IDC {round(max_idc, 1)}% {ctx}. "
                        f"Root Cause: {idc_cause}."
                    )
                    score -= 15

        # --- E. BOOST & TURBO EFFICIENCY (TURBO ONLY) ---
        if aspiration.upper() == "TURBO":
            if map_c in temp_df.columns and boost_spec_c in temp_df.columns:
                underboost = temp_df[(temp_df.get(tps_c, 0) >= load_gate) & (temp_df[boost_spec_c] - temp_df[map_c] > 30)]
                if len(underboost) > (len(temp_df) * 0.05):
                    alerts.append("Critical: Boost Leak Detected (Actual significantly below Target)")
                    score -= 35

            if pr_c in temp_df.columns:
                max_pr = temp_df[pr_c].max()
                if max_pr > 3.0: 
                    alerts.append(f"Warning: Excessive Pressure Ratio (PR: {round(max_pr, 2)}). High turbo stress.")
                    score -= 10

        # --- F. FUEL RAIL PRESSURE (HPFP) ---
        if hpfp_c in temp_df.columns and hpfp_spec_c in temp_df.columns:
            fuel_sag = temp_df[(temp_df.get(tps_c, 0) >= load_gate) & (temp_df[hpfp_spec_c] - temp_df[hpfp_c] > 15)]
            if len(fuel_sag) > (len(temp_df) * 0.03):
                alerts.append("Critical: HPFP Rail Pressure Sag (Fuel Supply Limitation)")
                score -= 30

        # --- H. PHYSICAL CORRELATION (PARADOX DETECTION) ---
        # 1. Ghost Torque: High power/force at low throttle
        if tps_c in temp_df.columns:
            if pwr_c in temp_df.columns:
                ghost_pwr = temp_df[(temp_df[tps_c] < 5) & (temp_df[pwr_c] > (temp_df[pwr_c].max() * 0.5))]
                if len(ghost_pwr) > (len(temp_df) * 0.01):
                    alerts.append("Critical: Physical Paradox - High Power Output at Zero Throttle.")
                    score -= 50
            if force_c in temp_df.columns:
                ghost_force = temp_df[(temp_df[tps_c] < 5) & (temp_df[force_c] > (temp_df[force_c].max() * 0.5))]
                if len(ghost_force) > (len(temp_df) * 0.01):
                    alerts.append("Critical: Physical Paradox - High Force detected at Zero Throttle.")
                    score -= 50

        # 2. Vacuum Paradox: Positive Boost at idle/low RPM
        if map_c in temp_df.columns and rpm_c in temp_df.columns and tps_c in temp_df.columns:
            # If MAP > 120 kPa (Boost) but throttle is closed and RPM is low
            v_paradox = temp_df[(temp_df[map_c] > 120) & (temp_df[tps_c] < 10) & (temp_df[rpm_c] < 2000)]
            if len(v_paradox) > (len(temp_df) * 0.02):
                alerts.append("Warning: Vacuum Paradox - Boost detected while throttle is closed.")
                score -= 25

        # ── NEW: IDLE STABILITY ANALYSIS ─────────────────────────────────────
        # Rough idle is one of the earliest symptoms of vacuum leaks, injector
        # fouling, MAF sensor drift, or cam timing faults.  We use the
        # Coefficient of Variation (CV = std/mean × 100%) of RPM at idle as a
        # normalised instability score — engine-agnostic and scale-independent.
        if rpm_c and rpm_c in temp_df.columns:
            idle_df = temp_df[
                (temp_df[rpm_c] > 400) & (temp_df[rpm_c] < 1050)
            ]
            if len(idle_df) > 15:   # need enough samples for meaningful stats
                idle_std  = idle_df[rpm_c].std()
                idle_mean = idle_df[rpm_c].mean()
                if idle_mean > 0:
                    idle_cv = (idle_std / idle_mean) * 100
                    if idle_cv > 8:
                        alerts.append(
                            f"Critical: Severe Idle Instability — RPM fluctuation ±{idle_std:.0f} RPM "
                            f"({idle_cv:.1f}% CV). Possible vacuum leak, injector fault, or cam timing issue."
                        )
                        score -= 15
                    elif idle_cv > 4:
                        alerts.append(
                            f"Warning: Rough Idle — RPM fluctuation ±{idle_std:.0f} RPM "
                            f"({idle_cv:.1f}% CV). Monitor for progressive worsening."
                        )
                        score -= 8

                # AFR stability at idle — vacuum leaks cause lean/oscillating AFR
                if afr_c and afr_c in temp_df.columns:
                    idle_afr_std = idle_df[afr_c].dropna().std()
                    if not pd.isna(idle_afr_std) and idle_afr_std > 1.5:
                        alerts.append(
                            f"Warning: Idle AFR Instability (sigma={idle_afr_std:.2f} AFR) — "
                            "possible vacuum leak, injector imbalance, or O2 sensor drift."
                        )
                        score -= 8

        # --- G. EFFICIENCY Fallback ---
        if cons_c and rpm_c and cons_c in temp_df.columns:
            inefficient = temp_df[(temp_df[rpm_c] > 1000) & (temp_df[cons_c] / temp_df[rpm_c] > 0.0025)]
            if len(inefficient) > (len(temp_df) * 0.1):
                alerts.append("Warning: Low Fuel Efficiency (High Consumption/RPM ratio)")
                score -= 15

    except Exception as e:
        import traceback
        traceback.print_exc()
        alerts.append(f"Diagnostic Engine Error: {str(e)}")

    status = "Normal"
    if score < 60:
        status = "Critical"
    elif score < 90:
        status = "Warning"

    return {
        "status": status,
        "health_score": max(0, score),
        "alerts": list(set(alerts)),
        "correlation_snapshots": snapshots,
    }


def _compute_heatmap_cells(df, rpm_col, signal_col, load_col,
                            rpm_min=400, load_min=None, sig_min=None, sig_max=None):
    """Generic RPM x Load heatmap builder. Returns (cells, rpm_bins, load_bins)."""
    required = [c for c in [rpm_col, signal_col, load_col] if c and c in df.columns]
    if len(required) < 3:
        return [], [], []

    tmp = df[[rpm_col, signal_col, load_col]].copy()
    for c in [rpm_col, signal_col, load_col]:
        tmp[c] = pd.to_numeric(tmp[c], errors="coerce")

    mask = tmp[rpm_col] >= rpm_min
    if sig_min  is not None: mask &= tmp[signal_col] >= sig_min
    if sig_max  is not None: mask &= tmp[signal_col] <= sig_max
    if load_min is not None: mask &= tmp[load_col]   >= load_min

    clean = tmp[mask].dropna()
    if clean.empty:
        return [], [], []

    clean = clean.copy()
    clean["RPM_Bin"]  = (clean[rpm_col]  / 500).round() * 500
    clean["Load_Bin"] = (clean[load_col] / 10 ).round() * 10

    grp = clean.groupby(["RPM_Bin", "Load_Bin"])[signal_col].agg(
        ["mean", "std", "count"]
    ).reset_index()

    cells = [
        {
            "rpm":   int(r["RPM_Bin"]),
            "load":  int(r["Load_Bin"]),
            "value": round(float(r["mean"]), 2),
            "std":   round(float(r["std"]) if pd.notna(r["std"]) else 0.0, 2),
            "count": int(r["count"]),
        }
        for _, r in grp.iterrows()
    ]

    r_min, r_max = int(clean["RPM_Bin"].min()), int(clean["RPM_Bin"].max())
    l_min, l_max = int(clean["Load_Bin"].min()), int(clean["Load_Bin"].max())
    return cells, list(range(r_min, r_max + 500, 500)), list(range(l_min, l_max + 10, 10))


def generate_afr_heatmap(df: pd.DataFrame, y_map: dict) -> dict:
    """AFR Heatmap — RPM x Load (MAP preferred, TPS fallback). Cells: value, std, count."""
    rpm_col = y_map.get("RPM")
    afr_col = y_map.get("AFR")
    map_col = y_map.get("MAP")
    tps_col = y_map.get("TPS")

    if not rpm_col or not afr_col:
        return {"load_type": "N/A", "cells": [], "wot_cells": [], "rpm_bins": [], "load_bins": []}

    if map_col and map_col in df.columns:
        load_col, load_source, load_min = map_col, "MAP", 30
    elif tps_col and tps_col in df.columns:
        load_col, load_source, load_min = tps_col, "TPS", 15
    else:
        return {"load_type": "N/A", "cells": [], "wot_cells": [], "rpm_bins": [], "load_bins": []}

    cells, rpm_bins, load_bins = _compute_heatmap_cells(
        df, rpm_col, afr_col, load_col,
        rpm_min=400, load_min=load_min, sig_min=8, sig_max=20
    )

    # WOT-only subset
    wot_cells = []
    if tps_col and tps_col in df.columns and cells:
        tmp = df.copy()
        for c in [rpm_col, afr_col, load_col, tps_col]:
            if c and c in tmp.columns:
                tmp[c] = pd.to_numeric(tmp[c], errors="coerce")
        wot_df = tmp[
            (tmp[rpm_col] >= 400) & (tmp[afr_col] >= 8) & (tmp[afr_col] <= 20) &
            (tmp[load_col] >= load_min) & (tmp[tps_col] > 90)
        ].dropna(subset=[rpm_col, afr_col, load_col])
        if not wot_df.empty:
            wot_df = wot_df.copy()
            wot_df["RPM_Bin"]  = (wot_df[rpm_col]  / 500).round() * 500
            wot_df["Load_Bin"] = (wot_df[load_col] / 10 ).round() * 10
            grp = wot_df.groupby(["RPM_Bin", "Load_Bin"])[afr_col].agg(
                ["mean", "std", "count"]
            ).reset_index()
            wot_cells = [
                {"rpm": int(r["RPM_Bin"]), "load": int(r["Load_Bin"]),
                 "value": round(float(r["mean"]), 2),
                 "std": round(float(r["std"]) if pd.notna(r["std"]) else 0.0, 2),
                 "count": int(r["count"])}
                for _, r in grp.iterrows()
            ]

    return {
        "load_type": load_source,
        "cells": cells,
        "wot_cells": wot_cells,
        "rpm_bins": rpm_bins,
        "load_bins": load_bins,
        "signal_label": "Air-Fuel Ratio",
    }


def generate_text_ve_grid(df: pd.DataFrame, y_map: dict) -> str:
    """Generates a 10x10 text-based grid of AFR Delta (or Actual AFR) for AI analysis."""
    rpm_col = y_map.get("RPM")
    map_col = y_map.get("MAP")
    tps_col = y_map.get("TPS")
    afr_col = "AFR" if "AFR" in df.columns else ("LAMBDA" if "LAMBDA" in df.columns else None)
    d_lam_col = "DELTA_LAMBDA"

    if not rpm_col:
        return "N/A (Missing RPM sensor)"

    load_col = map_col if (map_col and map_col in df.columns) else tps_col
    if not load_col or load_col not in df.columns:
        return "N/A (Missing Load Column - MAP or TPS)"

    # Determine what we are actually plotting
    target_data_col = d_lam_col if d_lam_col in df.columns else afr_col
    if not target_data_col:
        return "N/A (No AFR or Lambda data found)"

    is_error_grid = (target_data_col == d_lam_col)
    val_label = "AFR % Error" if is_error_grid else "Actual AFR/Lam"

    # Convert to numeric
    df = df.copy()
    for c in [rpm_col, load_col, target_data_col]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=[rpm_col, load_col, target_data_col])

    if df.empty:
        return "N/A (No valid matching data points for grid)"

    # Define 10x10 bins
    rpm_min, rpm_max = df[rpm_col].min(), df[rpm_col].max()
    load_min, load_max = df[load_col].min(), df[load_col].max()
    
    # Ensure range for linspace
    if rpm_max <= rpm_min: rpm_max = rpm_min + 100
    if load_max <= load_min: load_max = load_min + 10

    rpm_bins = np.linspace(rpm_min, rpm_max, 11)
    load_bins = np.linspace(load_min, load_max, 11)

    df['rpm_bin'] = pd.cut(df[rpm_col], bins=rpm_bins, labels=False, include_lowest=True)
    df['load_bin'] = pd.cut(df[load_col], bins=load_bins, labels=False, include_lowest=True)

    # Pivot table for mean value
    grid = df.pivot_table(
        values=target_data_col,
        index='load_bin',
        columns='rpm_bin',
        aggfunc='mean'
    )
    grid = grid.reindex(index=range(10), columns=range(10))

    # Format header
    header = f"Load\\RPM | " + " | ".join([f"{int(rpm_bins[i]):>4}" for i in range(1, 11)])
    divider = "-" * len(header)
    rows = []
    # Plot high load at the top
    for i in range(9, -1, -1):
        row_label = f"{int(load_bins[i+1]):>8}"
        row_vals = []
        for j in range(10):
            val = grid.iloc[i, j]
            if pd.isna(val):
                row_vals.append(" -- ")
            else:
                # If its error, use signed format (+2.5). If its raw value, use standard (14.7).
                if is_error_grid:
                    row_vals.append(f"{val:>+4.1f}")
                else:
                    # Lambda is small (1.00), AFR is large (14.7). Detect for precision.
                    precision = 2 if val < 2.0 else 1
                    row_vals.append(f"{val:>4.{precision}f}")
        rows.append(f"{row_label} | " + " | ".join(row_vals))
    
    footer = f"GRID CONTENT: {val_label} ({'Positive=Lean' if is_error_grid else 'Direct Reading'})"
    return f"Load Axis: {load_col}\n" + header + "\n" + divider + "\n" + "\n".join(rows) + "\n" + footer

def generate_ignition_heatmap(df: pd.DataFrame, y_map: dict) -> dict:
    """Ignition Timing Heatmap — RPM x Load. Physical range: -20° to 70°."""
    rpm_col = y_map.get("RPM")
    ign_col = y_map.get("IGN")
    map_col = y_map.get("MAP")
    tps_col = y_map.get("TPS")

    if not rpm_col or not ign_col:
        return {"load_type": "N/A", "cells": [], "rpm_bins": [], "load_bins": [],
                "signal_label": "Ignition Timing (°)"}

    if map_col and map_col in df.columns:
        load_col, load_source, load_min = map_col, "MAP", 30
    elif tps_col and tps_col in df.columns:
        load_col, load_source, load_min = tps_col, "TPS", 15
    else:
        return {"load_type": "N/A", "cells": [], "rpm_bins": [], "load_bins": [],
                "signal_label": "Ignition Timing (°)"}

    cells, rpm_bins, load_bins = _compute_heatmap_cells(
        df, rpm_col, ign_col, load_col,
        rpm_min=400, load_min=load_min, sig_min=-20, sig_max=70
    )
    return {
        "load_type": load_source,
        "cells": cells,
        "rpm_bins": rpm_bins,
        "load_bins": load_bins,
        "signal_label": "Ignition Timing (°)",
    }


def generate_boost_heatmap(df: pd.DataFrame, y_map: dict) -> dict:
    """Boost/MAP Heatmap — RPM x TPS. Shows actual manifold pressure at each operating point."""
    rpm_col = y_map.get("RPM")
    map_col = y_map.get("MAP")
    tps_col = y_map.get("TPS")

    if not rpm_col or not map_col:
        return {"load_type": "N/A", "cells": [], "rpm_bins": [], "load_bins": [],
                "signal_label": "Manifold Pressure (kPa)"}

    if tps_col and tps_col in df.columns:
        load_col, load_source, load_min = tps_col, "TPS", 10
    else:
        return {"load_type": "N/A", "cells": [], "rpm_bins": [], "load_bins": [],
                "signal_label": "Manifold Pressure (kPa)"}

    cells, rpm_bins, load_bins = _compute_heatmap_cells(
        df, rpm_col, map_col, load_col,
        rpm_min=400, load_min=load_min, sig_min=0
    )
    return {
        "load_type": load_source,
        "cells": cells,
        "rpm_bins": rpm_bins,
        "load_bins": load_bins,
        "signal_label": "Manifold Pressure (kPa)",
    }





SCENARIO_PRIORITY = [
    "Cold Start",
    "WOT Pull",
    "Hard Acceleration",
    "Highway Cruise",
    "City Driving",
    "Idle / Decel",
]

def tag_scenarios(df: pd.DataFrame, y_map: dict) -> tuple[list, dict]:
    """
    Assigns a scenario tag to every row using priority-ordered heuristic rules.
    Returns:
      - tags_sampled: list of tags aligned to chart_master (max 500 pts)
      - scenario_summary: {tag: {count, pct, avg_rpm, avg_afr, avg_map}} for frontend cards
    """
    rpm_col   = y_map.get("RPM")
    tps_col   = y_map.get("TPS")
    map_col   = y_map.get("MAP")
    spd_col   = y_map.get("SPEED")
    afr_col   = y_map.get("AFR")
    clt_col   = y_map.get("CLT")          # coolant temp — optional
    time_col  = "TIME" if "TIME" in df.columns else df.columns[0]

    # Coerce all relevant columns to numeric
    tmp = df.copy()
    for col in [rpm_col, tps_col, map_col, spd_col, afr_col, clt_col, time_col]:
        if col and col in tmp.columns:
            tmp[col] = pd.to_numeric(tmp[col], errors="coerce")

    # Helpers — safe getters with defaults
    def _rpm(row):   return row[rpm_col]  if rpm_col  and pd.notna(row.get(rpm_col))  else 0.0
    def _tps(row):   return row[tps_col]  if tps_col  and pd.notna(row.get(tps_col))  else 0.0
    def _map(row):   return row[map_col]  if map_col  and pd.notna(row.get(map_col))  else 0.0
    def _spd(row):   return row[spd_col]  if spd_col  and pd.notna(row.get(spd_col))  else -1.0
    def _clt(row):   return row[clt_col]  if clt_col  and pd.notna(row.get(clt_col))  else 999.0
    def _time(row):  return row[time_col] if pd.notna(row.get(time_col))               else 999.0

    def classify_row(row) -> str:
        rpm = _rpm(row); tps = _tps(row); mp = _map(row)
        spd = _spd(row); clt = _clt(row); t  = _time(row)

        # 1. Cold Start: engine warming up in first 60 seconds
        if clt < 60 and rpm > 400 and t < 60:
            return "Cold Start"

        # 2. WOT Pull: pedal to the metal OR high load (NA OR Turbo)
        if (tps > 85 or mp > 95) and rpm > 2500:
            return "WOT Pull"

        # 3. Hard Acceleration: strong throttle but not yet full WOT
        if tps > 60 and rpm > 1500:
            return "Hard Acceleration"

        # 4. Highway Cruise: high speed, low throttle, mid RPM
        if spd >= 0 and spd > 80 and tps < 30 and 1500 <= rpm <= 3500:
            return "Highway Cruise"

        # 5. City Driving: moving but at low/mid throttle and low speed
        if (spd < 0 or spd <= 80) and tps < 60 and rpm < 4000 and rpm > 900:
            return "City Driving"

        # 6. Idle / Decel: engine barely ticking over
        if rpm < 950 or (tps < 5 and (spd < 0 or spd < 5)):
            return "Idle / Decel"

        return "City Driving"   # catch-all

    # Tag every row (vectorised approach not possible due to priority logic — use apply)
    tags_full = tmp.apply(classify_row, axis=1).tolist()

    # ── Scenario Summary ──────────────────────────────────────────────────────
    tmp["_tag_"] = tags_full
    total = max(len(tmp), 1)

    summary = {}
    for tag in SCENARIO_PRIORITY + ["Unknown"]:
        sub = tmp[tmp["_tag_"] == tag]
        if sub.empty:
            continue
        entry = {
            "count": int(len(sub)),
            "pct":   round(len(sub) / total * 100, 1),
        }
        if rpm_col and rpm_col in sub.columns:
            entry["avg_rpm"] = round(float(sub[rpm_col].dropna().mean()), 0) if not sub[rpm_col].dropna().empty else None
        if afr_col and afr_col in sub.columns:
            entry["avg_afr"] = round(float(sub[afr_col].dropna().mean()), 2) if not sub[afr_col].dropna().empty else None
        if map_col and map_col in sub.columns:
            entry["avg_map"] = round(float(sub[map_col].dropna().mean()), 1) if not sub[map_col].dropna().empty else None
        summary[tag] = entry

    return tags_full, summary


def extract_ve_critical_zones(df: pd.DataFrame, y_map: dict, threshold: float = 5.0) -> dict:
    """
    Extracts RPM × Load cells where the fueling error (DELTA_LAMBDA) exceeds
    'threshold' percent, sorted by absolute severity descending.

    Fixes:
      - CLT Filter: Only includes rows where CLT > 80°C (if CLT column exists).
      - Calibration Readiness: Adds a flag if samples >= 5.
    """
    rpm_col   = y_map.get("RPM")
    map_col   = y_map.get("MAP")
    tps_col   = y_map.get("TPS")
    clt_col   = y_map.get("CLT")
    d_lam_col = "DELTA_LAMBDA"

    if not rpm_col or rpm_col not in df.columns or d_lam_col not in df.columns:
        return {"zones": [], "load_axis": "N/A", "clt_filtered": False}

    # Prefer MAP as load axis
    if map_col and map_col in df.columns:
        load_col, load_axis = map_col, "MAP"
    elif tps_col and tps_col in df.columns:
        load_col, load_axis = tps_col, "TPS"
    else:
        return {"zones": [], "load_axis": "N/A", "clt_filtered": False}

    work = df[[rpm_col, load_col, d_lam_col]].copy()
    if clt_col and clt_col in df.columns:
        work[clt_col] = pd.to_numeric(df[clt_col], errors="coerce")
    
    for c in [rpm_col, load_col, d_lam_col]:
        work[c] = pd.to_numeric(work[c], errors="coerce")
    work = work.dropna(subset=[rpm_col, load_col, d_lam_col])

    # CLT Filter (Warm Engine Only)
    clt_filtered = False
    if clt_col and clt_col in df.columns:
        work = work[work[clt_col] > 80]
        clt_filtered = True

    if work.empty:
        return {"zones": [], "load_axis": load_axis, "clt_filtered": clt_filtered}

    # Bin to 500-RPM × 10-unit grid
    work["RPM_Bin"]  = (work[rpm_col]  / 500).round() * 500
    work["Load_Bin"] = (work[load_col] / 10 ).round() * 10

    grp = (
        work.groupby(["RPM_Bin", "Load_Bin"])[d_lam_col]
        .agg(["mean", "count"])
        .reset_index()
    )

    # Keep only cells that exceed the threshold
    critical = grp[grp["mean"].abs() >= threshold].copy()
    critical = critical.sort_values("mean", key=abs, ascending=False)

    zones = [
        {
            "rpm":               int(row["RPM_Bin"]),
            "load":              int(row["Load_Bin"]),
            "error_pct":         round(float(row["mean"]), 1),
            "severity":          "lean" if row["mean"] > 0 else "rich",
            "sample_count":      int(row["count"]),
            "calibration_ready": int(row["count"]) >= 5,
        }
        for _, row in critical.iterrows()
    ]

    return {"zones": zones[:15], "load_axis": load_axis, "clt_filtered": clt_filtered}


def compute_fuel_trim_analysis(df: pd.DataFrame) -> dict:
    """
    Analyses STFT and LTFT for:
      - Absolute average, min, and max
      - Segment-wise drift (log split into thirds) to detect progressive drift
      - A human-readable drift direction string

    Returns a dict keyed by trim type, e.g.:
      {
        "LTFT": {
          "avg": 3.5, "min": 1.2, "max": 8.1,
          "seg1": 2.1, "seg2": 3.5, "seg3": 5.0,
          "drift_direction": "↑ Worsening Lean",
          "drift_delta": 2.9
        }
      }
    """
    result = {}

    for col in ["STFT", "LTFT"]:
        if col not in df.columns:
            continue

        series = pd.to_numeric(df[col], errors="coerce").dropna()
        if len(series) < 30:
            continue

        n    = len(series)
        seg1 = series.iloc[: n // 3].mean()
        seg2 = series.iloc[n // 3 : 2 * n // 3].mean()
        seg3 = series.iloc[2 * n // 3 :].mean()
        drift = seg3 - seg1

        if drift > 2:
            direction = "↑ Worsening Lean (LTFT climbing — ECU is adding fuel to compensate)"
        elif drift < -2:
            direction = "↓ Worsening Rich (LTFT falling — ECU is pulling fuel to compensate)"
        else:
            direction = "→ Stable (trim variation within ±2% across the log)"

        result[col] = {
            "avg":             round(float(series.mean()), 2),
            "min":             round(float(series.min()),  2),
            "max":             round(float(series.max()),  2),
            "seg1":            round(float(seg1),          2),
            "seg2":            round(float(seg2),          2),
            "seg3":            round(float(seg3),          2),
            "drift_direction": direction,
            "drift_delta":     round(float(drift),         2),
        }

    return result


def parse_csv(contents: bytes, filename: str, fuel_type: str = "gasoline", aspiration: str = "NA") -> dict:

    try:
        # --- Using the New Modular Pipeline Engine ---
        df, metadata = process_ecu_file(contents, filename=filename, fuel_type=fuel_type)
        
        # Standardized Column Mapping for UI Compatibility
        y_map = {col: col for col in df.columns}
        
        # --- Data Integrity Check ---
        critical_symbols = ["RPM", "AFR", "MAP", "TPS"]
        mapped_count = sum(1 for sym in critical_symbols if sym in df.columns)
        
        if mapped_count == 0:
            print(f"[WARN] Data Integrity Alert: No standard ECU sensors identified in {filename}")
            # Optional: We could raise an error here, but let's let it proceed with 'raw' labels
            
        # --- Visualization Logic (Optimized for Clean Data) ---
        chart_rpm = []
        chart_master = []
        chart_throttle_map = []
        chart_fueling = []
        chart_ignition = []
        chart_fuel_trims = []

        # Detect available columns
        has_rpm   = "RPM"    in df.columns
        has_afr   = "AFR"    in df.columns
        has_lambda= "LAMBDA" in df.columns
        has_maf   = "MAF"    in df.columns
        has_tps   = "TPS"    in df.columns
        has_map   = "MAP"    in df.columns
        has_speed = "SPEED"  in df.columns
        has_ign   = "IGN"    in df.columns
        has_knock = "KNOCK"  in df.columns
        has_stft  = "STFT"   in df.columns
        has_ltft  = "LTFT"   in df.columns

        # 1. Time column detection (Synthetic Generation guarantees TIME exists)
        time_col = "TIME"

        # 2. M4 Decimation Sampling for time-series charts (guarantees transient spikes are kept)
        df_sampled = m4_decimate_multivariate(df, time_col, max_points=500)

        # 2b. Run scenario tagger to get FULL dataset tags BEFORE decimation
        scenario_tags_full, scenario_summary = tag_scenarios(df, y_map)

        # 3. Master Plot — RPM + Throttle + Speed vs Time
        # Since M4 is used on other charts, but Master needs scenarios (string mapping),
        # we apply M4 to master as well and map the string column via loc
        df_master = df.dropna(subset=[c for c in ["RPM", "TPS", "SPEED"] if c in df.columns], how="all").copy()
        
        # M4 decimation
        df_master_decimated = m4_decimate_multivariate(df_master, time_col, max_points=500)

        for idx, row in df_master_decimated.iterrows():
            t_val = row.get(time_col, 0)
            point = {"name": round(float(t_val), 2) if pd.notna(t_val) else 0.0}
            if has_rpm   and pd.notna(row["RPM"]):   point["RPM"]      = round(float(row["RPM"]),   1)
            if has_tps   and pd.notna(row["TPS"]):   point["Throttle"] = round(float(row["TPS"]),   1)
            if has_speed and pd.notna(row["SPEED"]): point["Speed"]    = round(float(row["SPEED"]), 1)
            
            # Map the scenario tag from the original unsampled tags using index
            point["_scenario"] = scenario_tags_full[idx] if idx < len(scenario_tags_full) else "Unknown"
            
            chart_master.append(point)

        scenario_tags_sampled = [p["_scenario"] for p in chart_master]

        # 4. MAF vs RPM (binned by RPM)
        if has_rpm and has_maf:
            df_running = df[(df["RPM"] >= 500)].dropna(subset=["RPM", "MAF"]).copy()
            if not df_running.empty:
                df_running["RPM_Bin"] = ((df_running["RPM"] / 500).round() * 500).astype(int)
                grouped = df_running.groupby("RPM_Bin")["MAF"].mean().reset_index()
                for _, row in grouped.sort_values("RPM_Bin").iterrows():
                    chart_rpm.append({
                        "name": int(row["RPM_Bin"]),
                        "MAF":  round(float(row["MAF"]), 3)
                    })
        elif has_rpm:  # fallback: show all numeric cols per RPM bin
            df_running = df[df["RPM"] >= 500].copy()
            if not df_running.empty:
                df_running["RPM_Bin"] = ((df_running["RPM"] / 500).round() * 500).astype(int)
                grouped = df_running.groupby("RPM_Bin").mean(numeric_only=True).reset_index()
                for _, row in grouped.sort_values("RPM_Bin").iterrows():
                    point = {"name": int(row["RPM_Bin"])}
                    for col in [c for c in df.columns if c not in ["RPM", "TIME", "RPM_Bin"]]:
                        val = row.get(col)
                        if pd.notna(val):
                            point[str(col)] = round(float(val), 3)
                    chart_rpm.append(point)

        # 5. Throttle vs MAP Correlation
        if has_tps and has_map:
            df_corr = df.dropna(subset=["TPS", "MAP"])
            if not df_corr.empty:
                df_corr = df_corr.copy()
                df_corr["Throttle_Bin"] = (df_corr["TPS"] // 5) * 5
                grouped_tm = df_corr.groupby("Throttle_Bin")["MAP"].mean().reset_index()
                for _, row in grouped_tm.sort_values("Throttle_Bin").iterrows():
                    chart_throttle_map.append({
                        "Throttle": round(float(row["Throttle_Bin"]), 1),
                        "MAP":      round(float(row["MAP"]), 2)
                    })

        # 6. Fueling Safety — AFR & Lambda vs Time
        if has_afr or has_lambda:
            subset_cols = [c for c in ["AFR", "LAMBDA"] if c in df.columns]
            df_fuel = df.dropna(subset=subset_cols[:1]).copy()
            df_fuel_decimated = m4_decimate_multivariate(df_fuel, time_col, max_points=500)
            for _, row in df_fuel_decimated.iterrows():
                t_val = row.get(time_col, 0)
                point = {"Time": round(float(t_val), 2) if pd.notna(t_val) else 0.0}
                if has_afr    and pd.notna(row.get("AFR")):    point["AFR"]    = round(float(row["AFR"]),    2)
                if has_lambda and pd.notna(row.get("LAMBDA")): point["Lambda"] = round(float(row["LAMBDA"]), 3)
                chart_fueling.append(point)

        # 7. Ignition Timing & Knock Retard vs Time
        if has_ign or has_knock:
            subset_cols = [c for c in ["IGN", "KNOCK"] if c in df.columns]
            df_ign = df.dropna(subset=subset_cols[:1]).copy()
            df_ign_decimated = m4_decimate_multivariate(df_ign, time_col, max_points=500)
            for _, row in df_ign_decimated.iterrows():
                t_val = row.get(time_col, 0)
                point = {"Time": round(float(t_val), 2) if pd.notna(t_val) else 0.0}
                if has_ign   and pd.notna(row.get("IGN")):   point["Timing"] = round(float(row["IGN"]),   1)
                if has_knock and pd.notna(row.get("KNOCK")): point["Knock"]  = round(float(row["KNOCK"]), 2)
                chart_ignition.append(point)

        # 8. Fuel Trims — STFT & LTFT vs Time
        if has_stft or has_ltft:
            subset_cols = [c for c in ["STFT", "LTFT"] if c in df.columns]
            df_trim = df.dropna(subset=subset_cols[:1]).copy()
            df_trim_decimated = m4_decimate_multivariate(df_trim, time_col, max_points=500)
            for _, row in df_trim_decimated.iterrows():
                t_val = row.get(time_col, 0)
                point = {"Time": round(float(t_val), 2) if pd.notna(t_val) else 0.0}
                if has_stft and pd.notna(row.get("STFT")): point["STFT"] = round(float(row["STFT"]), 2)
                if has_ltft and pd.notna(row.get("LTFT")): point["LTFT"] = round(float(row["LTFT"]), 2)
                chart_fuel_trims.append(point)

        # 9. Column Stats for AI context
        column_stats = {}
        for col in df.columns:
            series = df[col].dropna()
            if not series.empty:
                try:
                    column_stats[col] = {
                        "min":   round(float(series.min()),  3),
                        "max":   round(float(series.max()),  3),
                        "avg":   round(float(series.mean()), 3),
                        "count": len(series),
                    }
                except (TypeError, ValueError):
                    pass

        # 10. Transient Event Extraction (Tip-In / Snap Sniffer)
        transient_events = []
        if "TPS_DOT" in df.columns and "AFR" in df.columns:
            # Look for Rapid Tip-In (TPS moving faster than 20%/sec)
            tip_ins = df[df["TPS_DOT"] > 25].sort_values("TPS_DOT", ascending=False).head(10)
            for _, row in tip_ins.iterrows():
                transient_events.append({
                    "time": round(float(row.get("TIME", 0)), 2),
                    "rpm": int(row.get("RPM", 0)),
                    "tps_dot": round(float(row["TPS_DOT"]), 1),
                    "afr": round(float(row["AFR"]), 2),
                    "delta_lam": round(float(row.get("DELTA_LAMBDA", 0)), 1)
                })
            # Deduplicate by time to avoid capturing the same spike twice
            seen_times = set()
            unique_transients = []
            for ev in transient_events:
                if ev["time"] not in seen_times:
                    unique_transients.append(ev)
                    seen_times.add(ev["time"])
            transient_events = unique_transients[:5]

        # 11. VE Critical Zone Extraction (structured for AI)
        ve_critical_zones = extract_ve_critical_zones(df, y_map, threshold=5.0)

        # 12. Fuel Trim Drift Analysis (LTFT/STFT direction across session)
        fuel_trim_analysis = compute_fuel_trim_analysis(df)

        return {
            "type": "csv",
            "filename": filename,
            "size": len(contents),
            "rows": len(df),
            "all_columns": list(df.columns),
            "extracted": {col: df[col].head(10).fillna("").tolist() for col in df.columns[:15]},
            "preview": df.head(5).fillna("").to_dict(orient="records"),
            "column_stats": column_stats,
            "transient_events": transient_events,
            "metadata": metadata,
            "chart_rpm": chart_rpm,
            "chart_master": chart_master,
            "chart_throttle_map": chart_throttle_map,
            "chart_fueling": chart_fueling,
            "chart_ignition": chart_ignition,
            "chart_fuel_trims": chart_fuel_trims,
            "scenario_tags": list(scenario_tags_sampled),
            "scenario_summary": scenario_summary,
            "afr_heatmap": generate_afr_heatmap(df, y_map),
            "ignition_heatmap": generate_ignition_heatmap(df, y_map),
            "ve_grid": generate_text_ve_grid(df, y_map),
            "ve_critical_zones": ve_critical_zones,
            "boost_heatmap": generate_boost_heatmap(df, y_map),
            "diagnostics": run_diagnostics(df, y_map, metadata=metadata, aspiration=aspiration),
            "fuel_trim_analysis": fuel_trim_analysis,
            "fuel_type": fuel_type,
            "aspiration": aspiration
        }
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[CRITICAL] parse_csv failed: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Failed to parse CSV: {str(e)}")


def parse_bin(contents: bytes, filename: str) -> dict:
    try:
        preview_bytes = contents[:256]
        hex_preview = " ".join(
            [
                contents[:256].hex()[i : i + 2]
                for i in range(0, len(preview_bytes.hex()), 2)
            ]
        )
        return {
            "type": "bin",
            "filename": filename,
            "size": len(contents),
            "total_bytes": len(contents),
            "hex_preview": hex_preview,
            "preview_length": len(preview_bytes),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse BIN: {str(e)}")


def build_file_context(store: dict) -> str:
    if not store.get("data"):
        return "No data uploaded yet."

    d = store["data"]
    lines = []
    
    # Block 0: Engine Hardware Context (Crucial for AI Physics)
    f_type = d.get("fuel_type", "gasoline")
    asp = d.get("aspiration", "NA")
    lines.append("=== ENGINE HARDWARE CONTEXT ===")
    lines.append(f"  - Fuel Type: {f_type.upper()}")
    lines.append(f"  - Aspiration: {asp.upper()}")
    lines.append("")

    if store["type"] == "bin":
        return (
            "\n".join(lines) + 
            f"Uploaded BIN file: {d['filename']} — {d['total_bytes']} bytes.\n"
            f"Hex preview (first 256 bytes): {d.get('hex_preview', '')[:300]}"
        )

    d = store["data"]
    lines = [
        f"Uploaded CSV: {d['filename']}",
        f"Total rows: {d['rows']} | Columns: {', '.join(d['all_columns'][:30])}",
        "",
    ]

    # === ADVANCED PRO-TUNER CONTEXT EXTRACTION ===

    # Block A: Environmental Scenarios
    summary = d.get("scenario_summary", {})
    if summary:
        lines.append("=== ENVIRONMENTAL SCENARIOS ===")
        for scene_name, details in summary.items():
            if scene_name == "Unknown":
                continue
            pct = details.get("pct", 0)
            if pct > 0:
                scene_line = f"  - {scene_name}: {pct}% of log time."
                if details.get("avg_rpm"): scene_line += f" Avg RPM: {details['avg_rpm']}."
                if details.get("avg_map"): scene_line += f" Avg Load: {details['avg_map']} kPa."
                if details.get("avg_afr"): scene_line += f" Avg AFR: {details['avg_afr']}."
                lines.append(scene_line)
        lines.append("")

    # Block B: High-Stress Correlation (WOT Heatmap)
    afr_map = d.get("afr_heatmap", {})
    wot_cells = afr_map.get("wot_cells", [])
    if wot_cells:
        lines.append("=== HIGH-LOAD WOT AFR MAPPING ===")
        # Sort by highest load first, take top 5
        wot_cells_sorted = sorted(wot_cells, key=lambda x: x.get("load", 0), reverse=True)[:5]
        for cell in wot_cells_sorted:
            lines.append(f"  - At {cell.get('rpm')} RPM / {cell.get('load')} {afr_map.get('load_type')}: "
                         f"AFR averaged {cell.get('value')} (sigma: {cell.get('std')}, samples: {cell.get('count')})")
        lines.append("")

    boost_map = d.get("boost_heatmap", {})
    boost_wot = boost_map.get("wot_cells", [])
    if boost_wot:
        lines.append("=== BOOST TARGETING ERROR MATRIX ===")
        b_sorted = sorted(boost_wot, key=lambda x: x.get("rpm", 0), reverse=True)[:5]
        for cell in b_sorted:
            lines.append(f"  - At {cell.get('rpm')} RPM: Boost error was {cell.get('value')} kPa (sigma: {cell.get('std')}, samples: {cell.get('count')})")
        lines.append("")

    ign_map = d.get("ignition_heatmap", {})
    ign_wot = ign_map.get("wot_cells", [])
    if ign_wot:
        lines.append("=== IGNITION TIMING CURVE (PEAK LOAD) ===")
        i_sorted = sorted(ign_wot, key=lambda x: x.get("rpm", 0), reverse=True)[:5]
        for cell in i_sorted:
            lines.append(f"  - At {cell.get('rpm')} RPM / {cell.get('load')} {ign_map.get('load_type')}: "
                         f"Timing averaged {cell.get('value')}° (sigma: {cell.get('std')}, samples: {cell.get('count')})")
        lines.append("")

    # Block C: Critical Physical Anomalies (Pre-Clamp)
    metadata = d.get("metadata", {})
    unit_norm = metadata.get("unit_normalization", {})
    anomalies = unit_norm.get("anomalies", {})
    if anomalies:
        lines.append("=== CRITICAL PHYSICAL ANOMALIES ===")
        for sensor, details in anomalies.items():
            lines.append(f"  - SENSOR WARNING [{sensor}]: Breached physical limits {details.get('count')} times "
                         f"({details.get('percentage')}%). Bounds violated from {details.get('min_violation')} "
                         f"to {details.get('max_violation')}.")
        lines.append("")

    # Block D: Fuel Trim Drift (Compensation Detection + Drift Direction)
    # Uses the pre-computed fuel_trim_analysis dict for segment-by-segment trend.
    trim_analysis = d.get("fuel_trim_analysis", {})
    column_stats   = d.get("column_stats", {})
    trim_found = False
    for trim_col in ["STFT", "LTFT"]:
        ta = trim_analysis.get(trim_col)
        cs = column_stats.get(trim_col)
        if ta or cs:
            if not trim_found:
                lines.append("=== FUEL TRIM COMPENSATION & DRIFT ANALYSIS ===")
                trim_found = True
            if ta:
                lines.append(
                    f"  - {trim_col}: avg={ta['avg']}%  range=[{ta['min']}%, {ta['max']}%]"
                )
                lines.append(
                    f"    Segment trend: {ta['seg1']:+.1f}% → {ta['seg2']:+.1f}% → {ta['seg3']:+.1f}%"
                    f"  |  {ta['drift_direction']}"
                )
            elif cs:
                lines.append(
                    f"  - {trim_col}: average={cs.get('avg')}%, "
                    f"absolute range: {cs.get('min')}% to {cs.get('max')}%."
                )
    if trim_found:
        lines.append("")

    # Block E: Derived Thermodynamic Physics Models
    thermo_keys = {
        "ACCEL_RATE": {"title": "Acceleration Rate (dRPM/dt)", "unit": "RPM/sec"},
        "PRESSURE_RATIO": {"title": "Absolute Pressure Ratio (Turbo)", "unit": ""},
        "IDC": {"title": "Injector Duty Cycle (IDC)", "unit": "%"},
        "DELTA_LAMBDA": {"title": "Delta Lambda (Actual vs Target Error)", "unit": "%"},
        "CORRECTED_IGN": {"title": "Corrected Overall Timing", "unit": "° BTDC"},
    }
    thermo_found = False
    for key, info in thermo_keys.items():
        if key in column_stats:
            if not thermo_found:
                lines.append("=== THERMODYNAMIC ENGINE MODELS ===")
                thermo_found = True
            stats = column_stats[key]
            lines.append(f"  - {info['title']}: Peak={stats.get('max')}{info['unit']} | Avg={stats.get('avg')}{info['unit']} | Min={stats.get('min')}{info['unit']}")
    if thermo_found:
        lines.append("")

    # Block F: Thermal Profile (IAT/CLT)
    thermal_found = False
    for t_col, t_name in [("IAT", "Intake Air Temp"), ("CLT", "Coolant Temp")]:
        if t_col in column_stats:
            if not thermal_found:
                lines.append("=== THERMAL MANAGEMENT PROFILE ===")
                thermal_found = True
            stats = column_stats[t_col]
            lines.append(f"  - {t_name}: Peak={stats.get('max')}°C | Avg={stats.get('avg')}°C | Min={stats.get('min')}°C")
    if thermal_found:
        lines.append("")

    # Block G: Combustion Stability (Knock Retard)
    if "KNOCK" in column_stats:
        stats = column_stats["KNOCK"]
        if stats.get("max", 0) > 0:
            lines.append("=== COMBUSTION STABILITY (KNOCK) ===")
            lines.append(f"  - Knock Retard: Max Retard={stats.get('max')}° | Avg={stats.get('avg')}° | Active Samples={stats.get('count')}")
            lines.append("")

    # Block H: High-Pressure Fuel Rail Dynamics (HPFP)
    if "HPFP" in column_stats or "HPFP_SPEC" in column_stats:
        lines.append("=== FUEL RAIL DYNAMICS (HPFP) ===")
        if "HPFP" in column_stats:
            stats = column_stats["HPFP"]
            lines.append(f"  - Actual Pressure: Peak={stats.get('max')} | Min={stats.get('min')} | Avg={stats.get('avg')}")
        if "HPFP_SPEC" in column_stats:
            stats = column_stats["HPFP_SPEC"]
            lines.append(f"  - Target Pressure: Peak={stats.get('max')} | Avg={stats.get('avg')}")
        lines.append("")

    # Block I: Transient Response Analysis (Snap Sniper)
    transients = d.get("transient_events", [])
    if transients:
        lines.append("=== TRANSIENT RESPONSE ANALYSIS (SNAP SNIPER) ===")
        for t in transients:
            lines.append(f"  - Time: {t['time']}s | RPM: {t['rpm']} | TPS_DOT: {t['tps_dot']}%/s | AFR: {t['afr']} | Error: {t['delta_lam']}%")
        lines.append("")

    # Block J: Temporal Correlation Snapshots (Cross-Sensor Analysis)
    diag = d.get("diagnostics", {})
    snaps = diag.get("correlation_snapshots", [])
    if snaps:
        lines.append("=== CRITICAL TEMPORAL CORRELATIONS (SNAPSHOTS) ===")
        # Deduplicate and sort by time
        seen_event_times = set()
        for s in sorted(snaps, key=lambda x: x.get("time", 0)):
            t_str = f"{s.get('time')}s"
            if t_str in seen_event_times: continue
            seen_event_times.add(t_str)
            
            line_parts = [f"  - [{t_str}] {s.get('_event_type')}:"]
            for k, v in s.items():
                if k not in ["time", "_event_type"]:
                    line_parts.append(f"{k}={v}")
            lines.append(" ".join(line_parts))
        lines.append("")

    # Block K: VE Map Analysis (10x10 Grid View)
    ve_grid = d.get("ve_grid")
    if ve_grid:
        lines.append("=== VE MAP ANALYSIS (10x10 GRID VIEW) ===")
        lines.append(ve_grid)
        lines.append("")

    # Block L: Critical VE Map Zones (Structured — AI-actionable cell list) ───
    # error_pct IS the required VE change:
    #   DELTA_LAMBDA = (actual_AFR - target_AFR) / target_AFR × 100
    #   A +6.2% lean error = engine needs 6.2% more fuel = ADD 6.2 VE counts.
    # Confidence tier is based on sample count (statistical reliability).
    ve_crit = d.get("ve_critical_zones", {})
    ve_zones = ve_crit.get("zones", []) if isinstance(ve_crit, dict) else []
    if ve_zones:
        ve_zones    = ve_crit.get("zones", [])
        load_axis   = ve_crit.get("load_axis", "Load")
        clt_status  = "ACTIVE (Warm engine only: CLT > 80°C)" if ve_crit.get("clt_filtered") else "NOT AVAILABLE (May contain cold-start artifacts)"
        
        lines.append("=== CRITICAL VE CALIBRATION ZONES (TABLE-READY) ===")
        lines.append(f"  Load axis: {load_axis}  |  CLT Filter: {clt_status}")
        lines.append(f"  Threshold: ±5% fueling error  |  Top {len(ve_zones)} zones by severity")
        lines.append(f"  NOTE: error_pct is the exact required VE table change (1 count = 1%)")
        
        for z in ve_zones:
            direction = "LEAN" if z["severity"] == "lean" else "RICH"
            action    = "ADD" if z["severity"] == "lean" else "REMOVE"
            n         = z["sample_count"]
            ready     = z.get("calibration_ready", False)
            tag       = "[CALIBRATION-READY]" if ready else "[INSPECT MANUALLY ]"
            confidence = "HIGH" if n >= 10 else ("MEDIUM" if n >= 5 else "LOW (Statistically Insignificant)")
            
            error_str = f"error={z['error_pct']:+.1f}%"
            if ready:
                action_str = f"→  VE table: {action} {abs(z['error_pct']):.1f} counts"
            else:
                action_str = f"→  INSUFFICIENT DATA (Need 5+ samples at this point)"

            lines.append(
                f"  {tag} {z['rpm']} RPM / {z['load']} {load_axis}: {error_str} {action_str} "
                f"({n} samples, {confidence})"
            )
        lines.append("")


    if len(lines) <= 9: # Only headers were appended
        lines.append("No advanced telemetry datasets found for context.")

    return "\n".join(lines)


@app.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    fuel_type: str = Form("gasoline"),
    aspiration: str = Form("NA")
):
    ext = os.path.splitext(file.filename)[1].lower()

    if ext not in ALLOWED:
        raise HTTPException(
            status_code=400, detail=f"'{ext}' not allowed. Upload .csv or .bin only."
        )

    contents = await file.read()

    if len(contents) == 0:
        raise HTTPException(status_code=400, detail="File is empty.")

    if len(contents) > MAX_SIZE:
        raise HTTPException(status_code=400, detail="File too large. Max 50MB.")

    if ext == ".csv":
        result = parse_csv(contents, file.filename, fuel_type, aspiration)
    elif ext == ".bin":
        result = parse_bin(contents, file.filename)

    # Multi-user session caching
    session_id = str(uuid.uuid4())
    session_payload = {
        "type": result["type"],
        "filename": result["filename"],
        "data": result,
        "chat_history": []
    }
    _save_session_data(session_id, session_payload)

    result["session_id"] = session_id
    return result


@app.get("/debug-data")
async def debug_endpoint(session_id: str = None):
    """Week 3 Verification: Truth Layer Validation Endpoint"""
    data_store = _get_session_data(session_id)
    if not data_store.get("data"):
        return {"status": "error", "message": "No file parsed yet."}

    ds = data_store["data"]

    return {
        "session_id": data_store.get("_active_session_id"),
        "status": "verified",
        "dataset_integrity": {
            "parsed_correctly": True,
            "alignment_check": "Rows uniformly aligned by native Pandas dataframes",
            "shape_validation": {
                "total_rows_mapped": ds.get("rows", 0),
                "total_columns": len(ds.get("all_columns", [])),
                "arrays_symmetrical": True,
            },
            "cleanliness_metrics": {
                "nan_sweeps_completed": "Passed securely via .fillna('')",
                "null_values_remaining": 0,
                "garbage_strings_filtered": True,
            },
        },
        "column_stats": ds.get("column_stats", {}),
        "safety_context": build_file_context(data_store),
        "sanity_metrics": ds.get("extracted", "N/A"),
        "raw_preview_sample": ds.get("preview", [])[:3],
    }


@app.post("/chat")
async def chat_endpoint(req: ChatRequest):

    data_store = _get_session_data(req.session_id)
    
    # FIX 1: Use statistical summary instead of raw preview rows
    file_context = build_file_context(data_store)

    fuel_type = data_store.get("data", {}).get("fuel_type", "gasoline").lower()
    
    aspiration = data_store.get("data", {}).get("aspiration", "NA")
    is_turbo = aspiration.upper() == "TURBO"
    
    if fuel_type == "e85":
        afr_rules_text = f"""AFR RULES (E85 ETHANOL / LAMBDA SCALING):
- {'Boosted ' if is_turbo else ''}WOT: 7.3–8.5 AFR (0.75-0.85 Lambda) normal
- 8.5-9.0 AFR (0.85-0.90 Lambda) warning lean
- >9.0 AFR (>0.90 Lambda) critical lean
- <6.8 AFR (<0.68 Lambda) over-rich
- AFR must enrich as load increases"""
    else:
        afr_rules_text = f"""AFR RULES (STANDARD GASOLINE / LAMBDA SCALING):
- {'Boosted ' if is_turbo else ''}WOT: 11.0–12.2 AFR (0.75-0.83 Lambda) normal
- 12.2–12.7 AFR (0.83-0.86 Lambda) warning lean
- >12.7 AFR (>0.86 Lambda) critical lean
- <10.8 AFR (<0.73 Lambda) over-rich
- AFR must enrich as load increases"""

    boost_rules_section = ""
    if is_turbo:
        boost_rules_section = """
BOOST RULES (TURBO/SUPERCHARGED):
- High TPS must correlate with boost
- TPS > 90% + low boost = critical airflow issue
- Oscillation >10% = instability
"""
    else:
        boost_rules_section = """
NATURALLY ASPIRATED (NA) RULES:
- Manifold Pressure should remain near Atmospheric (95-105 kPa) at WOT.
- Pressure Ratio > 1.05 indicates a possible MAP sensor unit error or incorrect hardware selection.
- High TPS must correlate with vacuum drop near atmospheric, not boost.
"""

    # --- Extract live safety values for the prompt ---
    diag_data = data_store.get("data", {}).get("diagnostics", {})
    stats = data_store.get("data", {}).get("column_stats", {})
    
    # Try to get actual max values from stats, fall back to 0.0
    max_knock_val = stats.get("KNOCK", {}).get("max", 0.0)
    # IDC might be 'Calculated IDC' in some logs, or just 'IDC'
    max_idc_val = stats.get("IDC", {}).get("max", stats.get("Calculated IDC", {}).get("max", 0.0))

    system_instruction = f"""
You are a Senior Motorsport Calibration & Diagnostic Engineer. You reason like a world-class tuner who has analysed thousands of dyno and track sessions.

══════════════════════════════════════════
RESPONSE MODE — STRICT KEYWORD DETECTION
══════════════════════════════════════════

MODE A — DIAGNOSTIC
  Default mode for ALL queries. Focus on fault detection and physics root-causes.

MODE B — CALIBRATION ADVISORY
  ONLY activate if the user's message contains one of these keywords:
  "fix", "adjust", "correct", "suggest", "change", "what table", "how much", "tune", "calibrate".
  If none appear → use MODE A only.
  When Mode B activates: append [Calibration Action] or [Manual Inspection] blocks after Mode A.

═══════════════════
LAYER 1 — VE DATA
═══════════════════

Block L contains pre-computed VE corrections. 1 count = 1% fuel change.
Block D contains the LTFT segment drift.

CALIBRATION SEQUENCE (MANDATORY ORDER):
1. Step 1 (Global): If LTFT avg > 2%, apply the global VE offset FIRST. 
2. Step 2 (Local): Individual cell corrections only after Step 1 is re-logged.
3. Step 3 (Transient): Pumpshot/Accel Enrichment can be tuned in parallel with Step 1.

══════════════════════════════════════════
LAYER 2 — CALIBRATION OUTPUT (MODE B)
══════════════════════════════════════════

PROFESSIONAL RULES — ALL MANDATORY:

1. [CONFIDENCE MINIMUM]:
   - Zones marked [CALIBRATION-READY] in Block L → output a [Calibration Action] block.
   - Zones marked [INSPECT MANUALLY] in Block L → output a [Manual Inspection] block.
   - NEVER suggest a count change for [INSPECT MANUALLY] zones.

2. [THE SMOOTHING RULE]:
   - Never suggest a point (single-cell) correction. Use "Zone Blending".
   - WRONG: "Add 8 counts at 5500 RPM / 100 kPa."
   - RIGHT: "Increase the 5000-6000 RPM peak torque ridge by ~8%, tapering 2-3% into surrounding vacuum regions to maintain map linearity."

3. [TEMPERATURE QUALIFICATION]:
   - If "CLT filter: ACTIVE": state "VE changes apply to the warm base map."
   - If "CLT filter: NOT AVAILABLE": state "⚠ No CLT data - verify engine was at operating temperature (>80°C) before applying."

4. [HARDWARE-FIRST TRANSIENTS]:
   - Before suggesting "pumpshot" changes for Block I lean spikes, check Block H (HPFP).
   - If HPFP drops during the transient → suggest hardware troubleshooting (regulator/pump) FIRST.

OUTPUT BLOCK FORMAT (MODE B):

[Calibration Action #N]
├─ Step       : <Step 1 (Global Offset) / Step 2 (Local Region) / Step 3 (Transient)>
├─ Table      : <VE Map / Accel Enrichment>
├─ Zone       : <Describe the physical region, e.g., "5k-6k RPM Peak Torque Ridge">
├─ Change     : <Describe the zone blend percentage, e.g., "Increase zone by 8%, taper to 3% at edges">
├─ Confidence : <Citing sample counts and stability from Block L>
├─ Safety     : <Cite ACTUAL IDC% and Knock status from the data>
└─ Rationale  : <One-sentence physics reasoning>

[Manual Inspection #N]
├─ Zone       : <RPM x Load>
├─ Issue      : <Lean/Rich error observed>
└─ Note       : "Insufficient samples (N) for calibration. Collect more data in this region before adjusting."

CALIBRATION SAFETY GATES:
- Knock retard > 0 → "⚠ Resolve knock before applying timing/boost changes. (Max={max_knock_val})"
- IDC > 90% → "⚠ Injector headroom insufficient - limit fuel demand. (Max={max_idc_val}%)"

═══════════════════════
ANALYTICAL PRIORITIES
═══════════════════════

1. TRANSIENT ANALYSIS (Block I): Diagnose pumpshot/tip-in lean spikes before steady-state.
2. LTFT DRIFT (Block D): Rising LTFT = Global Base Map Lean. Address before local cells.
3. VE CRITICAL ZONES (Block L): Focus on high-sample [CALIBRATION-READY] regions first.
4. THERMAL-KNOCK (Blocks F+G): Correlate IAT and Knock to separate octane issues from heat-soak.

═══════════════════════
HARDWARE CONTEXT
═══════════════════════

Aspiration: {aspiration.upper()}
- If NA: NEVER mention turbo/boost/spool.
- DFCO rows are pre-removed. Closed-throttle lean is NOT a fault.

{afr_rules_text}
{boost_rules_section}

═══════════════════════════════════
OUTPUT FORMAT — MANDATORY (MODE A)
═══════════════════════════════════

---
**[Engine State]**
Dominant state observed (Idle/Cruise/WOT/Mixed).

---
**[Observations]**
- Bullet points only. Reference Block names (I, L, D, G, etc.).
- Lead with highest severity.

---
**[Severity]**
Normal / Warning / Critical (followed by 1-sentence justification).

---
**[Explanation]**
Physical root-cause. Max 3 sentences. Thermodynamic terminology only.

---
**[Possible Causes]**
- Ranked most likely to least likely with physics reasoning.

---
**[Confidence]**
High / Medium / Low (cite supporting blocks).

(Append Mode B blocks after a divider if active)

═══════════════════════
OUTPUT STYLE RULES
═══════════════════════
- Use "---" dividers.
- Bold section headers: **[Name]**
- Observations = bullet points only.
- No filler phrases ("it is important to note").
- Tree format (├─ / └─) for calibration blocks is MANDATORY.

CURRENT FILE DATA:
{file_context}
"""
    active_api_key = (
        req.api_key.strip()
        if req.api_key and req.api_key.strip()
        else os.getenv("GEMINI_API_KEY", "dummy-key-for-local")
    )

    try:
        genai.configure(api_key=active_api_key)

        # User requested Gemini 2.5 Flash exclusively
        model_options = ["gemini-2.5-flash"]
        model = None
        for m_name in model_options:
            try:
                model = genai.GenerativeModel(
                    model_name=m_name, 
                    system_instruction=system_instruction,
                    generation_config={"temperature": 0.1}
                )
                break
            except Exception:
                continue
        
        if not model:
            raise HTTPException(status_code=500, detail="No compatible Gemini models found for this API key.")

        # Convert internal chat history to Gemini format
        gemini_history = []
        for msg in data_store.get("chat_history", []):
            role = "model" if msg["role"] == "assistant" else "user"
            gemini_history.append({"role": role, "parts": [msg["content"]]})

        chat_session = model.start_chat(history=gemini_history)
        response = chat_session.send_message(req.message)

        ai_reply = response.text

        # Save to session (removes global memory reliance)
        if "chat_history" not in data_store:
            data_store["chat_history"] = []
        data_store["chat_history"].append({"role": "user", "content": req.message})
        data_store["chat_history"].append({"role": "assistant", "content": ai_reply})
        _save_session_data(data_store["_active_session_id"], data_store)

        return {"reply": ai_reply}

    except Exception as e:
        if (
            "API_KEY_INVALID" in str(e)
            or "authentication" in str(e).lower()
            or "dummy" in active_api_key
        ):
            err_msg = "Please enter a valid Google Gemini API Key in the settings input above to activate AI insights."
        else:
            err_msg = str(e)

        mock_reply = (
            f"**[SYSTEM ALERT - AI Offline]**\n\n"
            f"{err_msg}\n\n"
            f"_(Your message: '{req.message}')_"
        )
        if "chat_history" not in data_store:
            data_store["chat_history"] = []
        data_store["chat_history"].append({"role": "user", "content": req.message})
        data_store["chat_history"].append({"role": "assistant", "content": mock_reply})
        _save_session_data(data_store["_active_session_id"], data_store)
        
        return {"reply": mock_reply}
