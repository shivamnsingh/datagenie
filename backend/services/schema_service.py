"""
services/schema_service.py
───────────────────────────
Analyses a DataFrame and returns a rich SchemaReport.
Detects column types, nulls, uniqueness, potential keys, and join candidates.
"""

from __future__ import annotations
from datetime import datetime
import re
import uuid
from typing import List

import numpy as np
import pandas as pd

from models.schemas import ColumnProfile, JoinSuggestion, SchemaReport


# ── Heuristics ─────────────────────────────────────────────────────────────────

_ID_PATTERN = re.compile(r"(^id$|_id$|^id_|_key$|_code$)", re.IGNORECASE)

# Keep schema inference bounded even on wide or tall uploads.
_SCHEMA_SAMPLE_SIZE = 100
_LARGE_DATASET_THRESHOLD = 100_000

# Sample only a small slice of each column so schema inference stays fast on uploads.
_DATETIME_SAMPLE_SIZE = 50

# Require most sampled values to parse before we call a column datetime.
_DATETIME_SUCCESS_THRESHOLD = 0.80

# Explicit formats keep parsing deterministic and avoid pandas' format inference warning.
_DATETIME_FORMATS = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%d-%m-%Y",
    "%m/%d/%Y",
    "%d/%m/%Y",
    "%d %b %Y",
    "%d %B %Y",
    "%Y-%m-%d %H:%M:%S",
    "%Y/%m/%d %H:%M:%S",
)


def _sample_non_null(series: pd.Series, limit: int = _SCHEMA_SAMPLE_SIZE) -> pd.Series:
    sample = series.head(limit)
    sample = sample[sample.notna()]
    if len(sample) <= limit:
        return sample
    return sample.head(limit)


def _estimate_unique_count(series: pd.Series) -> int:
    total_count = len(series)
    if total_count == 0:
        return 0

    if total_count <= _LARGE_DATASET_THRESHOLD:
        return int(series.nunique(dropna=True))

    sample = series.head(_SCHEMA_SAMPLE_SIZE)
    sample_non_null = sample[sample.notna()]
    if sample_non_null.empty:
        return 0

    sample_unique = int(sample_non_null.nunique(dropna=True))
    sample_size = max(len(sample_non_null), 1)
    sample_unique_ratio = sample_unique / sample_size
    sample_non_null_ratio = len(sample_non_null) / max(len(sample), 1)
    estimated_non_null = max(1, int(round(sample_non_null_ratio * total_count)))
    estimated = int(round(sample_unique_ratio * estimated_non_null))
    return min(total_count, max(sample_unique, estimated))


def _is_pk_candidate(col: str, series: pd.Series) -> bool:
    """High uniqueness + ID-like name → probable primary key."""
    sample = series.head(_SCHEMA_SAMPLE_SIZE)
    sample = sample[sample.notna()]
    if sample.empty:
        return False

    uniqueness = sample.nunique(dropna=True) / max(len(sample), 1)
    return uniqueness > 0.95 and bool(_ID_PATTERN.search(col))


def _detect_datetime(series: pd.Series) -> bool:
    """Detect datetime-like columns without triggering pandas inference warnings.

    The check is intentionally conservative:
    - ignore null/empty values
    - inspect only a small sample for speed
    - try a handful of explicit formats vectorized first
    - fall back to per-value format checks only if the batch pass is inconclusive
    - classify as datetime only when at least 80% of sampled values parse
    """

    # Remove nulls, blanks, and repeated placeholders before testing.
    sample = series.head(_SCHEMA_SAMPLE_SIZE).astype(str).str.strip()
    sample = sample[sample.ne("")]
    sample = sample[~sample.str.lower().isin({"nan", "nat", "none"})]
    sample = sample.drop_duplicates().head(_SCHEMA_SAMPLE_SIZE)

    if sample.empty:
        return False

    # First try explicit formats in a vectorized way. This is fast and warning-free.
    # It also handles the common case where a column uses one consistent date layout.
    best_ratio = 0.0
    for fmt in _DATETIME_FORMATS:
        parsed = pd.to_datetime(sample, format=fmt, errors="coerce", cache=True)
        ratio = float(parsed.notna().mean())
        if ratio > best_ratio:
            best_ratio = ratio
        if best_ratio >= _DATETIME_SUCCESS_THRESHOLD:
            return True

    # If the batch pass was close but not definitive, test each sampled value against
    # the same explicit formats. This is still bounded by the small sample size and
    # avoids pandas' format inference fallback entirely.
    successful = 0
    for value in sample:
        for fmt in _DATETIME_FORMATS:
            try:
                datetime.strptime(value, fmt)
                successful += 1
                break
            except ValueError:
                continue

    return (successful / len(sample)) >= _DATETIME_SUCCESS_THRESHOLD


def _sample_values(series: pd.Series, n: int = 5) -> list:
    sample = series.head(max(n, _SCHEMA_SAMPLE_SIZE))
    sample = sample[sample.notna()]
    vals = sample.head(n)
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
        if len(df) > _LARGE_DATASET_THRESHOLD:
            sample = s.head(_SCHEMA_SAMPLE_SIZE)
            null_pct = round(float(sample.isna().mean()) * 100, 2) if len(sample) else 0.0
            null_count = int(round((null_pct / 100) * len(s)))
        else:
            null_count = int(s.isna().sum())
            null_pct = round(null_count / len(s) * 100, 2) if len(s) else 0.0
        unique_count = _estimate_unique_count(s)
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

    if len(df) > _LARGE_DATASET_THRESHOLD:
        dup_sample = df.head(_SCHEMA_SAMPLE_SIZE)
        dup_ratio = float(dup_sample.duplicated().sum() / max(len(dup_sample), 1)) if len(dup_sample) else 0.0
        dup_count = int(round(dup_ratio * len(df)))
    else:
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
        memory_mb=round(df.memory_usage(deep=False).sum() / 1e6, 3),
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
