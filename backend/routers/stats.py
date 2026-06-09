"""
Stats router — aggregate counts for the dashboard.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from database import get_db, Meeting, Task, Escalation, Risk, Decision
from schemas import StatsResponse

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("/", response_model=StatsResponse)
async def get_stats(db: AsyncSession = Depends(get_db)):
    total_meetings    = (await db.execute(select(func.count(Meeting.id)))).scalar_one()
    total_tasks       = (await db.execute(select(func.count(Task.id)))).scalar_one()
    open_tasks        = (await db.execute(
        select(func.count(Task.id)).where(Task.status == "open")
    )).scalar_one()
    total_escalations = (await db.execute(select(func.count(Escalation.id)))).scalar_one()
    open_escalations  = (await db.execute(
        select(func.count(Escalation.id)).where(Escalation.status == "open")
    )).scalar_one()
    total_risks       = (await db.execute(select(func.count(Risk.id)))).scalar_one()
    total_decisions   = (await db.execute(select(func.count(Decision.id)))).scalar_one()

    return StatsResponse(
        total_meetings=total_meetings,
        total_tasks=total_tasks,
        open_tasks=open_tasks,
        total_escalations=total_escalations,
        open_escalations=open_escalations,
        total_risks=total_risks,
        total_decisions=total_decisions,
    )
