"""
services/sql_service.py
────────────────────────
The Text-to-SQL brain.

Flow:
  1. Build a schema context string from registered tables
  2. Call Groq API (free) with the schema + user question
  3. Parse the SQL from the response
  4. Validate it with sql_validator.py
  5. Execute via DuckDB
  6. Auto-suggest the best visualization for the result
  7. Return QueryResult
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import httpx
import pandas as pd

from models.sql_schemas import (
    QueryColumn,
    QueryHistoryItem,
    QueryResult,
    TableInfo,
    VizSuggestion,
)
from services.sql_validator import validate_sql
from utils.duck_session import DuckSession


# ══════════════════════════════════════════════════════════════════
# SCHEMA CONTEXT BUILDER
# ══════════════════════════════════════════════════════════════════

def build_schema_context(tables: Dict[str, TableInfo]) -> str:
    lines = ["Available SQL tables (DuckDB syntax):"]
    for tname, info in tables.items():
        col_defs = ", ".join(
            f"{col} ({info.column_types[col]})" for col in info.columns
        )
        lines.append(f"  • {tname} ({info.row_count:,} rows): {col_defs}")

    if len(tables) > 1:
        lines.append("")
        lines.append("Possible JOIN relationships (inferred from column names):")
        from collections import defaultdict
        col_to_tables: Dict[str, List[str]] = defaultdict(list)
        for tname, info in tables.items():
            for col in info.columns:
                col_to_tables[col.lower()].append(tname)
        for col, tnames in col_to_tables.items():
            if len(tnames) > 1:
                lines.append(f"  • '{col}' appears in: {', '.join(tnames)}")

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════
# PROMPT BUILDER
# ══════════════════════════════════════════════════════════════════

def _build_system_prompt(schema_context: str) -> str:
    return f"""You are an expert SQL analyst assistant for a data platform called DataGenie AI.
Your job is to convert natural language questions into correct DuckDB SQL queries.

{schema_context}

STRICT RULES — you MUST follow these:
1. Only use columns and tables that exist in the schema above. Never invent column names.
2. Always use DuckDB-compatible SQL syntax.
3. For aggregations, always include GROUP BY for non-aggregated columns.
4. Handle NULLs safely: use COALESCE where appropriate.
5. For "top N" questions, always use ORDER BY + LIMIT.
6. For date/time filtering, use DuckDB date functions (date_trunc, strftime, etc).
7. Never use DROP, DELETE, INSERT, UPDATE, ALTER, CREATE, or any write operations.
8. If the question is ambiguous, make a reasonable assumption and note it.
9. If the question cannot be answered from the available columns, say so clearly.

RESPONSE FORMAT — always respond with valid JSON in this exact structure:
{{
  "sql": "<the complete SQL query>",
  "explanation": "<plain English explanation of what the SQL does and why>",
  "assumptions": "<any assumptions made, or empty string>",
  "clarification_needed": "<question to ask user if truly ambiguous, or empty string>"
}}

