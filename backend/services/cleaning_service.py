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

import gc
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
    CleaningReport,
    ColumnAnalysis,
)
from utils.session_store import store
from services.schema_service import _sample_values


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

    if len(df) > 100_000:
        sample = df.head(1_000)
        total_cells = max(sample.size, 1)
        null_cells = int(sample.isna().sum().sum())
        dup_pct = sample.duplicated().sum() / len(sample)
        obj_cols = sample.select_dtypes(include="object").columns
    else:
        total_cells = df.size
        null_cells = df.isna().sum().sum()
        dup_pct = df.duplicated().sum() / len(df)
        obj_cols = df.select_dtypes(include="object").columns

    completeness = 60 * (1 - null_cells / total_cells)
    uniqueness = 20 * (1 - dup_pct)

    # Penalise object columns that parse as numeric
    bad = 0
    for c in obj_cols:
        converted = pd.to_numeric(sample[c] if len(df) > 100_000 else df[c], errors="coerce")
        if converted.notna().mean() > 0.8:
            bad += 1
    type_score = 20 * max(0, 1 - bad / max(len(obj_cols), 1))

    return round(completeness + uniqueness + type_score, 1)


def _infer_semantic_type(series: pd.Series) -> str:
    s = series.dropna()
    if s.empty:
        return "text"

    # numeric
    if pd.api.types.is_numeric_dtype(series):
        return "numeric"

    # datetime
    try:
        parsed = pd.to_datetime(s.head(50), errors="coerce")
        if parsed.notna().mean() > 0.8:
            return "date"
    except Exception:
        pass

    # email
    if s.astype(str).str.contains(r"^[^@\s]+@[^@\s]+\.[^@\s]+$").mean() > 0.8:
        return "email"

    # currency (contains $ or numeric with 2 decimals)
    if s.astype(str).str.contains(r"^\$?\d+[\.,]?\d{0,2}").mean() > 0.8:
        return "currency"

    # id-like
    if s.astype(str).str.match(r"^[A-Za-z0-9_\-]{6,}$").mean() > 0.9:
        return "id"

    # categorical if low cardinality
    non_null = len(s)
    uniques = s.nunique()
    if non_null > 0 and (uniques / non_null) < 0.05:
        return "category"

    return "text"


def _column_profile(series: pd.Series) -> ColumnAnalysis:
    name = series.name
    dtype = str(series.dtype)
    non_null = series.notna().sum()
    null_count = int(series.isna().sum())
    null_pct = round(null_count / max(len(series), 1) * 100, 2)
    unique_count = int(series.nunique(dropna=True))
    cardinality = round(unique_count / max(non_null, 1), 4)
    inferred = _infer_semantic_type(series)
    sample_values = _sample_values(series)

    # outlier detection for numeric
    has_outliers = None
    outlier_count = None
    if pd.api.types.is_numeric_dtype(series):
        vals = series.dropna()
        if len(vals) >= 5:
            lo, hi = _iqr_bounds(vals)
            mask = (series < lo) | (series > hi)
            outlier_count = int(mask.sum())
            has_outliers = outlier_count > 0

    mem = int(series.memory_usage(deep=True))

    return ColumnAnalysis(
        name=name,
        dtype=dtype,
        null_count=null_count,
        null_pct=null_pct,
        unique_count=unique_count,
        cardinality=cardinality,
        inferred_semantic=inferred,
        sample_values=sample_values,
        has_outliers=has_outliers,
        outlier_count=outlier_count,
        memory_bytes=mem,
    )


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
        const_cols = df.columns[df.nunique(dropna=False) <= 1].tolist()
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
    df = store.load(config.file_id, copy=False)
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
        if len(df) > 100_000:
            dup_sample = df.head(100)
            dup_ratio = float(dup_sample.duplicated().sum() / max(len(dup_sample), 1)) if len(dup_sample) else 0.0
            dup_drop = int(round(dup_ratio * len(df)))
        else:
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

    # Additional profiling and cleaning-report generation (non-breaking)
    # Trim whitespace and normalize case if requested
    if config.standardization.trim_whitespace:
        for col in df.select_dtypes(include=["object"]).columns:
            df[col] = df[col].astype(str).str.strip()

    if config.standardization.lowercase_columns:
        for col in df.select_dtypes(include=["object"]).columns:
            df[col] = df[col].apply(lambda v: v.lower() if isinstance(v, str) else v)

    # Memory optimization: downcast numeric columns
    for col in df.select_dtypes(include=["number"]).columns:
        try:
            df[col] = pd.to_numeric(df[col], downcast="integer")
            df[col] = pd.to_numeric(df[col], downcast="float")
        except Exception:
            pass

    # Build CleaningReport and attach to warnings via store (non-breaking)
    columns_analysis = [_column_profile(df[c]) for c in df.columns]
    dup_count = int(df.duplicated().sum())
    missing_values = int(df.isna().sum().sum())
    quality_after = _quality_score(df)
    memory_mb = round(df.memory_usage(deep=False).sum() / 1e6, 3)

    from datetime import datetime

    # Save under new ID early so dataset_service can reference it
    clean_file_id = str(uuid.uuid4())
    store.save(clean_file_id, df)

    cleaning_report = CleaningReport(
        file_id=clean_file_id,
        filename=str(config.file_id),
        row_count=len(df),
        col_count=len(df.columns),
        quality_score=quality_after,
        memory_mb=memory_mb,
        duplicates=dup_count,
        duplicate_pct=round(dup_count / max(len(df), 1) * 100, 2),
        missing_values=missing_values,
        missing_pct=round(missing_values / max(df.size, 1) * 100, 2),
        columns=columns_analysis,
        generated_at=datetime.utcnow().isoformat() + "Z",
    )

    # Persist report to .data/reports/{file_id}.json for caching
    try:
        import json
        from pathlib import Path
        rpt_dir = Path('.data')
        rpt_dir.mkdir(exist_ok=True)
        with (rpt_dir / f"cleaning_report_{clean_file_id}.json").open('w', encoding='utf-8') as f:
            json.dump(json.loads(cleaning_report.json()), f, indent=2)
    except Exception:
        pass

    # Generate dataset understanding (cached) for downstream features
    try:
        from services.dataset_service import generate_dataset_understanding
        try:
            generate_dataset_understanding(store.load(clean_file_id, copy=False), str(config.file_id), clean_file_id)
        except Exception:
            pass
    except Exception:
        pass

    rows_after = len(df)
    cols_after = len(df.columns)
    quality_after = _quality_score(df)

    pct_dropped = round((rows_before - rows_after) / rows_before * 100, 2) if rows_before else 0.0
    if pct_dropped > 10:
        warnings.append(f"⚠️ {pct_dropped:.1f}% of rows were removed during cleaning.")

    # df already saved earlier to store as clean_file_id
    del df
    gc.collect()

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
