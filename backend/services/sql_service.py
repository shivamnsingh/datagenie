"""
services/sql_service.py
────────────────────────
The Text-to-SQL brain.

Flow:
    1. Build a schema context string from registered tables
    2. Call the LLM (Gemini) via the LLMService with the schema + user question
    3. Parse the SQL from the LLM response
    4. Validate it with sql_validator.py
    5. Execute via DuckDB
    6. Auto-suggest the best visualization for the result
    7. Return QueryResult

LLM is prompted with strict rules — never hallucinate columns, always use only
the provided schema and ask for clarification if ambiguous.
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import pandas as pd

from models.sql_schemas import (
    QueryColumn,
    QueryHistoryItem,
    QueryResult,
    TableInfo,
    VizSuggestion,
)
from services.sql_validator import validate_sql
# Use the centralized llm_service via runtime import where needed
from utils.duck_session import DuckSession


# ══════════════════════════════════════════════════════════════════
# SCHEMA CONTEXT BUILDER
# ══════════════════════════════════════════════════════════════════

def build_schema_context(tables: Dict[str, TableInfo]) -> str:
    """
    Build a compact schema string to inject into the LLM system prompt.
    Format keeps token count low while giving the model everything it needs.
    """
    lines = ["Available SQL tables (DuckDB syntax):"]
    for tname, info in tables.items():
        col_defs = ", ".join(
            f"{col} ({info.column_types[col]})" for col in info.columns
        )
        lines.append(f"  • {tname} ({info.row_count:,} rows): {col_defs}")

    if len(tables) > 1:
        lines.append("")
        lines.append("Possible JOIN relationships (inferred from column names):")
        # Simple heuristic: find shared column names across tables
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
# SYSTEM PROMPT
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
    """
    Parse LLM JSON response.
    Returns (sql, explanation, clarification_needed).
    Falls back gracefully if JSON is malformed.
    """
    # Strip markdown fences if present despite instructions
    content = re.sub(r"```(?:json)?", "", content).strip().rstrip("```").strip()

    try:
        data = json.loads(content)
        sql = data.get("sql", "").strip()
        explanation = data.get("explanation", "").strip()
        clarification = data.get("clarification_needed", "").strip()
        return sql, explanation, clarification
    except json.JSONDecodeError:
        # Last resort: try to extract SQL block
        sql_match = re.search(r"SELECT.*?;", content, re.IGNORECASE | re.DOTALL)
        sql = sql_match.group(0) if sql_match else ""
        return sql, "Could not parse full explanation.", ""


# ══════════════════════════════════════════════════════════════════
# VISUALIZATION SUGGESTER
# ══════════════════════════════════════════════════════════════════

def _suggest_viz(df: pd.DataFrame, sql: str) -> Optional[VizSuggestion]:
    """
    Heuristically decide the best chart type for a query result.
    Rules priority:
      1. Time column + numeric → line chart
      2. 1 string col + 1 numeric + few rows → bar chart
      3. 1 string col + 1 numeric with % or proportion → pie chart
      4. 2 numeric cols → scatter
      5. Single numeric column → histogram
      6. Many columns → table
    """
    if df.empty or len(df.columns) == 0:
        return None

    cols = list(df.columns)
    dtypes = {c: str(df[c].dtype) for c in cols}

    numeric_cols = [c for c in cols if pd.api.types.is_numeric_dtype(df[c])]
    string_cols = [c for c in cols if pd.api.types.is_object_dtype(df[c]) or str(df[c].dtype) == "category"]
    date_cols = [c for c in cols if pd.api.types.is_datetime64_any_dtype(df[c])
                 or any(kw in c.lower() for kw in ("date", "month", "year", "week", "time"))]

    row_count = len(df)

    # 1. Time series
    if date_cols and numeric_cols:
        return VizSuggestion(
            chart_type="line",
            x_col=date_cols[0],
            y_col=numeric_cols[0],
            title=f"{numeric_cols[0]} over time",
            reason="Detected a date/time column with a numeric measure — line chart shows trend.",
        )

    # 2. Bar chart (categorical + numeric, reasonable rows)
    if string_cols and numeric_cols and row_count <= 30:
        # Check if it looks like a proportion/percentage for pie
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

    # 3. Scatter (2 numeric)
    if len(numeric_cols) >= 2:
        return VizSuggestion(
            chart_type="scatter",
            x_col=numeric_cols[0],
            y_col=numeric_cols[1],
            title=f"{numeric_cols[0]} vs {numeric_cols[1]}",
            reason="Two numeric columns — scatter reveals correlation.",
        )

    # 4. Histogram (single numeric)
    if len(numeric_cols) == 1:
        return VizSuggestion(
            chart_type="histogram",
            x_col=numeric_cols[0],
            y_col=None,
            title=f"Distribution of {numeric_cols[0]}",
            reason="Single numeric column — histogram shows distribution.",
        )

    # 5. Fallback: table
    return VizSuggestion(
        chart_type="table",
        title="Query Results",
        reason="Mixed or complex result — tabular view is clearest.",
    )


# ══════════════════════════════════════════════════════════════════
# MAIN SERVICE
# ══════════════════════════════════════════════════════════════════





async def nl_to_sql_and_execute(
    question: str,
    session: DuckSession,
    max_rows: int = 500,
    api_key: str = "",
) -> QueryResult:
    """
    Full pipeline: natural language → SQL → validate → execute → visualize.
    """
    schema_ctx = build_schema_context(session.tables)
    system_prompt = _build_system_prompt(schema_ctx)
    t_start = time.perf_counter()

    # ── Step 1: Call Gemini (via LLMService) to generate SQL ──────
    from llm import llm_service

    prompt = system_prompt + "\n\nUser question: " + question + "\n\nRespond in the exact JSON format specified in the system prompt."

    try:
        gen = await llm_service.generate_sql(prompt)
        raw_content = gen.get("raw", "")
        sql = gen.get("sql")
        # If the LLM returned a JSON structure, try to parse explanation
        explanation = ""
        clarification = ""
        if raw_content:
            sql_p, explanation_p, clarification_p = _parse_llm_response(raw_content)
            # prefer explicit sql from parsing if extract found it
            if sql_p:
                sql = sql_p
            explanation = explanation_p
            clarification = clarification_p
    except Exception as e:
        return _error_result(question, "", f"LLM provider error: {e}")

    if clarification:
        return _error_result(question, sql, f"Clarification needed: {clarification}")

    if not sql:
        return _error_result(question, sql, "LLM did not return a SQL query. Please rephrase your question.")

    # ── Step 3+4: Validate → Execute, with unified auto-repair ────
    # Both a validation failure (e.g. Gemini referencing a table/column
    # that doesn't exist) and an execution failure (a DuckDB error) are
    # "the SQL is wrong" in the same sense — both get fed back to Gemini
    # for repair, up to 2 retries total. Previously only execution
    # failures triggered repair, so a validation failure (like a stray
    # unknown table) surfaced immediately as an unrecoverable error even
    # though it's exactly the class of mistake auto-repair exists to fix.
    last_error: Optional[Exception | str] = None
    validation = None
    result_df = None

    for attempt in range(0, 3):
        validation = validate_sql(sql, session.tables)

        if not validation.is_valid:
            last_error = "Validation failed: " + "; ".join(validation.issues)
        else:
            try:
                result_df = session.execute(sql)
                last_error = None
                break
            except Exception as e:
                last_error = e

        if attempt >= 2:
            break

        # build repair prompt from whichever kind of failure just happened
        repair_prompt = (
            system_prompt
            + "\n\nUser question: "
            + question
            + "\n\nPreviously generated SQL: "
            + (sql or "")
            + "\n\nThis SQL failed with the following problem:\n"
            + str(last_error)
            + "\n\nPlease return a corrected SQL query in the same JSON format: {\"sql\": \"...\", \"explanation\": \"...\", \"assumptions\": \"\", \"clarification_needed\": \"\"}. Reply only with JSON."
        )
        try:
            repair_raw = await llm_service.generate_raw(repair_prompt, temperature=0.0, max_tokens=1024)
            repaired_sql, repaired_explanation, repaired_clarification = _parse_llm_response(repair_raw)
            if repaired_sql:
                sql = repaired_sql
                explanation = repaired_explanation or explanation
                clarification = repaired_clarification or clarification
                continue
            else:
                from llm.utils import extract_sql as _extract_sql

                candidate = _extract_sql(repair_raw or "")
                if candidate:
                    sql = candidate
                    continue
                # repair produced nothing usable — stop retrying, keep last_error
                break
        except Exception:
            # repair call itself failed — stop retrying, keep last_error
            break

    # Note: do not close the global llm_service here; lifecycle is handled by app shutdown.

    if last_error is not None or result_df is None:
        prefix = "Generated SQL failed validation" if isinstance(last_error, str) else "SQL execution failed after retries"
        return _error_result(question, sql, f"{prefix}: {last_error}")

    elapsed_ms = (time.perf_counter() - t_start) * 1000

    truncated = len(result_df) > max_rows
    if truncated:
        result_df = result_df.head(max_rows)

    # Clean NaN → None for JSON serialisation
    result_df = result_df.where(pd.notnull(result_df), None)

    # ── Step 5: Suggest visualization ───────────────────────────
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
    """
    Execute a raw SQL query directly (no LLM translation).
    Used by the SQL editor in the frontend.
    """
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

def _error_result(question: str, sql: Optional[str], error: str) -> QueryResult:
    """Build a QueryResult representing a failed query.

    `sql` may legitimately be None here — e.g. when the question wasn't a
    data question at all ("who are u") and Gemini returned no SQL, or asked
    for clarification instead. QueryResult.sql is a required str field, so
    None must be coerced to "" or pydantic raises a ValidationError that
    turns this "friendly error response" path into an unhandled 500.
    """
    return QueryResult(
        session_id="",
        question=question,
        sql=sql or "",
        sql_explanation="",
        columns=[],
        rows=[],
        row_count=0,
        truncated=False,
        execution_time_ms=0,
        viz_suggestion=None,
        error=error,
    )