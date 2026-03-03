"""
services/schema_service.py
───────────────────────────
Analyses a DataFrame and returns a rich SchemaReport.
Detects column types, nulls, uniqueness, potential keys, and join candidates.
"""

from __future__ import annotations
import re
import uuid
from typing import List

import numpy as np
import pandas as pd

from models.schemas import ColumnProfile, JoinSuggestion, SchemaReport


# ── Heuristics ─────────────────────────────────────────────────────────────────

_ID_PATTERN = re.compile(r"(^id$|_id$|^id_|_key$|_code$)", re.IGNORECASE)


def _is_pk_candidate(col: str, series: pd.Series) -> bool:
    """High uniqueness + ID-like name → probable primary key."""
    uniqueness = series.nunique() / max(len(series), 1)
    return uniqueness > 0.95 and bool(_ID_PATTERN.search(col))


def _detect_datetime(series: pd.Series) -> bool:
    """Try parsing a sample as datetime."""
    sample = series.dropna().head(50).astype(str)
    try:
        pd.to_datetime(sample, infer_datetime_format=True, errors="raise")
        return True
    except Exception:
        return False


def _sample_values(series: pd.Series, n: int = 5) -> list:
    vals = series.dropna().unique()[:n]
    return [v.item() if hasattr(v, "item") else v for v in vals]


# ── Main builder ────────────────────────────────────────────────────────────────

def build_schema_report(
    df: pd.DataFrame,
    filename: str,
    file_id: str | None = None,
) -> SchemaReport:
    if file_id is None:
        file_id = str(uuid.uuid4())

    cols: List[ColumnProfile] = []
    for col in df.columns:
        s = df[col]
        null_count = int(s.isna().sum())
        null_pct = round(null_count / len(s) * 100, 2) if len(s) else 0.0
        unique_count = int(s.nunique(dropna=True))
        is_numeric = pd.api.types.is_numeric_dtype(s)
        is_dt = False if is_numeric else _detect_datetime(s)
        is_cat = (
            not is_numeric
            and not is_dt
            and unique_count < max(50, len(s) * 0.05)
        )

        cols.append(
            ColumnProfile(
                name=col,
                dtype=str(s.dtype),
                null_count=null_count,
                null_pct=null_pct,
                unique_count=unique_count,
                sample_values=_sample_values(s),
                is_numeric=is_numeric,
                is_datetime=is_dt,
                is_categorical=is_cat,
                suggested_pk=_is_pk_candidate(col, s),
            )
        )

    dup_count = int(df.duplicated().sum())
    dup_pct = round(dup_count / len(df) * 100, 2) if len(df) else 0.0

    return SchemaReport(
        file_id=file_id,
        filename=filename,
        row_count=len(df),
        col_count=len(df.columns),
        columns=cols,
        duplicate_row_count=dup_count,
        duplicate_row_pct=dup_pct,
        memory_mb=round(df.memory_usage(deep=True).sum() / 1e6, 3),
    )


# ── Join suggestion ─────────────────────────────────────────────────────────────

def suggest_joins(
    schemas: List[SchemaReport],
) -> List[JoinSuggestion]:
    """
    Compare every pair of schemas.
    A join is suggested when two columns share the same name
    (or both match the ID pattern) and have compatible uniqueness.
    """
    suggestions: List[JoinSuggestion] = []

    for i in range(len(schemas)):
        for j in range(i + 1, len(schemas)):
            left, right = schemas[i], schemas[j]
            left_cols = {c.name: c for c in left.columns}
            right_cols = {c.name: c for c in right.columns}

            for col_name, lc in left_cols.items():
                if col_name in right_cols:
                    rc = right_cols[col_name]
                    # Confidence: both high-uniqueness + id-like → 0.95
                    # Same name + numeric → 0.80
                    # Same name only → 0.60
                    conf = 0.60
                    if lc.suggested_pk or rc.suggested_pk:
                        conf = 0.90
                    if lc.is_numeric and rc.is_numeric:
                        conf = max(conf, 0.80)

                    suggestions.append(
                        JoinSuggestion(
                            left_file=left.filename,
                            right_file=right.filename,
                            left_col=col_name,
                            right_col=col_name,
                            confidence=conf,
                        )
                    )

    # Deduplicate, keep highest confidence per pair
    seen: dict = {}
    for s in suggestions:
        key = (s.left_file, s.right_file, s.left_col, s.right_col)
        if key not in seen or seen[key].confidence < s.confidence:
            seen[key] = s

    return sorted(seen.values(), key=lambda x: -x.confidence)
