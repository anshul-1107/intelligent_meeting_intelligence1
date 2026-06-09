"""
Intelligent Meeting Intelligence & Escalation Tracking System
FastAPI Application Entry Point
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
import os

from config import settings
from database import init_db
from routers import meetings, query, stats, items, extract, listing


# ── Lifespan (startup / shutdown) ─────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialise database tables
    await init_db()
    print("✅  Database initialised")
    print(f"🚀  Meeting Intelligence API running on http://{settings.app_host}:{settings.app_port}")
    yield
    # Shutdown: nothing special needed for SQLite
    print("👋  Shutting down...")


# ── App Instance ──────────────────────────────────────────────────────────────
app = FastAPI(
    title="Intelligent Meeting Intelligence & Escalation Tracking",
    description=(
        "AI-powered system that extracts tasks, escalations, risks, and decisions "
        "from meeting transcripts using Google Gemini."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)


# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health Check ──────────────────────────────────────────────────────────────
@app.get("/health", tags=["health"])
async def health():
    """Health probe — returns {"status": "ok"}"""
    return {"status": "ok"}


# ── API Routers ───────────────────────────────────────────────────────────────
app.include_router(meetings.router)
app.include_router(extract.router)   # POST /api/extract
app.include_router(query.router)     # POST /api/query
app.include_router(listing.router)   # GET  /api/tasks, /api/escalations, /api/risks
app.include_router(stats.router)
app.include_router(items.router)


# ── Serve Frontend (static files) ─────────────────────────────────────────────
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")

if os.path.isdir(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="static")
