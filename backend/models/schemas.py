"""
models/schemas.py
─────────────────
All Pydantic request/response models used across the API.
"""

from __future__ import annotations
from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field


# ══════════════════════════════════════════════════════════════════
# INGEST / SCHEMA
# ══════════════════════════════════════════════════════════════════

class ColumnProfile(BaseModel):
    name: str
    dtype: str                        # pandas dtype string
    null_count: int
    null_pct: float                   # 0–100
    unique_count: int
    sample_values: List[Any]          # first 5 non-null values
    is_numeric: bool
    is_datetime: bool
    is_categorical: bool
    suggested_pk: bool                # heuristic: high uniqueness + id-like name
    has_outliers: Optional[bool] = None   # filled after outlier scan


class JoinSuggestion(BaseModel):
    left_file: str
    right_file: str
    left_col: str
    right_col: str
    confidence: float                 # 0–1


class SchemaReport(BaseModel):
    file_id: str                      # server-side UUID for this dataset
    filename: str
    row_count: int
    col_count: int
    columns: List[ColumnProfile]
    duplicate_row_count: int
    duplicate_row_pct: float
    memory_mb: float


class IngestResponse(BaseModel):
    file_ids: List[str]
    schemas: List[SchemaReport]
    join_suggestions: List[JoinSuggestion]


# ══════════════════════════════════════════════════════════════════
# CLEANING CONFIG  (sent by the frontend after user choices)
# ══════════════════════════════════════════════════════════════════

NullStrategy = Literal[
    "drop_rows", "drop_column",
    "fill_mean", "fill_median", "fill_mode",
    "fill_forward", "fill_backward",
    "fill_custom",
]

OutlierStrategy = Literal["remove_iqr", "cap_percentile", "keep"]

DtypeStrategy = Literal[
    "to_numeric", "to_datetime", "to_category", "leave"
]


class NullConfig(BaseModel):
    column: str
    strategy: NullStrategy
    custom_value: Optional[Union[str, float, int]] = None


class OutlierConfig(BaseModel):
    column: str
    strategy: OutlierStrategy
    lower_percentile: float = 1.0    # used when strategy = cap_percentile
    upper_percentile: float = 99.0


class DtypeConfig(BaseModel):
    column: str
    strategy: DtypeStrategy
    datetime_format: Optional[str] = None   # e.g. "%Y-%m-%d"


class StandardizationConfig(BaseModel):
    lowercase_columns: bool = True
    replace_spaces_with_underscore: bool = True
    trim_whitespace: bool = True
    drop_constant_columns: bool = False
    drop_duplicates: bool = True


class CleaningConfig(BaseModel):
    file_id: str
    null_configs: List[NullConfig] = Field(default_factory=list)
    outlier_configs: List[OutlierConfig] = Field(default_factory=list)
    dtype_configs: List[DtypeConfig] = Field(default_factory=list)
    standardization: StandardizationConfig = Field(
        default_factory=StandardizationConfig
    )


# ══════════════════════════════════════════════════════════════════
# CLEANING RESPONSE
# ══════════════════════════════════════════════════════════════════

class CleaningStep(BaseModel):
    step: str                        # human-readable description
    column: Optional[str]
    action: str
    rows_affected: int
    detail: Optional[str] = None


class CleaningSummaryPreview(BaseModel):
    """
    Returned BEFORE applying changes — shown to user for confirmation.
    """
    file_id: str
    steps: List[CleaningStep]
    rows_before: int
    rows_after_estimate: int
    pct_rows_dropped_estimate: float
    warnings: List[str]              # e.g. "Will drop >10% of rows"


class CleaningResult(BaseModel):
    """
    Returned AFTER applying cleaning. Contains the new clean file_id.
    """
    original_file_id: str
    clean_file_id: str               # UUID for the cleaned dataset
    rows_before: int
    rows_after: int
    cols_before: int
    cols_after: int
    steps_applied: List[CleaningStep]
    quality_score_before: float      # 0–100
    quality_score_after: float
    warnings: List[str]


# ══════════════════════════════════════════════════════════════════
# ENHANCED CLEANING REPORTS
# ══════════════════════════════════════════════════════════════════


class ColumnAnalysis(BaseModel):
    name: str
    dtype: str
    null_count: int
    null_pct: float
    unique_count: int
    cardinality: float  # unique / non-null
    inferred_semantic: str  # date, id, email, currency, category, text, numeric
    sample_values: List[Any]
    has_outliers: Optional[bool] = None
    outlier_count: Optional[int] = None
    memory_bytes: Optional[int] = None


class CleaningReport(BaseModel):
    file_id: str
    filename: str
    row_count: int
    col_count: int
    quality_score: float
    memory_mb: float
    duplicates: int
    duplicate_pct: float
    missing_values: int
    missing_pct: float
    columns: List[ColumnAnalysis]
    generated_at: str


# ══════════════════════════════════════════════════════════════════
# DATASET UNDERSTANDING
# ══════════════════════════════════════════════════════════════════


class DatasetUnderstanding(BaseModel):
    file_id: str
    title: str
    business_domain: Optional[str]
    description: Optional[str]
    row_count: int
    col_count: int
    numeric_columns: List[str]
    categorical_columns: List[str]
    date_columns: List[str]
    target_candidates: List[str]
    suggested_kpis: List[str]
    interesting_relationships: List[str]
    business_insights: List[str]
    recommended_analyses: List[str]
    suggested_questions: List[str]
    generated_at: str


# ══════════════════════════════════════════════════════════════════
# EXPORT
# ══════════════════════════════════════════════════════════════════

class ExportRequest(BaseModel):
    file_id: str
    format: Literal["csv", "json", "xlsx"] = "csv"
