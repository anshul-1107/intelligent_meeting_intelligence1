"""
GET /api/tasks        — list all tasks with optional filters
GET /api/escalations  — list all escalations with optional filters
GET /api/risks        — list all risks with optional filters

Each endpoint supports:
  - owner       filter by owner name (case-insensitive substring)
  - status      filter by status value (tasks: open/in_progress/done/cancelled,
                                        escalations: open/acknowledged/resolved)
  - priority    filter by priority   (tasks only: low/medium/high/critical)
  - severity    filter by severity   (escalations only: low/medium/high/critical)
  - impact      filter by impact     (risks only: low/medium/high/critical)
  - likelihood  filter by likelihood (risks only: low/medium/high)
  - meeting_id  filter to a single meeting
  - skip/limit  pagination
"""

from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import get_db, Task, Escalation, Risk
from schemas import TaskResponse, EscalationResponse, RiskResponse

router = APIRouter(tags=["listing"])


# ── GET /api/tasks ────────────────────────────────────────────────────────────
@router.get(
    "/api/tasks",
    response_model=list[TaskResponse],
    summary="List all tasks",
    description=(
        "Returns all extracted tasks across every meeting. "
        "Filter by `owner`, `status`, `priority`, or `meeting_id`."
    ),
)
async def list_tasks(
    owner:      Optional[str] = Query(None, description="Filter by owner name (substring, case-insensitive)"),
    status:     Optional[str] = Query(None, description="open | in_progress | done | cancelled"),
    priority:   Optional[str] = Query(None, description="low | medium | high | critical"),
    meeting_id: Optional[str] = Query(None, description="Restrict to a single meeting"),
    skip:       int           = Query(0,    ge=0,   description="Pagination offset"),
    limit:      int           = Query(100,  ge=1, le=500, description="Max rows to return"),
    db: AsyncSession = Depends(get_db),
) -> list[TaskResponse]:

    q = select(Task)

    if owner:
        q = q.where(Task.owner.ilike(f"%{owner}%"))
    if status:
        q = q.where(Task.status == status)
    if priority:
        q = q.where(Task.priority == priority)
    if meeting_id:
        q = q.where(Task.meeting_id == meeting_id)

    q = q.order_by(Task.created_at.desc()).offset(skip).limit(limit)
    rows = (await db.execute(q)).scalars().all()
    return [TaskResponse.model_validate(r) for r in rows]


# ── GET /api/escalations ──────────────────────────────────────────────────────
@router.get(
    "/api/escalations",
    response_model=list[EscalationResponse],
    summary="List all escalations",
    description=(
        "Returns all extracted escalations across every meeting. "
        "Filter by `owner`, `status`, `severity`, or `meeting_id`."
    ),
)
async def list_escalations(
    owner:      Optional[str] = Query(None, description="Filter by owner name (substring, case-insensitive)"),
    status:     Optional[str] = Query(None, description="open | acknowledged | resolved"),
    severity:   Optional[str] = Query(None, description="low | medium | high | critical"),
    meeting_id: Optional[str] = Query(None, description="Restrict to a single meeting"),
    skip:       int           = Query(0,    ge=0,   description="Pagination offset"),
    limit:      int           = Query(100,  ge=1, le=500, description="Max rows to return"),
    db: AsyncSession = Depends(get_db),
) -> list[EscalationResponse]:

    q = select(Escalation)

    if owner:
        q = q.where(Escalation.owner.ilike(f"%{owner}%"))
    if status:
        q = q.where(Escalation.status == status)
    if severity:
        q = q.where(Escalation.severity == severity)
    if meeting_id:
        q = q.where(Escalation.meeting_id == meeting_id)

    q = q.order_by(Escalation.created_at.desc()).offset(skip).limit(limit)
    rows = (await db.execute(q)).scalars().all()
    return [EscalationResponse.model_validate(r) for r in rows]


# ── GET /api/risks ────────────────────────────────────────────────────────────
@router.get(
    "/api/risks",
    response_model=list[RiskResponse],
    summary="List all risks",
    description=(
        "Returns all extracted risks across every meeting. "
        "Filter by `owner`, `impact`, `likelihood`, or `meeting_id`."
    ),
)
async def list_risks(
    owner:      Optional[str] = Query(None, description="Filter by owner name (substring, case-insensitive)"),
    impact:     Optional[str] = Query(None, description="low | medium | high | critical"),
    likelihood: Optional[str] = Query(None, description="low | medium | high"),
    meeting_id: Optional[str] = Query(None, description="Restrict to a single meeting"),
    skip:       int           = Query(0,    ge=0,   description="Pagination offset"),
    limit:      int           = Query(100,  ge=1, le=500, description="Max rows to return"),
    db: AsyncSession = Depends(get_db),
) -> list[RiskResponse]:

    q = select(Risk)

    if owner:
        q = q.where(Risk.owner.ilike(f"%{owner}%"))
    if impact:
        q = q.where(Risk.impact == impact)
    if likelihood:
        q = q.where(Risk.likelihood == likelihood)
    if meeting_id:
        q = q.where(Risk.meeting_id == meeting_id)

    q = q.order_by(Risk.created_at.desc()).offset(skip).limit(limit)
    rows = (await db.execute(q)).scalars().all()
    return [RiskResponse.model_validate(r) for r in rows]
