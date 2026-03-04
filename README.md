# ⚡ DataGenie AI

An AI-powered data cleaning, SQL generation, and analysis platform. Upload your datasets, clean them interactively, query them in plain English, and get instant visualizations — all in one tool.

---

## 🧰 Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.13, FastAPI, Uvicorn |
| SQL Engine | DuckDB |
| Data Processing | Pandas, Scipy, NumPy |
| AI / LLM | Groq API (LLaMA 3.3 70B) |
| Embeddings | Voyage AI |
| Frontend | React, Vite |
| Validation | Pydantic v2 |
| HTTP Client | Httpx |
| Config | Python-dotenv |

---

## 🚀 Getting Started

### Prerequisites

- Python 3.13+
- Node.js 18+
- A free [Groq API key](https://console.groq.com)
- (Optional) A [Voyage AI key](https://dash.voyageai.com) for better RAG quality

---

### 1. Clone the repository

```bash
git clone https://github.com/your-username/datagenie.git
cd datagenie
```

### 2. Set up the backend

```bash
cd backend
pip install -r requirements.txt
```

### 3. Configure environment variables

Copy the example env file and fill in your keys:

```bash
cp .env.example .env
```

Edit `.env`:

```dotenv
GROQ_API_KEY=gsk_your_groq_key_here
VOYAGE_API_KEY=your_voyage_key_here   # optional
BACKEND_PORT=8000
FRONTEND_PORT=3000
```

> ⚠️ Never commit your `.env` file to version control.

### 4. Start the backend

```bash
cd backend
uvicorn main:app --reload --port 8000
```

Backend will be running at: `http://localhost:8000`  
API docs available at: `http://localhost:8000/docs`

### 5. Start the frontend

Open a new terminal:

```bash
cd frontend
npm install
npm run dev
```

Frontend will be running at: `http://localhost:5173`

---

## 📁 Project Structure

```
datagenie/
├── backend/
│   ├── main.py                  # FastAPI entry point
│   ├── requirements.txt
│   ├── .env                     # your secrets (never commit)
│   ├── routers/
│   │   ├── ingest.py            # file upload & schema detection
│   │   ├── clean.py             # data cleaning endpoints
│   │   ├── export.py            # CSV/JSON/XLSX export
│   │   ├── sql.py               # NL-to-SQL + raw SQL engine
│   │   └── rag.py               # RAG chat endpoints
│   ├── services/
│   │   ├── schema_service.py    # column profiling & type detection
│   │   ├── cleaning_service.py  # cleaning engine (preview + apply)
│   │   ├── sql_service.py       # Groq NL-to-SQL pipeline
│   │   └── sql_validator.py     # SQL safety validation
│   ├── models/
│   │   ├── schemas.py           # Pydantic models (ingest, clean, export)
│   │   └── sql_schemas.py       # Pydantic models (SQL, RAG)
│   └── utils/
│       ├── session_store.py     # in-memory DataFrame store
│       └── duck_session.py      # DuckDB session manager
└── frontend/
    ├── src/
    └── package.json
```

---

## ✨ Features

### 📤 Data Ingestion
- Upload CSV, JSON, or XLSX files
- Automatic column profiling (types, nulls, outliers, duplicates)
- Join suggestions across multiple uploaded files

### 🧹 Data Cleaning
- **Preview mode** — see exactly what will change before applying
- Null handling: drop rows, fill mean/median/mode/custom, forward/backward fill
- Outlier handling: IQR removal or percentile capping
- Type conversion: numeric, datetime, category
- Standardization: lowercase columns, trim whitespace, drop duplicates & constants
- Quality score before and after (0–100)

### ⚡ SQL Query Engine
- Natural language → SQL using Groq (LLaMA 3.3 70B), completely free
- Raw SQL editor for direct queries
- DuckDB execution engine — fast, in-memory
- Query history per session
- Auto-suggested visualizations (bar, line, pie, scatter, histogram)

### 🤖 RAG Chat
- Index your cleaned dataset for semantic search
- Ask questions in plain English and get data-grounded answers
- Powered by Voyage AI embeddings

### 📥 Export
- Export cleaned data as CSV, JSON, or XLSX

---

## 🔌 API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/ingest/upload` | Upload files |
| GET | `/api/ingest/preview/{file_id}` | Preview data |
| POST | `/api/clean/preview` | Dry-run cleaning |
| POST | `/api/clean/apply` | Apply cleaning |
| GET | `/api/clean/nulls/{file_id}` | Null report |
| GET | `/api/clean/outliers/{file_id}` | Outlier report |
| GET | `/api/clean/duplicates/{file_id}` | Duplicate report |
| POST | `/api/export/` | Export dataset |
| POST | `/api/sql/session` | Create SQL session |
| POST | `/api/sql/query` | Natural language query |
| POST | `/api/sql/raw` | Raw SQL query |
| GET | `/api/sql/history/{session_id}` | Query history |
| POST | `/api/rag/index` | Create RAG index |
| POST | `/api/rag/chat` | Chat with data |
| GET | `/health` | Health check |

Full interactive docs: `http://localhost:8000/docs`

---

## 🔑 Getting API Keys

**Groq (required, free):**
1. Sign up at https://console.groq.com
2. Go to API Keys → Create API Key
3. Add to `.env` as `GROQ_API_KEY`

**Voyage AI (optional, improves RAG quality):**
1. Sign up at https://dash.voyageai.com
2. Create an API key
3. Add to `.env` as `VOYAGE_API_KEY`

---

## ⚙️ Troubleshooting

**`ModuleNotFoundError: No module named 'duckdb'`**
```bash
pip install duckdb
```

**`404 Not Found` on `/api/sql/session` or `/api/rag/index`**  
Make sure all routers are registered in `main.py`:
```python
from routers import ingest, clean, export, sql, rag
app.include_router(sql.router, prefix="/api/sql", tags=["SQL"])
app.include_router(rag.router, prefix="/api/rag", tags=["RAG"])
```

**`Groq API error 401: Invalid API Key`**  
Regenerate your key at https://console.groq.com and update `.env`.

**Frontend not starting with `npm start`**  
This project uses Vite. Use `npm run dev` instead.

---

## 📄 License

MIT License — free to use, modify, and distribute.
