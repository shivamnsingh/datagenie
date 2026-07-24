"""sql package — adapter over services.sql_service and services.sql_validator

Provides the primary NL→SQL and raw SQL execution functions.
"""
from services.sql_service import nl_to_sql_and_execute, execute_raw_sql
from services.sql_validator import validate_sql, ValidationResult

__all__ = ["nl_to_sql_and_execute", "execute_raw_sql", "validate_sql", "ValidationResult"]
