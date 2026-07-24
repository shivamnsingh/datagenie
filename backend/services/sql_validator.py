"""
services/sql_validator.py
──────────────────────────
Validates generated SQL BEFORE sending it to DuckDB.

Catches:
  • References to columns that don't exist in any registered table
  • References to tables not in the session
  • Dangerous write operations (DROP, DELETE, INSERT, UPDATE, ALTER, CREATE)
  • Overly broad SELECT * on large tables

Returns a ValidationResult with issues list and corrected SQL if possible.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from models.sql_schemas import TableInfo

# ── Types ──────────────────────────────────────────────────────────────────────

@dataclass
class ValidationResult:
    is_valid: bool
    issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    cleaned_sql: Optional[str] = None    # SQL with minor fixes applied


# ── Dangerous keywords ────────────────────────────────────────────────────────

_WRITE_OPS = re.compile(
    r"\b(DROP|DELETE|INSERT|UPDATE|ALTER|CREATE|TRUNCATE|REPLACE|MERGE|EXEC|EXECUTE)\b",
    re.IGNORECASE,
)

# ── Token extraction ──────────────────────────────────────────────────────────

def _extract_identifiers(sql: str) -> Set[str]:
    """
    Rough extraction of bare identifiers from SQL.
    Strips comments, string literals, and known keywords first.
    """
    # Remove single-line comments
    sql = re.sub(r"--[^\n]*", " ", sql)
    # Remove block comments
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    # Remove string literals
    sql = re.sub(r"'[^']*'", " ", sql)
    sql = re.sub(r'"[^"]*"', " ", sql)

    tokens = re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]*\b", sql)

    # Strip SQL keywords we don't care about
    _KEYWORDS = {
        "select","from","where","join","on","group","by","order","having",
        "limit","offset","as","and","or","not","in","is","null","true","false",
        "inner","left","right","full","outer","cross","union","all","distinct",
        "case","when","then","else","end","between","like","exists","with",
        "over","partition","rows","range","preceding","following","current",
        "row","asc","desc","using","natural","lateral","top",
        "int","integer","bigint","float","double","varchar","text","boolean",
        "date","timestamp","interval","numeric","decimal",
        # DuckDB functions
        "count","sum","avg","min","max","coalesce","nullif","ifnull","iif",
        "round","floor","ceil","abs","length","upper","lower","trim","substr",
        "strftime","date_trunc","extract","now","today","cast","try_cast",
        "rank","dense_rank","row_number","lag","lead","ntile",
        "stddev","variance","median","mode","percentile_cont","percentile_disc",
        "string_agg","list_agg","array_agg","count",
    }
    return {t.lower() for t in tokens if t.lower() not in _KEYWORDS}


def _extract_aliases(sql: str) -> Set[str]:
    """
    Extract identifiers introduced by `AS <alias>` — these are query-defined
    names (e.g. SELECT SUM(x) AS total_revenue) and must never be flagged as
    hallucinated columns, since they don't exist in the source schema by
    design.
    """
    sql_no_strings = re.sub(r"'[^']*'", " ", sql)
    sql_no_strings = re.sub(r'"[^"]*"', " ", sql_no_strings)
    return {m.lower() for m in re.findall(r"\bAS\s+([a-zA-Z_][a-zA-Z0-9_]*)", sql_no_strings, re.IGNORECASE)}


# ── Main validator ─────────────────────────────────────────────────────────────

def validate_sql(
    sql: str,
    table_info: Dict[str, TableInfo],   # table_name → TableInfo
) -> ValidationResult:
    """
    Validate generated SQL against the session's registered tables.

    Parameters
    ----------
    sql        : The SQL string to validate
    table_info : Dict of table_name → TableInfo (from DuckSession.tables)
    """
    issues: List[str] = []
    warnings: List[str] = []

    # 1. Block write operations
    write_match = _WRITE_OPS.search(sql)
    if write_match:
        return ValidationResult(
            is_valid=False,
            issues=[
                f"Write operation '{write_match.group().upper()}' is not allowed. "
                "Only SELECT queries are permitted."
            ],
        )

    # 2. Must contain SELECT
    if not re.search(r"\bSELECT\b", sql, re.IGNORECASE):
        return ValidationResult(
            is_valid=False,
            issues=["Query must contain a SELECT statement."],
        )

    # 3. Check referenced tables exist
    all_known_tables = set(table_info.keys())
    all_known_cols: Set[str] = set()
    col_to_tables: Dict[str, List[str]] = {}

    for tname, info in table_info.items():
        for col in info.columns:
            col_lower = col.lower()
            all_known_cols.add(col_lower)
            col_to_tables.setdefault(col_lower, []).append(tname)

    # Find FROM / JOIN table references
    from_pattern = re.compile(
        r"\b(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_]*)", re.IGNORECASE
    )
    referenced_tables = {m.group(1).lower() for m in from_pattern.finditer(sql)}

    unknown_tables = referenced_tables - {t.lower() for t in all_known_tables}
    if unknown_tables:
        issues.append(
            f"Unknown table(s): {', '.join(repr(t) for t in unknown_tables)}. "
            f"Available tables: {', '.join(repr(t) for t in all_known_tables)}."
        )

    # 4. Check for SELECT * warning on large tables
    if re.search(r"SELECT\s+\*", sql, re.IGNORECASE):
        for tname in referenced_tables:
            info = table_info.get(tname)
            if info and info.row_count > 10_000:
                warnings.append(
                    f"SELECT * on '{tname}' ({info.row_count:,} rows) may be slow. "
                    "Consider selecting specific columns."
                )

    # 5. Spot-check identifiers that look like column references
    # but aren't known (heuristic — avoids alias false-positives)
    query_aliases = _extract_aliases(sql)
    identifiers = _extract_identifiers(sql)
    possible_hallucinations = (
        identifiers
        - all_known_cols
        - {t.lower() for t in all_known_tables}
        - query_aliases
        # exclude single-letter aliases (a, b, t, s, e …)
        - {i for i in identifiers if len(i) <= 2}
    )
    if possible_hallucinations:
        warnings.append(
            f"Unrecognised identifier(s): {', '.join(sorted(possible_hallucinations))}. "
            "These may be aliases or functions — verify the query."
        )

    is_valid = len(issues) == 0
    return ValidationResult(
        is_valid=is_valid,
        issues=issues,
        warnings=warnings,
        cleaned_sql=sql.strip() if is_valid else None,
    )