No markdown, no code fences, just raw JSON."""


def _parse_llm_response(content: str) -> Tuple[str, str, str]:
    content = re.sub(r"```(?:json)?", "", content).strip().rstrip("```").strip()
    try:
        data = json.loads(content)
        sql = data.get("sql", "").strip()
        explanation = data.get("explanation", "").strip()
        clarification = data.get("clarification_needed", "").strip()
        return sql, explanation, clarification
    except json.JSONDecodeError:
        sql_match = re.search(r"SELECT.*?;", content, re.IGNORECASE | re.DOTALL)
        sql = sql_match.group(0) if sql_match else ""
        return sql, "Could not parse full explanation.", ""


# ══════════════════════════════════════════════════════════════════
# VISUALIZATION SUGGESTER
# ══════════════════════════════════════════════════════════════════

def _suggest_viz(df: pd.DataFrame, sql: str) -> Optional[VizSuggestion]:
    if df.empty or len(df.columns) == 0:
        return None

    cols = list(df.columns)
    numeric_cols = [c for c in cols if pd.api.types.is_numeric_dtype(df[c])]
    string_cols = [c for c in cols if pd.api.types.is_object_dtype(df[c]) or str(df[c].dtype) == "category"]
    date_cols = [c for c in cols if pd.api.types.is_datetime64_any_dtype(df[c])
                 or any(kw in c.lower() for kw in ("date", "month", "year", "week", "time"))]
    row_count = len(df)

    if date_cols and numeric_cols:
        return VizSuggestion(
            chart_type="line",
            x_col=date_cols[0],
            y_col=numeric_cols[0],
            title=f"{numeric_cols[0]} over time",
            reason="Detected a date/time column with a numeric measure — line chart shows trend.",
        )

    if string_cols and numeric_cols and row_count <= 30:
        y_col = numeric_cols[0]
        total = df[y_col].sum()
        if total > 0 and row_count <= 8:
            return VizSuggestion(
                chart_type="pie",
                x_col=string_cols[0],
                y_col=y_col,
                title=f"{y_col} distribution by {string_cols[0]}",
                reason=f"Small number of categories ({row_count}) with a summable metric — pie shows proportion.",
            )
        return VizSuggestion(
            chart_type="bar",
            x_col=string_cols[0],
            y_col=numeric_cols[0],
            title=f"{numeric_cols[0]} by {string_cols[0]}",
            reason="Categorical X-axis with numeric metric — bar chart is ideal.",
        )

    if len(numeric_cols) >= 2:
        return VizSuggestion(
            chart_type="scatter",
            x_col=numeric_cols[0],
            y_col=numeric_cols[1],
            title=f"{numeric_cols[0]} vs {numeric_cols[1]}",
            reason="Two numeric columns — scatter reveals correlation.",
        )

    if len(numeric_cols) == 1:
        return VizSuggestion(
            chart_type="histogram",
            x_col=numeric_cols[0],
            y_col=None,
            title=f"Distribution of {numeric_cols[0]}",
            reason="Single numeric column — histogram shows distribution.",
        )

    return VizSuggestion(
        chart_type="table",
        title="Query Results",
        reason="Mixed or complex result — tabular view is clearest.",
    )


# ══════════════════════════════════════════════════════════════════
# GROQ API CONFIG  (replaces Anthropic)
# ══════════════════════════════════════════════════════════════════

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL   = "llama-3.3-70b-versatile"   # free, fast, great at SQL


# ══════════════════════════════════════════════════════════════════
# MAIN SERVICE
# ══════════════════════════════════════════════════════════════════

async def nl_to_sql_and_execute(
    question: str,
    session: DuckSession,
    max_rows: int = 500,
    api_key: str = "",          # now expects GROQ_API_KEY
) -> QueryResult:
    """
    Full pipeline: natural language → SQL → validate → execute → visualize.
    Uses Groq (free tier) instead of Anthropic.
    """
    schema_ctx = build_schema_context(session.tables)
    system_prompt = _build_system_prompt(schema_ctx)
    t_start = time.perf_counter()

    # ── Step 1: Call Groq API ────────────────────────────────────
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                GROQ_API_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": GROQ_MODEL,
                    "max_tokens": 1024,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user",   "content": question},
                    ],
                },
            )
            resp.raise_for_status()
            data = resp.json()
            raw_content = data["choices"][0]["message"]["content"]
    except httpx.HTTPStatusError as e:
        return _error_result(question, "", f"Groq API error {e.response.status_code}: {e.response.text}")
    except Exception as e:
        return _error_result(question, "", f"Failed to reach Groq API: {e}")

    # ── Step 2: Parse response ───────────────────────────────────
    sql, explanation, clarification = _parse_llm_response(raw_content)

    if clarification:
        return _error_result(question, sql, f"Clarification needed: {clarification}")

    if not sql:
        return _error_result(question, sql, "No SQL query returned. Please rephrase your question.")

    # ── Step 3: Validate ─────────────────────────────────────────
    validation = validate_sql(sql, session.tables)
    if not validation.is_valid:
        return _error_result(
            question, sql,
            "Generated SQL failed validation:\n" + "\n".join(validation.issues)
        )

    # ── Step 4: Execute ──────────────────────────────────────────
    try:
        result_df = session.execute(sql)
    except Exception as e:
        return _error_result(question, sql, f"SQL execution failed: {e}")

    elapsed_ms = (time.perf_counter() - t_start) * 1000
    truncated = len(result_df) > max_rows
    if truncated:
        result_df = result_df.head(max_rows)

    result_df = result_df.where(pd.notnull(result_df), None)
    viz = _suggest_viz(result_df, sql)

    columns = [
        QueryColumn(name=c, dtype=str(result_df[c].dtype))
        for c in result_df.columns
    ]

    warning_note = ""
    if validation.warnings:
        warning_note = "\n⚠️ " + "; ".join(validation.warnings)

    return QueryResult(
        session_id=session.session_id,
        question=question,
        sql=sql,
        sql_explanation=explanation + warning_note,
        columns=columns,
        rows=result_df.to_dict(orient="records"),
        row_count=len(result_df),
        truncated=truncated,
        execution_time_ms=round(elapsed_ms, 2),
        viz_suggestion=viz,
        error=None,
    )


async def execute_raw_sql(
    sql: str,
    session: DuckSession,
    max_rows: int = 500,
) -> QueryResult:
    """Execute raw SQL directly — no LLM needed."""
    t_start = time.perf_counter()

    validation = validate_sql(sql, session.tables)
    if not validation.is_valid:
        return _error_result(
            sql, sql,
            "SQL validation failed:\n" + "\n".join(validation.issues)
        )

    try:
        result_df = session.execute(sql)
    except Exception as e:
        return _error_result(sql, sql, f"Execution error: {e}")

    elapsed_ms = (time.perf_counter() - t_start) * 1000
    truncated = len(result_df) > max_rows
    if truncated:
        result_df = result_df.head(max_rows)

    result_df = result_df.where(pd.notnull(result_df), None)
    viz = _suggest_viz(result_df, sql)

    return QueryResult(
        session_id=session.session_id,
        question=sql,
        sql=sql,
        sql_explanation="Raw SQL query executed directly.",
        columns=[QueryColumn(name=c, dtype=str(result_df[c].dtype)) for c in result_df.columns],
        rows=result_df.to_dict(orient="records"),
        row_count=len(result_df),
        truncated=truncated,
        execution_time_ms=round(elapsed_ms, 2),
        viz_suggestion=viz,
        error=None,
    )


# ── Helpers ────────────────────────────────────────────────────────────────────

def _error_result(question: str, sql: str, error: str) -> QueryResult:
    return QueryResult(
        session_id="",
        question=question,
        sql=sql,
        sql_explanation="",
        columns=[],
        rows=[],
        row_count=0,
        truncated=False,
        execution_time_ms=0,
        viz_suggestion=None,
        error=error,
    )