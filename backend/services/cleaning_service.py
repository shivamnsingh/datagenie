"""
services/cleaning_service.py
─────────────────────────────
The core cleaning engine.

Two-phase design:
  1. preview(config) → CleaningSummaryPreview   (no mutation)
  2. apply(config)   → CleaningResult           (mutates a copy)

Each cleaning step is isolated and logged for the audit trail.
"""

from __future__ import annotations

import uuid
from typing import List, Tuple

import numpy as np
import pandas as pd
from scipy import stats

from models.schemas import (
    CleaningConfig,
    CleaningResult,
    CleaningStep,
    CleaningSummaryPreview,
    DtypeConfig,
    NullConfig,
    OutlierConfig,
    StandardizationConfig,
)
from utils.session_store import store


# ══════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════

def _quality_score(df: pd.DataFrame) -> float:
    """
    Simple 0-100 completeness + consistency score.
      • Completeness  (60 pts): 1 - avg null pct
      • Uniqueness    (20 pts): no full-duplicate rows
      • Type sanity   (20 pts): no object cols that look numeric
    """
    if df.empty:
        return 0.0

    total_cells = df.size
    null_cells = df.isna().sum().sum()
    completeness = 60 * (1 - null_cells / total_cells)

    dup_pct = df.duplicated().sum() / len(df)
    uniqueness = 20 * (1 - dup_pct)

    # Penalise object columns that parse as numeric
    obj_cols = df.select_dtypes(include="object").columns
    bad = 0
    for c in obj_cols:
        converted = pd.to_numeric(df[c], errors="coerce")
        if converted.notna().mean() > 0.8:
            bad += 1
    type_score = 20 * max(0, 1 - bad / max(len(obj_cols), 1))

    return round(completeness + uniqueness + type_score, 1)


def _iqr_bounds(series: pd.Series) -> Tuple[float, float]:
    q1 = series.quantile(0.25)
    q3 = series.quantile(0.75)
    iqr = q3 - q1
    return q1 - 1.5 * iqr, q3 + 1.5 * iqr


# ══════════════════════════════════════════════════════════════════
# STEP EXECUTORS  (each returns (df_modified, CleaningStep))
# ══════════════════════════════════════════════════════════════════

def _apply_null(df: pd.DataFrame, cfg: NullConfig) -> Tuple[pd.DataFrame, CleaningStep]:
    col = cfg.column
    if col not in df.columns:
        return df, CleaningStep(
            step="null_handling", column=col,
            action="skipped – column not found", rows_affected=0,
        )

    before_nulls = int(df[col].isna().sum())
    if before_nulls == 0:
        return df, CleaningStep(
            step="null_handling", column=col,
            action="skipped – no nulls", rows_affected=0,
        )

    rows_before = len(df)

    if cfg.strategy == "drop_rows":
        df = df.dropna(subset=[col])
        affected = rows_before - len(df)
        action = "dropped rows"

    elif cfg.strategy == "drop_column":
        df = df.drop(columns=[col])
        affected = before_nulls
        action = "dropped column"

    elif cfg.strategy == "fill_mean":
    # ✅ Add this: convert to numeric first
        numeric_col = pd.to_numeric(df[col], errors="coerce")
        val = numeric_col.mean()
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(round(val, 4))
        affected = before_nulls
        action = f"filled with mean ({round(val, 4)})"

    elif cfg.strategy == "fill_median":
        # ✅ Add this: convert to numeric first
        numeric_col = pd.to_numeric(df[col], errors="coerce")
        val = numeric_col.median()
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(round(val, 4))
        affected = before_nulls
        action = f"filled with median ({round(val, 4)})"

    elif cfg.strategy == "fill_mode":
        val = df[col].mode()
        fill = val.iloc[0] if not val.empty else None
        df[col] = df[col].fillna(fill)
        affected = before_nulls
        action = f"filled with mode ({fill})"

    elif cfg.strategy == "fill_forward":
        df[col] = df[col].ffill()
        affected = before_nulls - int(df[col].isna().sum())
        action = "forward filled"

    elif cfg.strategy == "fill_backward":
        df[col] = df[col].bfill()
        affected = before_nulls - int(df[col].isna().sum())
        action = "backward filled"

    elif cfg.strategy == "fill_custom":
        df[col] = df[col].fillna(cfg.custom_value)
        affected = before_nulls
        action = f"filled with custom value ({cfg.custom_value!r})"

    else:
        action = "unknown strategy – skipped"
        affected = 0

    return df, CleaningStep(
        step="null_handling",
        column=col,
        action=action,
        rows_affected=affected,
        detail=f"{before_nulls} nulls resolved",
    )


