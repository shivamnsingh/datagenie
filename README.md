<div align="center">

# 🧞 DataGenie AI

**Turn messy CSVs into clean, queryable, explainable data — in one workflow.**

An AI-assisted data workspace that combines data profiling, guided cleaning, natural-language-to-SQL, analytical querying, visualization, and RAG-powered chat over your own datasets.

[**Live Demo**](https://datageniee.vercel.app/) · [API Docs](#api-surface) · [Architecture](#architecture) · [Run Locally](#run-locally)

![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)
![FastAPI](https://img.shields.io/badge/FastAPI-Python%203.13-009688?logo=fastapi&logoColor=white)
![DuckDB](https://img.shields.io/badge/DuckDB-Analytics-FFF000?logo=duckdb&logoColor=black)
![Gemini](https://img.shields.io/badge/Gemini-AI%20Powered-4285F4?logo=googlegemini&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-lightgrey)

</div>

---

## Overview

Most data analysis stalls before it starts — datasets show up with missing values, inconsistent types, duplicate rows, and unclear schemas, and turning a raw file into a trustworthy answer usually means writing the same transformations by hand every time.

**DataGenie AI** closes that gap. Upload a CSV, and it profiles the data, previews and applies cleaning operations, lets you ask questions in plain English (translated to validated SQL), run raw SQL against an in-memory analytical engine, visualize results, and export clean output — all from a single interface.

It's built as a full-stack, production-shaped project: FastAPI service layer, Pydantic-validated contracts, DuckDB analytics, LLM-generated SQL with a validation and repair loop, and a deployed React frontend.

---

## Why It's Interesting (Engineering-First)

This isn't a thin wrapper around an LLM — it's a system designed around one hard problem: **letting an AI write and execute SQL against user data without letting it break anything.**

- **Source-grounded Text-to-SQL** — Gemini receives the actual table schema alongside the user's question, and generated SQL is validated and automatically repaired when it's close but not quite right.
- **Read-only query safety** — SQL validation understands comments, string literals, CTE names, and scalar functions like `REPLACE()`, so it doesn't false-positive on legitimate read queries, while still hard-blocking `DROP`, `DELETE`, `INSERT`, and `UPDATE`.
- **Fast local analytics** — DuckDB runs joins, CTEs, aggregations, nested queries, and window functions directly over registered Pandas DataFrames, no external database required.
- **Clean service boundaries** — FastAPI routers own HTTP contracts, service modules own business logic, and Pydantic models own request/response schemas. Nothing crosses layers unchecked.
- **Resource-conscious by design** — DuckDB sessions are bounded with a TTL cache, and uploaded data is downcast where possible to control memory usage.
- **Deployment-ready from day one** — Render-configured backend with environment-based CORS, Vercel-configured frontend with build-time API URLs.

---

## Features

| Category | What it does |
| --- | --- |
| **Ingest & Profile** | Upload one or more CSVs, get instant schema, null, duplicate, and outlier insights |
| **Guided Cleaning** | Preview changes before applying — missing values, outliers, type conversions, whitespace, duplicates, column standardization — with before/after quality scores |
| **Natural-Language SQL** | Ask a question in plain English; Gemini generates SQL grounded in your actual schema |
| **Raw SQL Console** | Run validated, read-only SQL directly against DuckDB sessions |
| **Visualization** | Auto-suggested charts from query results — bar, line, pie, scatter, histogram, heatmap, table |
| **RAG Chat** | Chat with your dataset through a retrieval-augmented workflow over indexed context |
| **Export** | Download cleaned results as CSV, JSON, or XLSX |

---

## Architecture

```text
React + Vite frontend
        |
        | REST / JSON / multipart upload
        v
FastAPI backend
  |-- Ingest and schema profiling
  |-- Cleaning preview and apply services
  |-- DuckDB SQL sessions
  |-- SQL validation and repair loop
  |-- RAG indexing and chat
  |-- Export services
        |
        +--> Gemini API for natural-language analysis and SQL generation
        +--> Optional Voyage AI embeddings for RAG
```

## Tech Stack

| Layer | Technology |
| --- | --- |
| Frontend | React 18, Vite, Recharts, Tailwind CSS |
| Backend | Python 3.13, FastAPI, Uvicorn |
| Data Processing | Pandas, NumPy, SciPy |
| SQL Analytics | DuckDB |
| AI / LLM | Google Gemini API |
| Retrieval | Voyage AI embeddings (optional), with local fallback |
| Validation | Pydantic v2 |
| HTTP Client | HTTPX |
| Deployment | Vercel (frontend), Render (backend) |

---

## API Surface

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `POST` | `/api/ingest/upload` | Upload and profile CSV files |
| `GET` | `/api/ingest/preview/{file_id}` | Preview uploaded data |
| `POST` | `/api/clean/preview` | Preview cleaning changes |
| `POST` | `/api/clean/apply` | Apply cleaning operations |
| `POST` | `/api/sql/session` | Create a DuckDB query session |
| `POST` | `/api/sql/query` | Generate and execute SQL from a natural-language question |
| `POST` | `/api/sql/raw` | Execute validated read-only SQL |
| `GET` | `/api/sql/history/{session_id}` | Read query history |
| `POST` | `/api/rag/index` | Index dataset context |
| `POST` | `/api/rag/chat` | Ask questions about indexed data |
| `POST` | `/api/export/` | Export processed data |
| `GET` | `/health` | Service health check |

Interactive Swagger docs are available at `/docs` when running locally.

---

## Project Structure

```text
datagenie/
├── backend/
│   ├── main.py
│   ├── routers/           # HTTP endpoints
│   ├── services/          # Cleaning, SQL, schema, RAG, and export workflows
│   ├── models/             # Pydantic API schemas
│   ├── llm/                # Gemini provider and response handling
│   ├── utils/               # DuckDB sessions, storage, and vector store
│   └── requirements.txt
├── frontend/
│   ├── src/App.jsx
│   ├── src/components/    # Cleaning, SQL, chart, and RAG interfaces
│   └── src/services/        # API clients
├── render.yaml
└── sample_data.csv
```

---

## Run Locally

### Requirements

- Python 3.13+
- Node.js 18+
- A [Gemini API key](https://aistudio.google.com/app/apikey)
- (Optional) a Voyage AI key for production-quality embeddings

### 1. Backend

```powershell
cd backend
python -m pip install -r requirements.txt
```

Create `.env` in the repository root:

```dotenv
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-3.1-flash-lite
GEMINI_API_BASE=https://generativelanguage.googleapis.com/v1beta
GEMINI_TIMEOUT_S=30
VOYAGE_API_KEY=
```

Start the API:

```powershell
uvicorn main:app --reload --port 8000
```

- API: `http://127.0.0.1:8000`
- Swagger docs: `http://127.0.0.1:8000/docs`

### 2. Frontend

In a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Frontend: `http://127.0.0.1:3000`

To point at a different backend, set before building:

```dotenv
VITE_API_URL=https://your-backend-url.onrender.com
```

---

## Deployment

### Backend → Render

The repo includes [`render.yaml`](render.yaml). Set these environment variables in the Render service:

```text
GEMINI_API_KEY=your_new_gemini_api_key
GEMINI_MODEL=gemini-3.1-flash-lite
CORS_ORIGINS=https://datageniee.vercel.app
```

> Keep the Gemini key in Render's secret environment settings — never commit it or expose it as a Vercel frontend variable.

### Frontend → Vercel

| Setting | Value |
| --- | --- |
| Root directory | `frontend` |
| Build command | `npm run build` |
| Output directory | `dist` |
| Env variable | `VITE_API_URL=https://your-backend-url.onrender.com` |

After deployment, set the exact Vercel domain in the backend's `CORS_ORIGINS` and redeploy.

---

## Design Principles

DataGenie is built around **trustworthy AI-assisted analysis**, not just AI convenience:

1. **Inspect before transforming** — every dataset is profiled before any cleaning happens.
2. **Preview before applying** — cleaning changes are shown with before/after quality scores, never applied blind.
3. **Constrain generated SQL** — LLM output is treated as untrusted input and validated before it ever touches data.
4. **Validate before execution** — write operations are structurally blocked, not just prompted against.
5. **Secrets stay in deployment config** — API keys never live in the repo or the client bundle.

---

## About

DataGenie AI is a full-stack portfolio project exploring the practical gap between raw data and usable insight. It combines data engineering, backend API design, analytical SQL, LLM integration, retrieval-augmented generation, input validation, and cloud deployment into one end-to-end product.

## License

MIT License.