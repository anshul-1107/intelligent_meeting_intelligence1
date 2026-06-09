from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from sqlalchemy.sql import func
from config import settings


# ── Engine & Session ──────────────────────────────────────────────────────────
engine = create_async_engine(
    settings.database_url,
    echo=(settings.app_env == "development"),
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ── Base Model ────────────────────────────────────────────────────────────────
class Base(DeclarativeBase):
    pass


# ── ORM Models ────────────────────────────────────────────────────────────────
class Meeting(Base):
    __tablename__ = "meetings"

    id         = Column(String, primary_key=True)
    title      = Column(String, nullable=False)
    transcript = Column(Text, nullable=False)
    summary    = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Task(Base):
    __tablename__ = "tasks"

    id          = Column(String, primary_key=True)
    meeting_id  = Column(String, ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False)
    description = Column(Text, nullable=False)
    owner       = Column(String)
    deadline    = Column(String)
    priority    = Column(String, default="medium")
    status      = Column(String, default="open")
    created_at  = Column(DateTime(timezone=True), server_default=func.now())


class Escalation(Base):
    __tablename__ = "escalations"

    id          = Column(String, primary_key=True)
    meeting_id  = Column(String, ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False)
    description = Column(Text, nullable=False)
    owner       = Column(String)
    severity    = Column(String, default="medium")
    status      = Column(String, default="open")
    due_date    = Column(String)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())


class Risk(Base):
    __tablename__ = "risks"

    id          = Column(String, primary_key=True)
    meeting_id  = Column(String, ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False)
    description = Column(Text, nullable=False)
    impact      = Column(String, default="medium")
    likelihood  = Column(String, default="medium")
    mitigation  = Column(Text)
    owner       = Column(String)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())


class Decision(Base):
    __tablename__ = "decisions"

    id          = Column(String, primary_key=True)
    meeting_id  = Column(String, ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False)
    description = Column(Text, nullable=False)
    made_by     = Column(String)
    rationale   = Column(Text)
    decided_at  = Column(String)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())


# ── DB Init ───────────────────────────────────────────────────────────────────
async def init_db():
    """Create all tables on startup."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# ── Dependency ────────────────────────────────────────────────────────────────
async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
