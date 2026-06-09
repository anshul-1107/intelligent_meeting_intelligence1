"""
Items router — update status/priority of tasks and escalations.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import get_db, Task, Escalation
from schemas import TaskResponse, TaskUpdate, EscalationResponse, EscalationUpdate

router = APIRouter(prefix="/api/items", tags=["items"])


# ── PATCH /api/items/tasks/{id} ───────────────────────────────────────────────
@router.patch("/tasks/{task_id}", response_model=TaskResponse)
async def update_task(task_id: str, payload: TaskUpdate, db: AsyncSession = Depends(get_db)):
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(task, field, value)

    await db.commit()
    await db.refresh(task)
    return TaskResponse.model_validate(task)


# ── PATCH /api/items/escalations/{id} ────────────────────────────────────────
@router.patch("/escalations/{escalation_id}", response_model=EscalationResponse)
async def update_escalation(
    escalation_id: str, payload: EscalationUpdate, db: AsyncSession = Depends(get_db)
):
    esc = await db.get(Escalation, escalation_id)
    if not esc:
        raise HTTPException(status_code=404, detail="Escalation not found")

    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(esc, field, value)

    await db.commit()
    await db.refresh(esc)
    return EscalationResponse.model_validate(esc)
