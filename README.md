# DataGenie AI

DataGenie is an AI-assisted data workspace that turns raw CSV files into clean, queryable, explainable datasets. Users can upload data, inspect its quality, apply cleaning operations, ask questions in natural language, run SQL, explore visualizations, and export the result from one workflow.

**Live application:** [datageniee.vercel.app](https://datageniee.vercel.app/)

## Why This Project

Data analysis often breaks down before analysis begins: datasets contain missing values, inconsistent types, duplicate records, outliers, and unclear schemas. DataGenie brings data preparation and exploration together so users can move from an uploaded CSV to a defensible answer without writing every transformation by hand.

## Product Highlights

- Upload one or more CSV files and receive schema, quality, null, duplicate, and outlier insights.
- Preview cleaning changes before applying them, with before-and-after quality scores.
- Handle missing values, outliers, type conversions, whitespace, duplicate rows, and column standardization.
- Ask natural-language questions and translate them into SQL with Gemini.
- Execute raw SQL against in-memory DuckDB sessions for joins, CTEs, aggregations, nested queries, and window functions.
- Validate generated SQL before execution and block write operations such as `DROP`, `DELETE`, `INSERT`, and `UPDATE`.
- Suggest visualizations from query results using bar, line, pie, scatter, histogram, heatmap, and table views.
- Chat with indexed dataset context through a retrieval-augmented generation workflow.
- Export cleaned results as CSV, JSON, or XLSX.

## Engineering Highlights

- **Source-grounded Text-to-SQL:** Gemini receives the active table schema and user question, then generated SQL is validated and automatically repaired when possible.
- **Read-only query safety:** SQL validation is aware of comments, literals, CTE names, scalar functions such as `REPLACE()`, and complex read-only query structures while continuing to reject write statements.
- **Fast local analytics:** DuckDB runs analytical SQL over registered Pandas DataFrames without requiring a separate database server.
- **Clear service boundaries:** FastAPI routers handle HTTP contracts, service modules own business workflows, and Pydantic models define request and response schemas.
- **Resource-conscious sessions:** DuckDB connections are bounded with a TTL cache, and uploaded data is downcast where possible to reduce memory usage.
- **Deployment-ready configuration:** The backend supports Render environment variables and configurable CORS origins; the frontend uses a build-time API URL for Vercel deployment.

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

| Area | Technology |
| --- | --- |
| Frontend | React 18, Vite, Recharts, Tailwind CSS |
| Backend | Python 3.13, FastAPI, Uvicorn |
| Data processing | Pandas, NumPy, SciPy |
| SQL analytics | DuckDB |
| AI | Google Gemini API |
| Retrieval | Optional Voyage AI embeddings with local fallback |
| Validation | Pydantic v2 |
| HTTP | HTTPX |
| Deployment | Vercel frontend, Render backend |

## Run Locally

### Requirements

- Python 3.13+
- Node.js 18+
- A Gemini API key from [Google AI Studio](https://aistudio.google.com/app/apikey)
- Optional Voyage AI key for production-quality embeddings

### Backend

From the repository root:

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

The API is available at `http://127.0.0.1:8000` and its interactive documentation is at `http://127.0.0.1:8000/docs`.

### Frontend

In a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

The frontend is available at `http://127.0.0.1:3000`.

For a different backend URL, set this Vite variable before building:

```dotenv
VITE_API_URL=https://your-backend-url.onrender.com
```

## Deploy

### Backend on Render

The repository includes [render.yaml](render.yaml). Configure these environment variables in the Render service:

```text
GEMINI_API_KEY=your_new_gemini_api_key
GEMINI_MODEL=gemini-3.1-flash-lite
CORS_ORIGINS=https://datageniee.vercel.app
```

Keep the Gemini key in Render's secret environment settings. Never commit it to the repository or expose it as a Vercel frontend variable.

### Frontend on Vercel

- Root directory: `frontend`
- Build command: `npm run build`
- Output directory: `dist`
- Environment variable: `VITE_API_URL=https://your-backend-url.onrender.com`

After deployment, set the exact Vercel domain in the backend's `CORS_ORIGINS` value and redeploy the backend.

## API Surface

| Method | Endpoint | Purpose |
| --- | --- | --- |
| POST | `/api/ingest/upload` | Upload and profile CSV files |
| GET | `/api/ingest/preview/{file_id}` | Preview uploaded data |
| POST | `/api/clean/preview` | Preview cleaning changes |
| POST | `/api/clean/apply` | Apply cleaning operations |
| POST | `/api/sql/session` | Create a DuckDB query session |
| POST | `/api/sql/query` | Generate and execute SQL from a question |
| POST | `/api/sql/raw` | Execute validated read-only SQL |
| GET | `/api/sql/history/{session_id}` | Read query history |
| POST | `/api/rag/index` | Index dataset context |
| POST | `/api/rag/chat` | Ask questions about indexed data |
| POST | `/api/export/` | Export processed data |
| GET | `/health` | Service health check |

## Project Structure

```text
datagenie/
|-- backend/
|   |-- main.py
|   |-- routers/              # HTTP endpoints
|   |-- services/             # Cleaning, SQL, schema, RAG, and export workflows
|   |-- models/               # Pydantic API schemas
|   |-- llm/                  # Gemini provider and response handling
|   |-- utils/                # DuckDB sessions, storage, and vector store
|   `-- requirements.txt
|-- frontend/
|   |-- src/App.jsx
|   |-- src/components/       # Cleaning, SQL, chart, and RAG interfaces
|   |-- src/services/         # API clients
|   `-- package.json
|-- render.yaml
`-- sample_data.csv
```

## About

DataGenie AI is a full-stack portfolio project focused on the practical gap between raw data and useful insight. It combines data engineering, backend API design, analytical SQL, LLM integration, retrieval, validation, and cloud deployment in one end-to-end product.

The project demonstrates an engineering approach centered on trustworthy results: inspect data before transformation, preview changes before applying them, constrain generated SQL, validate queries before execution, and keep secrets in deployment-managed environments.

## License

MIT License.
