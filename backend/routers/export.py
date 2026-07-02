"""
routers/export.py
──────────────────
POST /api/export/  — download the cleaned dataset as CSV, JSON, or XLSX.
GET  /api/export/log/{file_id}  — download the cleaning audit log as JSON.
"""

from __future__ import annotations
import io
import json

import pandas as pd
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response, StreamingResponse

from models.schemas import ExportRequest
from utils.session_store import store

router = APIRouter()


@router.post("/")
def export_dataset(req: ExportRequest):
    df = store.load(req.file_id, copy=False)
    if df is None:
        raise HTTPException(status_code=404, detail=f"File ID '{req.file_id}' not found.")

    if req.format == "csv":
        buf = io.StringIO()
        df.to_csv(buf, index=False)
        buf.seek(0)
        return StreamingResponse(
            io.BytesIO(buf.getvalue().encode()),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=cleaned_data.csv"},
        )

    elif req.format == "json":
        payload = df.where(pd.notnull(df), None).to_json(orient="records", indent=2)
        return Response(
            content=payload,
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=cleaned_data.json"},
        )

    elif req.format == "xlsx":
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Cleaned Data")
        buf.seek(0)
        return StreamingResponse(
            buf,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=cleaned_data.xlsx"},
        )

    raise HTTPException(status_code=400, detail=f"Unsupported format: {req.format!r}")
