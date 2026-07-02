"""
DataGenie AI — FastAPI Backend
Entry point. Mounts all routers.
"""

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import ingest, clean, export, sql, rag  # ← add sql, rag

load_dotenv()

app = FastAPI(
    title="DataGenie AI",
    description="AI-powered data cleaning, SQL generation, and analysis engine.",
    version="1.0.0",
)

# ── CORS (React dev server runs on :3000) ──────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://datagenie-eight.vercel.app",
        "https://datageniee.vercel.app",
        "http://localhost:5173",
        "http://localhost:3000",
    ],
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