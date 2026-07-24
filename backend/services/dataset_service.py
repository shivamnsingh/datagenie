from __future__ import annotations

from datetime import datetime
from typing import List, Optional

import pandas as pd

from models.schemas import DatasetUnderstanding
from services.schema_service import build_schema_report


def _detect_business_domain(columns: List[str]) -> Optional[str]:
    cols = [c.lower() for c in columns]
    if any(k in cols for k in ("order_id", "order", "product", "price", "customer", "quantity", "revenue")):
        return "Retail / E-commerce"
    if any(k in cols for k in ("sensor", "timestamp", "device", "reading")):
        return "IoT / Sensor"
    if any(k in cols for k in ("user_id", "event", "session", "timestamp")):
        return "Web Analytics"
    return "General"


def _suggest_kpis(columns: List[str]) -> List[str]:
    cols = [c.lower() for c in columns]
    kpis = []
    if any(k in cols for k in ("price", "revenue", "amount", "total")):
        kpis.extend(["Total Revenue", "Average Order Value", "Revenue by Category"])
    if any(k in cols for k in ("order_id", "transaction_id")):
        kpis.append("Number of Orders")
    if any(k in cols for k in ("customer", "customer_id")):
        kpis.append("Repeat Customer Rate")
    return kpis or ["Row count", "Column completeness"]


def _suggest_questions(columns: List[str]) -> List[str]:
    cols = [c.lower() for c in columns]
    questions = ["Show top 10 products by revenue", "Monthly revenue trend"]
    if any(k in cols for k in ("customer",)):
        questions.append("Top 10 customers by spending")
    if any(k in cols for k in ("region", "country", "state")):
        questions.append("Sales by region")
    return questions


def generate_dataset_understanding(df: pd.DataFrame, filename: str, file_id: str) -> DatasetUnderstanding:
    """Generate and return a DatasetUnderstanding object and cache it to disk."""
    schema = build_schema_report(df, filename, file_id=file_id)

    numeric_cols = [c.name for c in schema.columns if c.is_numeric]
    date_cols = [c.name for c in schema.columns if c.is_datetime]
    cat_cols = [c.name for c in schema.columns if c.is_categorical]

    domain = _detect_business_domain([c.name for c in schema.columns])
    kpis = _suggest_kpis([c.name for c in schema.columns])
    questions = _suggest_questions([c.name for c in schema.columns])

    # Simple interesting relationships: shared column names across schema (joins)
    relationships = []
    # For single dataset, we can suggest correlations
    try:
        df_num = df.select_dtypes(include="number")
        if df_num.shape[1] >= 2:
            corr = df_num.corr().abs().unstack().dropna()
            corr = corr[corr < 1].sort_values(ascending=False).head(5)
            for (a, b), v in corr.items():
                relationships.append(f"{a} ↔ {b}: r={v:.2f}")
    except Exception:
        pass

    insights = [
        f"Dataset appears to be {domain}.",
        f"{schema.row_count:,} rows, {schema.col_count} columns."
    ]

    recommended_analyses = ["Time series analysis", "Top-N analysis", "Cohort analysis"]

    out = DatasetUnderstanding(
        file_id=file_id,
        title=filename,
        business_domain=domain,
        description=None,
        row_count=schema.row_count,
        col_count=schema.col_count,
        numeric_columns=numeric_cols,
        categorical_columns=cat_cols,
        date_columns=date_cols,
        target_candidates=[c for c in numeric_cols][:3],
        suggested_kpis=kpis,
        interesting_relationships=relationships,
        business_insights=insights,
        recommended_analyses=recommended_analyses,
        suggested_questions=questions,
        generated_at=datetime.utcnow().isoformat() + "Z",
    )

    # Cache
    try:
        import json
        from pathlib import Path
        p = Path('.data')
        p.mkdir(exist_ok=True)
        with (p / f"dataset_understanding_{file_id}.json").open('w', encoding='utf-8') as f:
            json.dump(json.loads(out.json()), f, indent=2)
    except Exception:
        pass

    return out
