"""
services/rag_chunker.py
────────────────────────
Converts a DataFrame into a list of rich text chunks suitable for embedding.

Strategy — we generate FIVE types of chunks per table:

  1. SCHEMA CHUNK        — column names, types, nulls, ranges (1 chunk per table)
  2. STATISTICS CHUNK    — mean/median/std/min/max per numeric col (1 chunk per table)
  3. SAMPLE ROW CHUNKS   — groups of 10 rows serialised as key:value text
  4. CATEGORY CHUNKS     — value_counts summary per categorical column
  5. CORRELATION CHUNK   — top correlated numeric pairs (1 chunk per table)

This gives the LLM enough statistical + factual context to answer
both "what is the data?" and "why is X happening?" questions.
"""

from __future__ import annotations

from typing import List, Tuple

import numpy as np
import pandas as pd


Chunk = Tuple[str, str]   # (text_content, source_label)

_LARGE_DATASET_THRESHOLD = 100_000
_SCHEMA_SAMPLE_SIZE = 100


# ══════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════

def _fmt(v) -> str:
    """Format a value compactly for chunk text."""
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "NULL"
    if isinstance(v, float):
        return f"{v:,.4g}"
    return str(v)


def _sample_non_null(series: pd.Series, limit: int = _SCHEMA_SAMPLE_SIZE) -> pd.Series:
    sample = series.head(limit)
    sample = sample[sample.notna()]
    if len(sample) <= limit:
        return sample
    return sample.head(limit)


# ══════════════════════════════════════════════════════════════════
# CHUNK GENERATORS
# ══════════════════════════════════════════════════════════════════

def _schema_chunk(df: pd.DataFrame, table_name: str) -> Chunk:
    lines = [f"TABLE: {table_name}", f"Rows: {len(df):,}  Columns: {len(df.columns)}"]
    for col in df.columns:
        s = df[col]
        if len(df) > _LARGE_DATASET_THRESHOLD:
            sample = s.head(_SCHEMA_SAMPLE_SIZE)
            null_pct = float(sample.isna().mean()) * 100 if len(sample) else 0.0
        else:
            null_pct = float(s.isna().mean()) * 100
        if len(df) > _LARGE_DATASET_THRESHOLD:
            sample = s.head(_SCHEMA_SAMPLE_SIZE)
            sample = sample[sample.notna()]
            if sample.empty:
                unique = 0
            else:
                sample_unique = int(sample.nunique(dropna=True))
                sample_non_null_ratio = len(sample) / max(len(s.head(_SCHEMA_SAMPLE_SIZE)), 1)
                estimated_non_null = max(1, int(round(sample_non_null_ratio * len(s))))
                unique = int(round((sample_unique / max(len(sample), 1)) * estimated_non_null))
        else:
            unique = int(s.nunique(dropna=True))
        dtype = str(s.dtype)
        lines.append(
            f"  {col} [{dtype}] — {unique:,} unique values, {null_pct:.1f}% null"
        )
    return "\n".join(lines), f"{table_name} · schema"


def _statistics_chunk(df: pd.DataFrame, table_name: str) -> Chunk:
    num_cols = df.select_dtypes(include="number").columns
    if len(num_cols) == 0:
        return f"TABLE: {table_name}\nNo numeric columns.", f"{table_name} · statistics"

    lines = [f"NUMERIC STATISTICS for table: {table_name}"]
    for col in num_cols:
        s = df[col].dropna()
        if len(s) == 0:
            continue
        lines.append(
            f"  {col}: "
            f"min={_fmt(s.min())}  max={_fmt(s.max())}  "
            f"mean={_fmt(s.mean())}  median={_fmt(s.median())}  "
            f"std={_fmt(s.std())}  "
            f"total={_fmt(s.sum())}"
        )
    return "\n".join(lines), f"{table_name} · statistics"


def _sample_row_chunks(
    df: pd.DataFrame,
    table_name: str,
    chunk_size: int = 10,
    max_chunks: int = 20,
) -> List[Chunk]:
    """
    Serialize rows in groups of `chunk_size`.
    Cap at `max_chunks` to keep index size reasonable.
    """
    chunks: List[Chunk] = []
    total = min(len(df), chunk_size * max_chunks)
    subset = df.head(total)

    for start in range(0, total, chunk_size):
        batch = subset.iloc[start : start + chunk_size]
        lines = [f"SAMPLE ROWS from {table_name} (rows {start+1}–{start+len(batch)}):"]
        for row in batch.itertuples(index=False, name=None):
            row_str = "  { " + ",  ".join(f"{c}: {_fmt(value)}" for c, value in zip(df.columns, row)) + " }"
            lines.append(row_str)
        chunks.append(("\n".join(lines), f"{table_name} · rows {start+1}-{start+len(batch)}"))

    return chunks


