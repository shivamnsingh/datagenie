"""dataset package — dataset understanding helpers

This thin layer re-uses the existing `services.schema_service` analysis
functions and exposes a friendly API for dataset understanding.
"""
from services.schema_service import build_schema_report, suggest_joins

def analyze_dataset(df, filename: str, file_id: str | None = None):
    """Return a SchemaReport for the supplied DataFrame."""
    return build_schema_report(df, filename, file_id=file_id)

__all__ = ["analyze_dataset", "suggest_joins"]
