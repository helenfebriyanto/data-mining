import pandas as pd
from typing import Any

def normalize_percentage(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if "percentage" in df.columns:
        df["percentage"] = pd.to_numeric(df["percentage"], errors="coerce")
        if df["percentage"].max(skipna=True) <= 1.0:
            df["percentage"] = df["percentage"] * 100
    return df


def pct(value: Any, decimals: int = 2) -> str:
    try:
        value_float = float(value)
    except Exception:
        return "—"
    return f"{value_float * 100:.{decimals}f}%"


def pct_from_percent(value: Any, decimals: int = 2) -> str:
    try:
        value_float = float(value)
    except Exception:
        return "—"
    return f"{value_float:.{decimals}f}%"


def num(value: Any) -> str:
    try:
        return f"{int(round(float(value))):,}"
    except Exception:
        return "—"


def small_num(value: Any, decimals: int = 2) -> str:
    try:
        value_float = float(value)
    except Exception:
        return "—"
    return f"{value_float:,.{decimals}f}"