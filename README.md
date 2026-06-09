# 🧠 Intelligent Meeting Intelligence & Escalation Tracking System

AI-powered full-stack app that extracts tasks, escalations, risks, and decisions from meeting transcripts using **Anthropic Claude**, stores them in a database, and lets you query everything in natural language.

---

## 📁 Project Structure

```
Intelligent_Meeting_Intellgence/
├── backend/
│   ├── main.py          # FastAPI app entry point
│   ├── config.py        # Settings / env vars
│   ├── database.py      # SQLAlchemy models + async engine
│   ├── schemas.py       # Pydantic request/response schemas
│   ├── ai_engine.py     # Anthropic Claude integration
│   ├── requirements.txt
│   ├── .env.example
│   └── routers/
│       ├── meetings.py  # POST/GET/DELETE /api/meetings
│       ├── items.py     # PATCH tasks & escalations
│       ├── query.py     # POST /api/query (NL queries)
│       └── stats.py     # GET /api/stats
├── frontend/
│   ├── index.html       # Single-page app
│   ├── style.css        # Dark glassmorphism design
│   └── app.js           # SPA router + API client
└── database/
    └── schema.sql       # Raw SQL schema (reference)
```

---

## 🚀 Quick Start

### 1. Clone & Enter Directory

```bash
cd Intelligent_Meeting_Intellgence
```

### 2. Set Up the Backend

```bash
cd backend

# Create virtual environment
python3 -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# ✏️  Edit .env and add your ANTHROPIC_API_KEY
```

### 3. Run the Backend

```bash
# From the backend/ directory with venv active:
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

API is now running at **http://localhost:8000**
- Docs: http://localhost:8000/docs
- Health: http://localhost:8000/health

### 4. Open the Frontend

Open `frontend/index.html` directly in your browser, **or** use a simple server:

```bash
# From project root:
npx serve frontend -p 5500
# → open http://localhost:5500
```

---

## 🔑 Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | ✅ Yes | — | Your Anthropic API key |
| `DATABASE_URL` | No | SQLite (local) | DB connection string |
| `CORS_ORIGINS` | No | localhost ports | Allowed frontend origins |

---

## 🛠️ API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Health check → `{"status":"ok"}` |
| POST | `/api/meetings/` | Ingest transcript → AI extract → store |
| GET | `/api/meetings/` | List all meetings |
| GET | `/api/meetings/{id}` | Get meeting detail with all items |
| DELETE | `/api/meetings/{id}` | Delete meeting |
| PATCH | `/api/items/tasks/{id}` | Update task status/priority |
| PATCH | `/api/items/escalations/{id}` | Update escalation status |
| POST | `/api/query/` | Natural language query |
| GET | `/api/stats/` | Dashboard aggregate stats |

---

## 🧠 What Claude Extracts

Given any meeting transcript, Claude identifies:

| Category | What's captured |
|---|---|
| **Tasks** | Description, owner, deadline, priority, status |
| **Escalations** | Description, owner, severity, due date |
| **Risks** | Description, impact, likelihood, mitigation, owner |
| **Decisions** | Description, made by, rationale, date |

---

## 💬 Natural Language Query Examples

> "What tasks are assigned to Alice?"
> "Which escalations are critical and unresolved?"
> "What decisions were made about authentication?"
> "Who has the most open action items?"
> "Summarize all risks from last week's meetings"

---

## 🗄️ Switching to PostgreSQL

Update `.env`:

```
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/meeting_intelligence
```

Then install: `pip install asyncpg`
