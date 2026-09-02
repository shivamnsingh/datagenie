"""
DataGenie AI — FastAPI Backend
Entry point. Mounts all routers.
"""

from pathlib import Path
import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Keep deployment-provided variables authoritative while supporting the repo-root .env.
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from routers import ingest, clean, export, sql, rag  # ← add sql, rag
from llm import llm_service

app = FastAPI(
    title="DataGenie AI",
    description="AI-powered data cleaning, SQL generation, and analysis engine.",
    version="1.0.0",
)

# ── CORS (React dev server runs on :3000) ──────────────────────────────────────
extra_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://datagenie-eight.vercel.app",
        "https://datageniee.vercel.app",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://localhost:3000",
    ] + extra_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ────────────────────────────────────────────────────────────────────
app.include_router(ingest.router,  prefix="/api/ingest",  tags=["Ingest"])
app.include_router(clean.router,   prefix="/api/clean",   tags=["Clean"])
app.include_router(export.router,  prefix="/api/export",  tags=["Export"])
app.include_router(sql.router,     prefix="/api/sql",     tags=["SQL"])    # ← add
app.include_router(rag.router,     prefix="/api/rag",     tags=["RAG"])    # ← add


@app.get("/health")
def health():
    return {"status": "ok", "service": "DataGenie AI"}


@app.get("/")
def root():
    return {"status": "ok", "service": "DataGenie AI"}


@app.on_event("shutdown")
async def _shutdown():
    """Gracefully close the global LLM service on application shutdown."""
    try:
        await llm_service.close()
    except Exception:
        pass