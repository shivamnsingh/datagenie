"""
routers/clean.py
─────────────────
POST /api/clean/preview  — dry-run, returns what WILL happen (for user confirmation)
POST /api/clean/apply    — apply cleaning, returns CleaningResult + new file_id
GET  /api/clean/outliers/{file_id}  — per-column outlier statistics
GET  /api/clean/nulls/{file_id}     — null statistics per column
"""

from __future__ import annotations

import pandas as pd
from fastapi import APIRouter, HTTPException

from models.schemas import CleaningConfig, CleaningResult, CleaningSummaryPreview
from services.cleaning_service import apply_cleaning, preview_cleaning, _iqr_bounds
from utils.session_store import store

router = APIRouter()


# ── Preview (dry-run) ──────────────────────────────────────────────────────────

@router.post("/preview", response_model=CleaningSummaryPreview)
def cleaning_preview(config: CleaningConfig):
    """
    Returns a summary of what WILL happen without applying changes.
    The frontend shows this to the user for confirmation.
    """
    try:
        return preview_cleaning(config)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── Apply ──────────────────────────────────────────────────────────────────────

@router.post("/apply", response_model=CleaningResult)
def cleaning_apply(config: CleaningConfig):
    """
    Apply the cleaning config to the dataset.
    Returns the new clean_file_id and full audit log.
    """
    try:
        return apply_cleaning(config)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cleaning failed: {e}")


# ── Null statistics ────────────────────────────────────────────────────────────

@router.get("/nulls/{file_id}")
def null_report(file_id: str):
    """
    Returns per-column null statistics.
    Used to populate the cleaning UI choices.
    """
    df = store.load(file_id)
    if df is None:
        raise HTTPException(status_code=404, detail=f"File ID '{file_id}' not found.")

    report = []
    for col in df.columns:
        null_count = int(df[col].isna().sum())
        report.append({
            "column": col,
            "dtype": str(df[col].dtype),
            "null_count": null_count,
            "null_pct": round(null_count / len(df) * 100, 2),
            "has_nulls": null_count > 0,
        })

    return {
        "file_id": file_id,
        "total_rows": len(df),
        "columns_with_nulls": sum(1 for r in report if r["has_nulls"]),
        "report": report,
    }


# ── Outlier statistics ─────────────────────────────────────────────────────────

@router.get("/outliers/{file_id}")
def outlier_report(file_id: str):
    """
    Returns IQR-based outlier counts for every numeric column.
    """
    df = store.load(file_id)
    if df is None:
        raise HTTPException(status_code=404, detail=f"File ID '{file_id}' not found.")

    numeric_cols = df.select_dtypes(include="number").columns
    report = []

    for col in numeric_cols:
        s = df[col].dropna()
        lo, hi = _iqr_bounds(s)
        outlier_mask = (df[col] < lo) | (df[col] > hi)
        outlier_count = int(outlier_mask.sum())

        report.append({
            "column": col,
            "outlier_count": outlier_count,
            "outlier_pct": round(outlier_count / len(df) * 100, 2),
            "iqr_lower_bound": round(lo, 4),
            "iqr_upper_bound": round(hi, 4),
            "min": round(float(s.min()), 4),
            "max": round(float(s.max()), 4),
            "mean": round(float(s.mean()), 4),
            "median": round(float(s.median()), 4),
            "has_outliers": outlier_count > 0,
        })

    return {
        "file_id": file_id,
        "numeric_columns": len(numeric_cols),
        "columns_with_outliers": sum(1 for r in report if r["has_outliers"]),
        "report": report,
    }


# ── Duplicate statistics ───────────────────────────────────────────────────────

@router.get("/duplicates/{file_id}")
def duplicate_report(file_id: str):
    """Returns duplicate row count and sample duplicate rows."""
    df = store.load(file_id)
    if df is None:
        raise HTTPException(status_code=404, detail=f"File ID '{file_id}' not found.")

    dup_mask = df.duplicated(keep=False)
    dup_count = int(df.duplicated().sum())
    sample = df[dup_mask].head(5).where(pd.notnull(df[dup_mask].head(5)), None)

    return {
        "file_id": file_id,
        "total_rows": len(df),
        "duplicate_rows": dup_count,
        "duplicate_pct": round(dup_count / len(df) * 100, 2),
        "sample_duplicates": sample.to_dict(orient="records"),
    }
