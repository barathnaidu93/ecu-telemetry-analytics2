"""
Commercial-Grade Unit Normalization Engine - V2
================================================
Standardizes MAP, AFR, and TPS to high-fidelity physical standards (kPa, AFR, %).

Key principles:
  - Multi-signal unit detection (median + max + physical range scoring)
  - Anomaly detection and logging BEFORE clamping
  - Numeric confidence scoring (0.0-1.0)
  - Original unit stats preserved in df.attrs for traceability
  - Normalization flag prevents double-processing (idempotency)
  - Configurable fuel type for stoichiometric ratio (defaults to gasoline)
"""

import pandas as pd
import numpy as np
import logging
from typing import Dict, Tuple, Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Physical Constants
# ---------------------------------------------------------------------------
STOICH_RATIOS = {
    "gasoline": 14.7,
    "e85":      9.8,
    "diesel":   14.5,
}

# Post-normalization physical clamp ranges
CLAMP_RANGES = {
    "MAP": (0, 400),    # kPa — vacuum to extreme forced induction
    "AFR": (8, 25),     # AFR — rich misfire floor to lean cut ceiling
    "TPS": (0, 100),    # Percentage
}


# ---------------------------------------------------------------------------
# Detection Functions (Multi-Signal Scoring)
# ---------------------------------------------------------------------------

def _detect_map_unit(series: pd.Series) -> Tuple[str, float]:
    """
    Determines MAP unit using weighted multi-signal scoring.
    Combines median, maximum, and minimum heuristics to handle:
      - Low-boost / NA engines
      - Idle-heavy logs
      - Already-normalized data

    Returns: (detected_unit, confidence 0.0–1.0)
    """
    median_val = series.median()
    max_val = series.max()
    min_val = series.min()

    scores = {"kPa": 0.0, "BAR": 0.0, "PSI": 0.0}

    # --- Median heuristic (Weight: 3) ---
    # kPa: atmospheric ~101, boosted ~150-350, NA idle ~30-100
    if 20 < median_val < 300:
        scores["kPa"] += 3.0
    # BAR: atmospheric ~1.0, boosted ~1.5-3.5, idle ~0.3-0.9
    if 0.2 < median_val < 4.5:
        scores["BAR"] += 3.0
    # PSI: atmospheric ~14.7, boosted ~20-50, idle ~5-14
    if 3 < median_val < 60:
        scores["PSI"] += 3.0

    # --- Maximum value heuristic (Weight: 2) ---
    # Validates the ceiling matches the unit's physical limits
    if max_val < 500 and max_val > 10:
        scores["kPa"] += 2.0
    if max_val < 6.0 and max_val > 0.3:
        scores["BAR"] += 2.0
    if max_val < 80 and max_val > 3:
        scores["PSI"] += 2.0

    # --- Minimum value heuristic (Weight: 1) ---
    # Atmospheric floor reference for sensors that read absolute pressure
    if min_val >= 0 and min_val < 120:
        scores["kPa"] += 1.0
    if min_val >= 0 and min_val < 1.5:
        scores["BAR"] += 1.0
    if min_val >= 0 and min_val < 18:
        scores["PSI"] += 1.0

    # --- Disambiguation: resolve ties using physical precision ---
    # BAR and PSI overlap in the 3-4.5 range. Use max to disambiguate:
    # If max < 6 it's almost certainly BAR, not PSI (PSI boosted logs go >20)
    if scores["BAR"] == scores["PSI"] and max_val < 6.0:
        scores["BAR"] += 0.5
    if scores["BAR"] == scores["PSI"] and max_val > 15.0:
        scores["PSI"] += 0.5

    # kPa vs PSI overlap in 20-60 range. Use median to disambiguate:
    # kPa atmospheric median ~50-110, PSI atmospheric median ~10-15
    if scores["kPa"] == scores["PSI"]:
        if median_val > 40:
            scores["kPa"] += 0.5
        else:
            scores["PSI"] += 0.5

    best_unit = max(scores, key=scores.get)
    max_possible = 6.0  # 3 + 2 + 1
    confidence = round(min(scores[best_unit] / max_possible, 1.0), 2)

    return best_unit, confidence


