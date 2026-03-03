"""
routers/ingest.py
──────────────────
POST /api/ingest/upload  — upload one or more CSVs, get back schema reports + join suggestions.
GET  /api/ingest/preview/{file_id}  — get first 20 rows as JSON for the frontend table preview.
"""

from __future__ import annotations
import io
import uuid
from typing import List

import pandas as pd
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from models.schemas import IngestResponse, SchemaReport
from services.schema_service import build_schema_report, suggest_joins
from utils.session_store import store

router = APIRouter()


# ── Upload ─────────────────────────────────────────────────────────────────────

@router.post("/upload", response_model=IngestResponse)
async def upload_files(files: List[UploadFile] = File(...)):
    """
    Accept 1–N CSV files.
    Returns schema analysis for each file + cross-file join suggestions.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files provided.")

    schemas: List[SchemaReport] = []
    file_ids: List[str] = []

    for upload in files:
        if not upload.filename.endswith(".csv"):
            raise HTTPException(
                status_code=415,
                detail=f"'{upload.filename}' is not a CSV file. Only .csv files are supported.",
            )

        raw = await upload.read()
        try:
            df = pd.read_csv(io.BytesIO(raw))
        except Exception as e:
            raise HTTPException(
                status_code=422,
                detail=f"Could not parse '{upload.filename}': {e}",
            )

        if df.empty:
            raise HTTPException(
                status_code=422,
                detail=f"'{upload.filename}' is empty.",
            )

        file_id = str(uuid.uuid4())
        store.save(file_id, df)

        schema = build_schema_report(df, filename=upload.filename, file_id=file_id)
        schemas.append(schema)
        file_ids.append(file_id)

    join_suggestions = suggest_joins(schemas) if len(schemas) > 1 else []

    return IngestResponse(
        file_ids=file_ids,
        schemas=schemas,
        join_suggestions=join_suggestions,
    )


# ── Preview ────────────────────────────────────────────────────────────────────

@router.get("/preview/{file_id}")
def preview_data(file_id: str, rows: int = 20):
    """Return the first N rows of a dataset as JSON (for the frontend table)."""
    df = store.load(file_id)
    if df is None:
        raise HTTPException(status_code=404, detail=f"File ID '{file_id}' not found.")

    # Replace NaN with None so JSON serialises cleanly
    preview_df = df.head(rows).where(pd.notnull(df.head(rows)), None)

    return JSONResponse(content={
        "file_id": file_id,
        "row_count": len(df),
        "col_count": len(df.columns),
        "columns": list(df.columns),
        "rows": preview_df.to_dict(orient="records"),
    })