def _apply_outlier(
    df: pd.DataFrame, cfg: OutlierConfig
) -> Tuple[pd.DataFrame, CleaningStep]:
    col = cfg.column
    if col not in df.columns or not pd.api.types.is_numeric_dtype(df[col]):
        return df, CleaningStep(
            step="outlier_handling", column=col,
            action="skipped – not numeric or not found", rows_affected=0,
        )

    rows_before = len(df)

    if cfg.strategy == "remove_iqr":
        lo, hi = _iqr_bounds(df[col].dropna())
        mask = (df[col] >= lo) & (df[col] <= hi) | df[col].isna()
        df = df[mask]
        affected = rows_before - len(df)
        action = f"removed IQR outliers (bounds: {lo:.2f} – {hi:.2f})"

    elif cfg.strategy == "cap_percentile":
        lo = df[col].quantile(cfg.lower_percentile / 100)
        hi = df[col].quantile(cfg.upper_percentile / 100)
        df[col] = df[col].clip(lower=lo, upper=hi)
        affected = int(((df[col] == lo) | (df[col] == hi)).sum())
        action = (
            f"capped at {cfg.lower_percentile}–{cfg.upper_percentile} percentile "
            f"({lo:.2f} – {hi:.2f})"
        )

    else:  # keep
        return df, CleaningStep(
            step="outlier_handling", column=col,
            action="kept unchanged", rows_affected=0,
        )

    return df, CleaningStep(
        step="outlier_handling",
        column=col,
        action=action,
        rows_affected=affected,
    )


def _apply_dtype(
    df: pd.DataFrame, cfg: DtypeConfig
) -> Tuple[pd.DataFrame, CleaningStep]:
    col = cfg.column
    if col not in df.columns:
        return df, CleaningStep(
            step="dtype_conversion", column=col,
            action="skipped – column not found", rows_affected=0,
        )

    original_dtype = str(df[col].dtype)
    affected = len(df[col].dropna())

    try:
        if cfg.strategy == "to_numeric":
            df[col] = pd.to_numeric(df[col], errors="coerce")
            action = f"converted to numeric (was {original_dtype})"

        elif cfg.strategy == "to_datetime":
            df[col] = pd.to_datetime(
                df[col],
                format=cfg.datetime_format,
                infer_datetime_format=True,
                errors="coerce",
            )
            action = f"converted to datetime (was {original_dtype})"

        elif cfg.strategy == "to_category":
            df[col] = df[col].astype("category")
            action = f"converted to category (was {original_dtype})"

        else:
            action = "left unchanged"
            affected = 0

    except Exception as e:
        action = f"conversion failed: {e}"
        affected = 0

    return df, CleaningStep(
        step="dtype_conversion",
        column=col,
        action=action,
        rows_affected=affected,
    )


def _apply_standardization(
    df: pd.DataFrame, cfg: StandardizationConfig
) -> Tuple[pd.DataFrame, List[CleaningStep]]:
    steps: List[CleaningStep] = []

    if cfg.lowercase_columns:
        df.columns = [c.lower() for c in df.columns]
        steps.append(CleaningStep(
            step="standardization", column=None,
            action="lowercased all column names", rows_affected=len(df.columns),
        ))

    if cfg.replace_spaces_with_underscore:
        df.columns = [c.replace(" ", "_") for c in df.columns]
        steps.append(CleaningStep(
            step="standardization", column=None,
            action="replaced spaces with underscores in column names",
            rows_affected=len(df.columns),
        ))

    if cfg.trim_whitespace:
        obj_cols = df.select_dtypes(include="object").columns
        for col in obj_cols:
            df[col] = df[col].str.strip()
        steps.append(CleaningStep(
            step="standardization", column=None,
            action=f"trimmed whitespace in {len(obj_cols)} string columns",
            rows_affected=len(obj_cols),
        ))

    if cfg.drop_constant_columns:
        before = list(df.columns)
        const_cols = [c for c in df.columns if df[c].nunique(dropna=False) <= 1]
        df = df.drop(columns=const_cols)
        steps.append(CleaningStep(
            step="standardization", column=None,
            action=f"dropped {len(const_cols)} constant columns: {const_cols}",
            rows_affected=len(const_cols),
        ))

    if cfg.drop_duplicates:
        before = len(df)
        df = df.drop_duplicates()
        dropped = before - len(df)
        steps.append(CleaningStep(
            step="standardization", column=None,
            action=f"dropped {dropped} duplicate rows",
            rows_affected=dropped,
        ))

    return df, steps


# ══════════════════════════════════════════════════════════════════
# PUBLIC API
# ══════════════════════════════════════════════════════════════════