def _detect_afr_unit(series: pd.Series) -> Tuple[str, float]:
    """
    Determines if AFR data is in AFR scale or Lambda scale.

    Returns: (detected_unit, confidence 0.0–1.0)
    """
    median_val = series.median()
    max_val = series.max()
    min_val = series.min()

    # Lambda: stoich = 1.0, typical range 0.65–1.35
    # AFR:    stoich = 14.7, typical range 10–20

    if max_val < 2.5 and 0.5 < median_val < 1.5:
        # Almost certainly Lambda
        confidence = 0.95 if (0.7 < median_val < 1.3) else 0.7
        return "Lambda", round(confidence, 2)

    if median_val > 8 and max_val > 9:
        # Already AFR scale
        confidence = 0.95 if (10 < median_val < 18) else 0.7
        return "AFR", round(confidence, 2)

    # Ambiguous
    return "Unknown", 0.2


def _detect_tps_unit(series: pd.Series) -> Tuple[str, float]:
    """
    Determines TPS unit handling three common sensor outputs:
      - 0–1 fractional scale
      - 0–5V voltage signal
      - 0–100% already scaled

    Returns: (detected_unit, confidence 0.0–1.0)
    """
    max_val = series.max()
    min_val = series.min()
    median_val = series.median()

    # 0–1 fractional: max near 1.0, values clustered 0–1
    if max_val <= 1.1 and max_val > 0.05 and min_val >= -0.05:
        confidence = 0.95 if max_val <= 1.02 else 0.8
        return "0-1_fraction", round(confidence, 2)

    # 0–5V voltage: max between 1.1 and 5.5, typical idle ~0.5-1V
    if 1.1 < max_val <= 5.5 and min_val >= -0.1 and median_val < 3.5:
        confidence = 0.85 if max_val <= 5.2 else 0.65
        return "voltage_0-5V", round(confidence, 2)

    # Already 0–100%: max between 5.5 and 105
    if 5.5 < max_val <= 105 and min_val >= -1:
        confidence = 0.95 if max_val <= 101 else 0.75
        return "percent", round(confidence, 2)

    return "Unknown", 0.2


# ---------------------------------------------------------------------------
# Anomaly Detection (Pre-Clamp)
# ---------------------------------------------------------------------------

def _detect_anomalies(series: pd.Series, signal_name: str,
                      low: float, high: float) -> Dict[str, Any]:
    """
    Identifies values outside the expected physical range BEFORE clamping.
    Returns anomaly summary dict (empty if no anomalies).
    """
    outlier_mask = (series < low) | (series > high)
    count = int(outlier_mask.sum())

    if count == 0:
        return {}

    outlier_values = series[outlier_mask]
    anomaly_info = {
        "count": count,
        "percentage": round(count / len(series) * 100, 2),
        "min_violation": round(float(outlier_values.min()), 4),
        "max_violation": round(float(outlier_values.max()), 4),
    }

    logger.warning(
        f"[UnitNorm] {signal_name}: {count} values ({anomaly_info['percentage']}%) "
        f"outside [{low}, {high}] — "
        f"range [{anomaly_info['min_violation']}, {anomaly_info['max_violation']}]"
    )

    return anomaly_info


# ---------------------------------------------------------------------------
# Pre-Conversion Stats Capture
# ---------------------------------------------------------------------------

def _capture_original_stats(series: pd.Series) -> Dict[str, float]:
    """Snapshot of signal statistics before any conversion."""
    return {
        "min": round(float(series.min()), 4),
        "max": round(float(series.max()), 4),
        "median": round(float(series.median()), 4),
        "mean": round(float(series.mean()), 4),
    }


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------

