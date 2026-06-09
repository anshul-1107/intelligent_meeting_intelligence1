"""
Meetings router — CRUD + AI-powered ingestion.
"""

import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete

from database import get_db, Meeting, Task, Escalation, Risk, Decision
from schemas import (
    MeetingCreate,
    MeetingResponse,
    MeetingDetailResponse,
    MeetingListItem,
    TaskResponse,
    EscalationResponse,
    RiskResponse,
    DecisionResponse,
)
from ai_engine import extract_intelligence

router = APIRouter(prefix="/api/meetings", tags=["meetings"])


# ── POST /api/meetings — ingest transcript ────────────────────────────────────
@router.post("/", response_model=MeetingDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_meeting(payload: MeetingCreate, db: AsyncSession = Depends(get_db)):
    """
    Accept a meeting title + transcript.
    Extract intelligence via Claude, store everything, return full detail.
    """
    # 1. AI extraction
    try:
        intel = await extract_intelligence(payload.transcript)
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI extraction failed: {str(e)}")

    meeting_id = str(uuid.uuid4())

    # 2. Persist meeting
    meeting = Meeting(
        id=meeting_id,
        title=payload.title,
        transcript=payload.transcript,
        summary=intel.summary,
    )
    db.add(meeting)

    # 3. Persist extracted items
    task_rows, escalation_rows, risk_rows, decision_rows = [], [], [], []

    for t in intel.tasks:
        row = Task(id=str(uuid.uuid4()), meeting_id=meeting_id, **t.model_dump())
        db.add(row)
        task_rows.append(row)

    for e in intel.escalations:
        row = Escalation(id=str(uuid.uuid4()), meeting_id=meeting_id, **e.model_dump())
        db.add(row)
        escalation_rows.append(row)

    for r in intel.risks:
        row = Risk(id=str(uuid.uuid4()), meeting_id=meeting_id, **r.model_dump())
        db.add(row)
        risk_rows.append(row)

    for d in intel.decisions:
        row = Decision(id=str(uuid.uuid4()), meeting_id=meeting_id, **d.model_dump())
        db.add(row)
        decision_rows.append(row)

    await db.commit()
    await db.refresh(meeting)

    return MeetingDetailResponse(
        **MeetingResponse.model_validate(meeting).model_dump(),
        tasks=[TaskResponse.model_validate(t) for t in task_rows],
        escalations=[EscalationResponse.model_validate(e) for e in escalation_rows],
        risks=[RiskResponse.model_validate(r) for r in risk_rows],
        decisions=[DecisionResponse.model_validate(d) for d in decision_rows],
    )


# ── GET /api/meetings — list all ─────────────────────────────────────────────
@router.get("/", response_model=list[MeetingListItem])
async def list_meetings(
    skip: int = 0, limit: int = 50, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Meeting).order_by(Meeting.created_at.desc()).offset(skip).limit(limit)
    )
    meetings = result.scalars().all()

    items = []
    for m in meetings:
        task_count = (await db.execute(
            select(func.count()).where(Task.meeting_id == m.id)
        )).scalar_one()
        esc_count = (await db.execute(
            select(func.count()).where(Escalation.meeting_id == m.id)
        )).scalar_one()
        risk_count = (await db.execute(
            select(func.count()).where(Risk.meeting_id == m.id)
        )).scalar_one()
        dec_count = (await db.execute(
            select(func.count()).where(Decision.meeting_id == m.id)
        )).scalar_one()

        items.append(MeetingListItem(
            id=m.id, title=m.title, summary=m.summary, created_at=m.created_at,
            task_count=task_count, escalation_count=esc_count,
            risk_count=risk_count, decision_count=dec_count,
        ))
    return items


# ── GET /api/meetings/{id} — detail ──────────────────────────────────────────
@router.get("/{meeting_id}", response_model=MeetingDetailResponse)
async def get_meeting(meeting_id: str, db: AsyncSession = Depends(get_db)):
    meeting = await db.get(Meeting, meeting_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    tasks       = (await db.execute(select(Task).where(Task.meeting_id == meeting_id))).scalars().all()
    escalations = (await db.execute(select(Escalation).where(Escalation.meeting_id == meeting_id))).scalars().all()
    risks       = (await db.execute(select(Risk).where(Risk.meeting_id == meeting_id))).scalars().all()
    decisions   = (await db.execute(select(Decision).where(Decision.meeting_id == meeting_id))).scalars().all()

    return MeetingDetailResponse(
        **MeetingResponse.model_validate(meeting).model_dump(),
        tasks=[TaskResponse.model_validate(t) for t in tasks],
        escalations=[EscalationResponse.model_validate(e) for e in escalations],
        risks=[RiskResponse.model_validate(r) for r in risks],
        decisions=[DecisionResponse.model_validate(d) for d in decisions],
    )


# ── DELETE /api/meetings/{id} ─────────────────────────────────────────────────
@router.delete("/{meeting_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_meeting(meeting_id: str, db: AsyncSession = Depends(get_db)):
    meeting = await db.get(Meeting, meeting_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    await db.delete(meeting)
    await db.commit()
