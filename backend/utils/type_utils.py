import pandas as pd

# Minimum fraction of non-null values that must parse as numeric
# for a column to be converted. Below this threshold the column is
# kept as-is (object/string dtype) so categorical columns like
# "scenario", "Scenario", "tag", etc. are not silently destroyed.
_NUMERIC_THRESHOLD = 0.5


def coerce_numeric(df: pd.DataFrame) -> pd.DataFrame:
    """
    Selective numeric coercion for ECU telemetry.

    Algorithm:
      1. Strip whitespace from all headers and string values.
      2. For each column, probe how many non-null values parse as numeric.
         - If >= _NUMERIC_THRESHOLD fraction: coerce the whole column.
         - Otherwise:           keep the column as object (string) dtype.

    This prevents categorical / label columns (e.g. "scenario", "Scenario",
    "tag", "Label", "Filename") from being silently converted to all-NaN
    float64 Series, which caused the downstream
    "Invalid value … dtype: float64 … for dtype 'str'" crash.
    """
    print("[INFO] Normalizing whitespace and coercing numeric types...")

    # 1. Deep Whitespace Normalization (Headers & Values)
    df.columns = [c.strip() for c in df.columns]
    df = df.map(lambda x: x.strip() if isinstance(x, str) else x)

    # 2. Selective Coercion Loop
    # Iterate by *position* (iloc) to handle duplicate column names safely —
    # df[col] returns a DataFrame when duplicates exist, crashing pd.to_numeric.
    coerced_series = {}
    for i in range(len(df.columns)):
        col_name = df.columns[i]
        raw = df.iloc[:, i]

        # Probe: try converting to numeric, count how many succeeded
        probed = pd.to_numeric(raw, errors="coerce")
        non_null_total = raw.notna().sum()

        if non_null_total == 0:
            # Entirely empty column — keep as numeric (all NaN) for compatibility
            coerced_series[i] = probed
        else:
            numeric_ratio = probed.notna().sum() / non_null_total
            if numeric_ratio >= _NUMERIC_THRESHOLD:
                coerced_series[i] = probed
                if numeric_ratio < 1.0:
                    print(
                        f"[INFO] Coerced '{col_name}' to numeric "
                        f"({numeric_ratio:.0%} parseable, rest → NaN)"
                    )
            else:
                # Predominantly text / categorical — preserve as-is
                coerced_series[i] = raw
                print(
                    f"[INFO] Kept '{col_name}' as string dtype "
                    f"(only {numeric_ratio:.0%} numeric values)"
                )

    new_df = pd.DataFrame(coerced_series)
    new_df.columns = df.columns
    return new_df