def normalize_units(df: pd.DataFrame,
                    fuel_type: str = "gasoline") -> pd.DataFrame:
    """
    Production-grade unit normalization for ECU telemetry.

    Standardizes:
      - MAP -> kPa
      - AFR -> AFR scale (gasoline stoich 14.7)
      - TPS -> 0-100%

    Stores in df.attrs:
      - unit_info:          {signal: "conversion description"}
      - unit_confidence:    {signal: 0.0-1.0}
      - original_units:     {signal: {"unit": str, "stats": {...}}}
      - anomalies_detected: {signal: {count, percentage, min/max_violation}}
      - _units_normalized:  True (idempotency flag)

    Args:
        df: DataFrame with standardized column names (post-mapping)
        fuel_type: Fuel type for stoichiometric ratio ("gasoline", "e85", "diesel")

    Returns:
        DataFrame with normalized units and traceability metadata in attrs
    """
    if df.empty:
        return df

    # --- Idempotency Guard ---
    if df.attrs.get("_units_normalized", False):
        logger.info("[UnitNorm] Data already normalized. Skipping re-processing.")
        return df

    stoich = STOICH_RATIOS.get(fuel_type, 14.7)

    unit_info = {}
    unit_confidence = {}
    original_units = {}
    anomalies_detected = {}

    # ===================================================================
    # 1. MAP (Manifold Absolute Pressure) -> Standard: kPa
    # ===================================================================
    if "MAP" in df.columns:
        m_data = pd.to_numeric(df["MAP"], errors="coerce")
        valid_mask = m_data.notna()

        if valid_mask.sum() > 0:
            m_valid = m_data[valid_mask]

            # Capture pre-conversion state
            detected_unit, confidence = _detect_map_unit(m_valid)
            pre_stats = _capture_original_stats(m_valid)
            original_units["MAP"] = {"unit": detected_unit, "stats": pre_stats}

            if detected_unit == "kPa":
                logger.info(
                    f"[UnitNorm] MAP: Already kPa (confidence={confidence}). "
                    f"Median={pre_stats['median']}"
                )
                unit_info["MAP"] = "kPa (no conversion)"
            elif detected_unit == "BAR":
                logger.info(
                    f"[UnitNorm] MAP: BAR -> kPa (*100) "
                    f"(confidence={confidence}, median={pre_stats['median']})"
                )
                df["MAP"] = m_data * 100
                unit_info["MAP"] = "BAR -> kPa"
            elif detected_unit == "PSI":
                logger.info(
                    f"[UnitNorm] MAP: PSI -> kPa (*6.89476) "
                    f"(confidence={confidence}, median={pre_stats['median']})"
                )
                df["MAP"] = m_data * 6.89476
                unit_info["MAP"] = "PSI -> kPa"
            else:
                logger.warning(
                    f"[UnitNorm] MAP: Unit unknown (confidence={confidence}). "
                    f"No conversion applied. Stats: {pre_stats}"
                )
                unit_info["MAP"] = "Unknown (skipped)"

            unit_confidence["MAP"] = confidence

            # Anomaly detection THEN clamping.
            # dropna() is used (not fillna(0)): NaN = sensor dropout, not a range violation.
            low, high = CLAMP_RANGES["MAP"]
            anomaly = _detect_anomalies(
                pd.to_numeric(df["MAP"], errors="coerce").dropna(),
                "MAP", low, high
            )
            if anomaly:
                anomalies_detected["MAP"] = anomaly
            df["MAP"] = pd.to_numeric(df["MAP"], errors="coerce").clip(low, high)

    # ===================================================================
    # 2. AFR (Air-Fuel Ratio) -> Standard: AFR scale
    # ===================================================================
    if "AFR" in df.columns:
        a_data = pd.to_numeric(df["AFR"], errors="coerce")
        valid_mask = a_data.notna()

        if valid_mask.sum() > 0:
            a_valid = a_data[valid_mask]

            detected_unit, confidence = _detect_afr_unit(a_valid)
            pre_stats = _capture_original_stats(a_valid)
            original_units["AFR"] = {"unit": detected_unit, "stats": pre_stats}

            if detected_unit == "AFR":
                logger.info(
                    f"[UnitNorm] AFR: Already AFR scale (confidence={confidence}). "
                    f"Median={pre_stats['median']}"
                )
                unit_info["AFR"] = "AFR (no conversion)"
            elif detected_unit == "Lambda":
                logger.info(
                    f"[UnitNorm] AFR: Lambda -> AFR (*{stoich}, fuel={fuel_type}) "
                    f"(confidence={confidence}, median={pre_stats['median']})"
                )
                df["AFR"] = a_data * stoich
                unit_info["AFR"] = f"Lambda -> AFR ({stoich}x, {fuel_type})"
            else:
                logger.warning(
                    f"[UnitNorm] AFR: Unit unknown (confidence={confidence}). "
                    f"No conversion applied. Stats: {pre_stats}"
                )
                unit_info["AFR"] = "Unknown (skipped)"

            unit_confidence["AFR"] = confidence

            # Anomaly detection THEN clamping.
            # dropna() is used: AFR NaNs filled with 0 would incorrectly register
            # as sub-8.0 violations on every sensor dropout.
            low, high = CLAMP_RANGES["AFR"]
            anomaly = _detect_anomalies(
                pd.to_numeric(df["AFR"], errors="coerce").dropna(),
                "AFR", low, high
            )
            if anomaly:
                anomalies_detected["AFR"] = anomaly
            df["AFR"] = pd.to_numeric(df["AFR"], errors="coerce").clip(low, high)

    # ===================================================================
    # 3. TPS (Throttle Position) -> Standard: 0-100%
    # ===================================================================
    if "TPS" in df.columns:
        t_data = pd.to_numeric(df["TPS"], errors="coerce")
        valid_mask = t_data.notna()

        if valid_mask.sum() > 0:
            t_valid = t_data[valid_mask]

            detected_unit, confidence = _detect_tps_unit(t_valid)
            pre_stats = _capture_original_stats(t_valid)
            original_units["TPS"] = {"unit": detected_unit, "stats": pre_stats}

            if detected_unit == "percent":
                logger.info(
                    f"[UnitNorm] TPS: Already 0-100% (confidence={confidence}). "
                    f"Max={pre_stats['max']}"
                )
                unit_info["TPS"] = "0-100% (no conversion)"
            elif detected_unit == "0-1_fraction":
                logger.info(
                    f"[UnitNorm] TPS: 0-1 fraction -> 0-100% (*100) "
                    f"(confidence={confidence}, max={pre_stats['max']})"
                )
                df["TPS"] = t_data * 100
                unit_info["TPS"] = "0-1 -> 0-100%"
            elif detected_unit == "voltage_0-5V":
                logger.info(
                    f"[UnitNorm] TPS: 0-5V -> 0-100% (/5 *100) "
                    f"(confidence={confidence}, max={pre_stats['max']})"
                )
                df["TPS"] = (t_data / 5.0) * 100
                unit_info["TPS"] = "0-5V -> 0-100%"
            else:
                logger.warning(
                    f"[UnitNorm] TPS: Unit unknown (confidence={confidence}). "
                    f"No conversion applied. Stats: {pre_stats}"
                )
                unit_info["TPS"] = "Unknown (skipped)"

            unit_confidence["TPS"] = confidence

            # Anomaly detection THEN clamping.
            # dropna() is used: TPS NaNs filled with 0 are within range (0, 100)
            # so they would silently suppress anomaly detection.
            low, high = CLAMP_RANGES["TPS"]
            anomaly = _detect_anomalies(
                pd.to_numeric(df["TPS"], errors="coerce").dropna(),
                "TPS", low, high
            )
            if anomaly:
                anomalies_detected["TPS"] = anomaly
            df["TPS"] = pd.to_numeric(df["TPS"], errors="coerce").clip(low, high)

    # ===================================================================
    # Attach Traceability Metadata
    # ===================================================================
    df.attrs["unit_info"] = unit_info
    df.attrs["unit_confidence"] = unit_confidence
    df.attrs["original_units"] = original_units
    df.attrs["anomalies_detected"] = anomalies_detected
    df.attrs["fuel_type"] = fuel_type
    df.attrs["_units_normalized"] = True

    logger.info(
        f"[UnitNorm] Normalization complete. "
        f"Signals processed: {list(unit_info.keys())} | "
        f"Anomalies flagged: {list(anomalies_detected.keys())}"
    )

    return df
