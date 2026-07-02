"""
routers/ingest.py
──────────────────
POST /api/ingest/upload  — upload one or more CSVs, get back schema reports + join suggestions.
GET  /api/ingest/preview/{file_id}  — get first 20 rows as JSON for the frontend table preview.
"""

from __future__ import annotations
import gc
import os
import platform
import ctypes
import uuid
from typing import List

import pandas as pd
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from models.schemas import IngestResponse, SchemaReport
from services.schema_service import build_schema_report, suggest_joins
from utils.session_store import store

router = APIRouter()


_MB = 1024 * 1024


def _process_memory_mb() -> float:
    """Best-effort process RSS in MB across Render Linux and local Windows."""
    try:
        import resource

        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if platform.system().lower() == "darwin":
            return rss / _MB
        return rss / 1024.0
    except Exception:
        pass

    if os.name == "nt":
        class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_ulong),
                ("PageFaultCount", ctypes.c_ulong),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
        handle = ctypes.windll.kernel32.GetCurrentProcess()
        if ctypes.windll.psapi.GetProcessMemoryInfo(
            handle,
            ctypes.byref(counters),
            counters.cb,
        ):
            return counters.WorkingSetSize / _MB

    return 0.0


def _downcast_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Reduce DataFrame memory footprint without changing API payloads."""
    for col in df.select_dtypes(include=["integer", "floating"]).columns:
        try:
            df[col] = pd.to_numeric(df[col], downcast="integer" if pd.api.types.is_integer_dtype(df[col]) else "float")
        except Exception:
            continue

    object_cols = df.select_dtypes(include="object").columns
    for col in object_cols:
        series = df[col]
        if len(df) > 100_000:
            sample = series.head(100)
            sample = sample[sample.notna()]
            if sample.empty:
                continue
            unique_count = int(sample.nunique(dropna=True))
            unique_ratio = unique_count / max(len(sample), 1)
        else:
            non_null = series.dropna()
            if non_null.empty:
                continue
            unique_count = int(non_null.nunique(dropna=True))
            unique_ratio = unique_count / max(len(non_null), 1)

        if unique_count <= 1000 and unique_ratio <= 0.5:
            df[col] = df[col].astype("category")

    return df


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

    print(f"[ingest] memory before upload processing: {_process_memory_mb():.1f} MB")

    for upload in files:
        if not upload.filename.endswith(".csv"):
            raise HTTPException(
                status_code=415,
                detail=f"'{upload.filename}' is not a CSV file. Only .csv files are supported.",
            )

        try:
            file_size = getattr(upload, "size", None)
            if file_size is None:
                current_pos = upload.file.tell()
                upload.file.seek(0, os.SEEK_END)
                file_size = upload.file.tell()
                upload.file.seek(current_pos)

            if file_size > 25 * _MB:
                raise HTTPException(
                    status_code=413,
                    detail=f"'{upload.filename}' exceeds the 25 MB upload limit.",
                )

            upload.file.seek(0)
            preview_df = pd.read_csv(upload.file, nrows=300_001)
            if len(preview_df) > 300_000:
                raise HTTPException(
                    status_code=413,
                    detail=f"'{upload.filename}' exceeds the 300,000 row limit.",
                )

            del preview_df
            gc.collect()

            upload.file.seek(0)
            df = pd.read_csv(upload.file)
            df = _downcast_dataframe(df)
        except Exception as e:
            if isinstance(e, HTTPException):
                raise
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

        del df
        gc.collect()

    print(f"[ingest] memory after upload processing: {_process_memory_mb():.1f} MB")

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
    df = store.load(file_id, copy=False)
    if df is None:
        raise HTTPException(status_code=404, detail=f"File ID '{file_id}' not found.")

    # Replace NaN with None so JSON serialises cleanly
    preview_df = df.head(rows)
    preview_df = preview_df.where(pd.notnull(preview_df), None)

    return JSONResponse(content={
        "file_id": file_id,
        "row_count": len(df),
        "col_count": len(df.columns),
        "columns": list(df.columns),
        "rows": preview_df.to_dict(orient="records"),
    })
