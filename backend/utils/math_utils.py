import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)

# Stoichiometric ratios per fuel type.
# Defined here (not imported from unit_utils) to keep this module dependency-free.
STOICH_RATIOS = {
    "gasoline": 14.7,
    "e85":       9.8,
    "diesel":   14.5,
}


def apply_physics_derivations(df: pd.DataFrame, fuel_type: str = "gasoline") -> pd.DataFrame:
    """
    Thermodynamic Math Engine — V2
    Calculates derived physical constants using native Pandas vectorization.

    Derived Channels:
      ACCEL_RATE     — dRPM/dt (software dyno proxy)
      TPS_DOT        — dTPS/dt (snap/tip-in detection)
      PRESSURE_RATIO — MAP / Ambient (turbo efficiency)
      IDC            — Injector Duty Cycle
      ALIGNED_AFR    — O2 transport-delay compensated AFR (shift -3 samples)
      SAFETY_AFR_FLOOR — Per-row dynamic lean safety limit (scales with boost)
      DELTA_LAMBDA   — % fueling error vs. target (uses ALIGNED_AFR when available)
      CORRECTED_IGN  — Base timing minus active knock retard
    """
    logger.info(f"[ENGINE] Applying thermodynamic derivations under {fuel_type.upper()} assumptions...")

    df = df.copy()
    stoich = STOICH_RATIOS.get(fuel_type.lower(), 14.7)

    # ── 1. Acceleration Rate (dRPM/dt) ────────────────────────────────────────
    # Positive = pulling / accelerating. Negative = lifting / shifting / braking.
    if "RPM" in df.columns and "TIME" in df.columns:
        dt   = df["TIME"].diff().replace(0, np.nan)
        drpm = df["RPM"].diff()
        df["ACCEL_RATE"] = (drpm / dt).fillna(0).round(1)
        # Rolling mean to eliminate digital sensor quantisation noise
        df["ACCEL_RATE"] = (
            df["ACCEL_RATE"]
            .rolling(window=3, center=True, min_periods=1)
            .mean()
            .round(1)
        )

    # ── 1b. Throttle Change Rate (TPS_DOT) ───────────────────────────────────
    # High-resolution: NO smoothing so raw snap events are preserved.
    if "TPS" in df.columns and "TIME" in df.columns:
        dt   = df["TIME"].diff().replace(0, np.nan)
        dtps = df["TPS"].diff()
        df["TPS_DOT"] = (dtps / dt).fillna(0).round(1)

    # ── 2. Pressure Ratio ─────────────────────────────────────────────────────
    # PR = MAP_absolute / Ambient. Uses BARO if logged, otherwise sea-level std.
    if "MAP" in df.columns:
        ambient  = df["BARO"] if "BARO" in df.columns else 101.3
        safe_map = df["MAP"].clip(lower=1.0)
        df["PRESSURE_RATIO"] = (safe_map / ambient).round(2).clip(lower=0.1)

    # ── 3. Injector Duty Cycle (IDC) ──────────────────────────────────────────
    # IDC % = (PW_ms × RPM) / 1200  — standard sequential 4-stroke formula.
    if "RPM" in df.columns and "PULSE_WIDTH" in df.columns:
        df["IDC"] = ((df["PULSE_WIDTH"] * df["RPM"]) / 1200).round(1).clip(lower=0.0)

    # ── 4. O2 Transport Delay Compensation (ALIGNED_AFR) ──────────────────────
    # Wideband sensors physically measure exhaust gas arriving from combustion
    # events that occurred ~80–150 ms earlier.  At a typical 10–20 Hz log rate,
    # shifting the AFR trace forward by 3 samples (~100–150 ms) re-aligns the
    # fueling feedback with the MAP/TPS event that caused it.
    #
    # Effect: eliminates "ghost lean spikes" during rapid tip-ins, where raw AFR
    # appears lean simply because the O2 is still reading the previous (richer)
    # mixture.  ALIGNED_AFR is used ONLY for internal diagnostics; the raw AFR
    # channel is left untouched for charting.
    if "AFR" in df.columns:
        TRANSPORT_SHIFT = 3   # configurable; valid for ~10–20 Hz logs
        df["ALIGNED_AFR"] = (
            df["AFR"]
            .shift(-TRANSPORT_SHIFT)
            .ffill()           # forward-fill the trailing NaNs created by shift
        )

    # ── 5. Dynamic Safety AFR Floor (SAFETY_AFR_FLOOR) ───────────────────────
    # Replaces the flat "12.7 = critical lean" rule with a per-row safety limit
    # that accounts for the fact that richer mixtures are required at higher
    # cylinder pressures to suppress detonation.
    #
    # Formula:
    #   base  = stoich × 0.83          (nominal WOT safety target at atmospheric)
    #   floor = base − (overpressure_kPa / 10) × 0.05
    #   clip  = [stoich×0.75, stoich×0.90]   (absolute physical bounds)
    #
    # Example (gasoline, 1.5 bar boost ≈ 252 kPa MAP):
    #   base  = 14.7 × 0.83 = 12.20
    #   delta = (252 − 101.3) / 10 × 0.05 = 0.75
    #   floor = 12.20 − 0.75 = 11.45   (vs. the flat 12.7 — correctly richer)
    if "MAP" in df.columns:
        base_afr       = stoich * 0.83
        overpressure   = (df["MAP"] - 101.3).clip(lower=0)
        df["SAFETY_AFR_FLOOR"] = (
            base_afr - (overpressure / 10.0) * 0.05
        ).clip(
            lower=stoich * 0.75,
            upper=stoich * 0.90,
        ).round(2)

    # ── 6. Fueling Error — DELTA_LAMBDA ──────────────────────────────────────
    # Error % = (Actual − Target) / Target × 100
    #   Positive = lean relative to target.  Negative = rich.
    #
    # Unit-matching logic:
    #   TARGET_LAMBDA (lambda scale 0.75–1.35) → pair with raw LAMBDA column.
    #   TARGET_AFR    (AFR scale 10–20)        → pair with ALIGNED_AFR (preferred)
    #                                             or raw AFR as fallback.
    actual_val = None
    target_val = None

    if "TARGET_LAMBDA" in df.columns:
        target_val = df["TARGET_LAMBDA"]
        # Must stay in lambda scale to avoid unit mismatch
        if "LAMBDA" in df.columns:
            actual_val = df["LAMBDA"]
        # If no LAMBDA column, skip (ALIGNED_AFR is AFR-scale — incompatible)

    elif "TARGET_AFR" in df.columns:
        target_val = df["TARGET_AFR"]
        # Prefer transport-delay-compensated signal
        if "ALIGNED_AFR" in df.columns:
            actual_val = df["ALIGNED_AFR"]
        elif "AFR" in df.columns:
            actual_val = df["AFR"]

    if actual_val is not None and target_val is not None:
        valid_target = target_val.replace(0, np.nan)
        df["DELTA_LAMBDA"] = (
            ((actual_val - valid_target) / valid_target) * 100
        ).round(1).clip(lower=-50.0, upper=50.0)

    # ── 7. Corrected Ignition Timing ─────────────────────────────────────────
    # Net timing = base advance minus ECU knock retard (MBT proxy).
    if "IGN" in df.columns and "KNOCK" in df.columns:
        df["CORRECTED_IGN"] = (df["IGN"] - df["KNOCK"]).round(1)

    return df