def preview_cleaning(config: CleaningConfig) -> CleaningSummaryPreview:
    """
    Dry-run: estimate what the cleaning will do WITHOUT mutating the dataframe.
    """
    df = store.load(config.file_id)
    if df is None:
        raise ValueError(f"File ID {config.file_id!r} not found in session store.")

    rows_before = len(df)
    steps: List[CleaningStep] = []
    warnings: List[str] = []

    estimated_drop = 0

    # Null steps
    for nc in config.null_configs:
        if nc.column in df.columns:
            nulls = int(df[nc.column].isna().sum())
            if nc.strategy == "drop_rows":
                estimated_drop += nulls
                steps.append(CleaningStep(
                    step="null_handling", column=nc.column,
                    action=f"will drop {nulls} rows (nulls in '{nc.column}')",
                    rows_affected=nulls,
                ))
            else:
                steps.append(CleaningStep(
                    step="null_handling", column=nc.column,
                    action=f"will {nc.strategy} for {nulls} nulls",
                    rows_affected=nulls,
                ))

    # Outlier steps
    for oc in config.outlier_configs:
        if oc.column in df.columns and pd.api.types.is_numeric_dtype(df[oc.column]):
            if oc.strategy == "remove_iqr":
                lo, hi = _iqr_bounds(df[oc.column].dropna())
                outlier_rows = int(((df[oc.column] < lo) | (df[oc.column] > hi)).sum())
                estimated_drop += outlier_rows
                steps.append(CleaningStep(
                    step="outlier_handling", column=oc.column,
                    action=f"will remove {outlier_rows} IQR outliers",
                    rows_affected=outlier_rows,
                ))
            elif oc.strategy == "cap_percentile":
                steps.append(CleaningStep(
                    step="outlier_handling", column=oc.column,
                    action=f"will cap at {oc.lower_percentile}–{oc.upper_percentile} percentile",
                    rows_affected=0,
                ))

    # Dtype steps
    for dc in config.dtype_configs:
        if dc.column in df.columns:
            steps.append(CleaningStep(
                step="dtype_conversion", column=dc.column,
                action=f"will convert '{dc.column}' → {dc.strategy}",
                rows_affected=int(df[dc.column].notna().sum()),
            ))

    # Standardization steps (estimated)
    std = config.standardization
    if std.drop_duplicates:
        dup_drop = int(df.duplicated().sum())
        estimated_drop += dup_drop
        steps.append(CleaningStep(
            step="standardization", column=None,
            action=f"will drop {dup_drop} duplicate rows",
            rows_affected=dup_drop,
        ))

    # Estimated rows after
    rows_after = max(0, rows_before - estimated_drop)
    pct_dropped = round((estimated_drop / rows_before) * 100, 2) if rows_before else 0.0

    if pct_dropped > 10:
        warnings.append(
            f"⚠️ Estimated {pct_dropped:.1f}% of rows will be removed. "
            "Consider using fill strategies instead of drop_rows."
        )
    if pct_dropped > 30:
        warnings.append(
            "🚨 More than 30% of rows will be dropped. "
            "This will significantly reduce your dataset. Please review."
        )

    return CleaningSummaryPreview(
        file_id=config.file_id,
        steps=steps,
        rows_before=rows_before,
        rows_after_estimate=rows_after,
        pct_rows_dropped_estimate=pct_dropped,
        warnings=warnings,
    )


def apply_cleaning(config: CleaningConfig) -> CleaningResult:
    """
    Apply all cleaning steps to a COPY of the dataframe.
    Saves the cleaned copy under a new file_id.
    """
    df = store.load(config.file_id)
    if df is None:
        raise ValueError(f"File ID {config.file_id!r} not found in session store.")

    rows_before = len(df)
    cols_before = len(df.columns)
    quality_before = _quality_score(df)
    all_steps: List[CleaningStep] = []
    warnings: List[str] = []

    # 1. Standardization (column names first — other steps reference them)
    df, std_steps = _apply_standardization(df, config.standardization)
    all_steps.extend(std_steps)

    # Remap config column names if we lowercased
    if config.standardization.lowercase_columns:
        for nc in config.null_configs:
            nc.column = nc.column.lower().replace(" ", "_")
        for oc in config.outlier_configs:
            oc.column = oc.column.lower().replace(" ", "_")
        for dc in config.dtype_configs:
            dc.column = dc.column.lower().replace(" ", "_")

    # 2. Dtype conversion (before null filling so means are correct type)
    for dc in config.dtype_configs:
        df, step = _apply_dtype(df, dc)
        all_steps.append(step)

    # 3. Null handling
    for nc in config.null_configs:
        df, step = _apply_null(df, nc)
        all_steps.append(step)

    # 4. Outlier handling
    for oc in config.outlier_configs:
        df, step = _apply_outlier(df, oc)
        all_steps.append(step)

    rows_after = len(df)
    cols_after = len(df.columns)
    quality_after = _quality_score(df)

    pct_dropped = round((rows_before - rows_after) / rows_before * 100, 2) if rows_before else 0.0
    if pct_dropped > 10:
        warnings.append(f"⚠️ {pct_dropped:.1f}% of rows were removed during cleaning.")

    # Save under new ID
    clean_file_id = str(uuid.uuid4())
    store.save(clean_file_id, df)

    return CleaningResult(
        original_file_id=config.file_id,
        clean_file_id=clean_file_id,
        rows_before=rows_before,
        rows_after=rows_after,
        cols_before=cols_before,
        cols_after=cols_after,
        steps_applied=all_steps,
        quality_score_before=quality_before,
        quality_score_after=quality_after,
        warnings=warnings,
    )