def _category_chunks(df: pd.DataFrame, table_name: str) -> List[Chunk]:
    """One chunk per categorical column with value distribution."""
    chunks: List[Chunk] = []
    cat_cols = df.select_dtypes(include=["object", "category"]).columns

    for col in cat_cols:
        if len(df) > _LARGE_DATASET_THRESHOLD:
            series = df[col].head(1_000)
            series = series[series.notna()]
        else:
            series = df[col].dropna()

        vc = series.value_counts(dropna=True).head(20)
        if len(vc) == 0:
            continue
        total = max(int(series.notna().sum()), 1)
        if len(df) > _LARGE_DATASET_THRESHOLD:
            unique_count = int(series.nunique(dropna=True))
        else:
            unique_count = int(df[col].nunique(dropna=True))
        lines = [f"VALUE DISTRIBUTION: {table_name}.{col} (top {len(vc)} of {unique_count} unique)"]
        for val, cnt in vc.items():
            pct = cnt / total * 100
            lines.append(f"  {_fmt(val)}: {cnt:,} ({pct:.1f}%)")
        chunks.append(("\n".join(lines), f"{table_name} · {col} distribution"))

    return chunks


def _correlation_chunk(df: pd.DataFrame, table_name: str) -> Chunk:
    """Top correlated numeric pairs — helps answer 'what drives X?' questions."""
    num_df = df.select_dtypes(include="number")
    if len(num_df.columns) < 2:
        return f"TABLE: {table_name}\nInsufficient numeric columns for correlation.", f"{table_name} · correlations"

    corr = num_df.corr().abs()
    # Flatten upper triangle
    pairs = []
    cols = list(corr.columns)
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            pairs.append((cols[i], cols[j], corr.iloc[i, j]))

    pairs.sort(key=lambda x: -x[2])
    top = pairs[:10]

    lines = [f"TOP CORRELATIONS in table: {table_name}"]
    for a, b, r in top:
        strength = "strong" if r > 0.7 else "moderate" if r > 0.4 else "weak"
        lines.append(f"  {a} ↔ {b}: r={r:.3f} ({strength})")
    return "\n".join(lines), f"{table_name} · correlations"


def _date_summary_chunk(df: pd.DataFrame, table_name: str) -> List[Chunk]:
    """Summarise date columns: range, gaps, frequency."""
    chunks: List[Chunk] = []
    for col in df.columns:
        if not pd.api.types.is_datetime64_any_dtype(df[col]):
            # Try to detect date-like strings
            if not any(kw in col.lower() for kw in ("date", "time", "month", "year")):
                continue
            try:
                parsed = pd.to_datetime(df[col], errors="coerce")
                if parsed.notna().mean() < 0.8:
                    continue
                s = parsed
            except Exception:
                continue
        else:
            s = df[col]

        s = s.dropna()
        if len(s) == 0:
            continue

        lines = [
            f"DATE COLUMN: {table_name}.{col}",
            f"  Range: {s.min()} → {s.max()}",
            f"  Span: {(s.max() - s.min()).days} days",
            f"  Non-null: {len(s):,}",
        ]

        # Monthly counts if range > 30 days
        try:
            if (s.max() - s.min()).days > 30:
                monthly = s.dt.to_period("M").value_counts().sort_index()
                lines.append(f"  Monthly record counts (sample):")
                for period, cnt in list(monthly.items())[:12]:
                    lines.append(f"    {period}: {cnt:,}")
        except Exception:
            pass

        chunks.append(("\n".join(lines), f"{table_name} · {col} timeline"))

    return chunks


# ══════════════════════════════════════════════════════════════════
# PUBLIC API
# ══════════════════════════════════════════════════════════════════

def build_chunks(
    df: pd.DataFrame,
    table_name: str,
    include_sample_rows: bool = True,
) -> List[Chunk]:
    """
    Build all chunk types for a DataFrame.
    Returns list of (text, source_label) tuples.
    """
    chunks: List[Chunk] = []

    chunks.append(_schema_chunk(df, table_name))
    chunks.append(_statistics_chunk(df, table_name))
    chunks.append(_correlation_chunk(df, table_name))
    chunks.extend(_category_chunks(df, table_name))
    chunks.extend(_date_summary_chunk(df, table_name))

    if include_sample_rows:
        chunks.extend(_sample_row_chunks(df, table_name))

    return chunks
