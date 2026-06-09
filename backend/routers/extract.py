"""
POST /api/extract
─────────────────────────────────────────────────────────────────────────────
The core extraction endpoint.

Flow:
  1.  Accept { text, title?, save_to_db? }
  2.  Send text to Claude with a strict JSON-only prompt
  3.  Parse & validate the four categories: tasks, escalations, risks, decisions
  4.  (Optionally) persist everything to the database
  5.  Return the full structured extraction + raw Claude output

Design notes:
  - Uses run_extraction() from ai_engine, which returns BOTH the raw dict AND
    the validated pydantic model, so the response can expose raw_claude_output
    for complete transparency.
  - DB persistence is transactional: all-or-nothing per meeting.
  - save_to_db=False is useful for preview / dry-run mode from the frontend.
  - Duplicate protection: if the same title + first 200 chars of text were
    already stored, the endpoint returns a 409 with the existing meeting_id
    so callers can decide whether to proceed.
"""

import uuid
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import get_db, Meeting, Task, Escalation, Risk, Decision
from schemas import (
    ExtractionRequest,
    ExtractionResponse,
    ExtractionCounts,
    TaskResponse,
    EscalationResponse,
    RiskResponse,
    DecisionResponse,
)
from ai_engine import run_extraction

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/extract", tags=["extract"])


# ── Helper: auto-generate a meeting title from the transcript ─────────────────
def _auto_title(text: str) -> str:
    """
    Build a sensible fallback title when the caller doesn't provide one.
    Takes the first non-empty line, trimmed to 60 characters.
    """
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line[:60] + ("…" if len(line) > 60 else "")
    return "Untitled Meeting"


# ── Main endpoint ─────────────────────────────────────────────────────────────
@router.post(
    "/",
    response_model=ExtractionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Extract intelligence from raw meeting text",
    description=(
        "Send raw meeting notes or a transcript. "
        "Claude analyses the text and returns structured JSON with "
        "**tasks**, **escalations**, **risks**, and **decisions** — "
        "each with owners, deadlines, priorities, and severity ratings. "
        "Optionally persists everything to the database."
    ),
    responses={
        201: {"description": "Extraction successful; data persisted (when save_to_db=True)"},
        409: {"description": "Duplicate detected — this transcript is already stored"},
        502: {"description": "Claude API error"},
        503: {"description": "ANTHROPIC_API_KEY not configured"},
    },
)
async def extract(
    payload: ExtractionRequest,
    db: AsyncSession = Depends(get_db),
) -> ExtractionResponse:

    # ── 1. Resolve title ──────────────────────────────────────────────────────
    title = (payload.title or _auto_title(payload.text)).strip()

    # ── 2. Duplicate guard (only when we intend to save) ─────────────────────
    if payload.save_to_db:
        fingerprint = payload.text[:200]
        existing = await db.execute(
            select(Meeting).where(
                Meeting.title == title,
                Meeting.transcript.startswith(fingerprint),
            )
        )
        dup = existing.scalar_one_or_none()
        if dup:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": "duplicate_transcript",
                    "message": (
                        "A meeting with this title and transcript is already stored. "
                        "Use the existing meeting or change the title."
                    ),
                    "existing_meeting_id": dup.id,
                },
            )

    # ── 3. Call Claude ────────────────────────────────────────────────────────
    logger.info("Starting Claude extraction for title='%s'", title)
    try:
        raw_data, intel = await run_extraction(payload.text)
    except ValueError as exc:
        # ANTHROPIC_API_KEY not set
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        logger.exception("Claude extraction failed")
        raise HTTPException(
            status_code=502,
            detail=f"Claude API error: {str(exc)}",
        )

    logger.info(
        "Extraction complete — tasks=%d escalations=%d risks=%d decisions=%d",
        len(intel.tasks), len(intel.escalations),
        len(intel.risks), len(intel.decisions),
    )

    # ── 4. Persist to DB (transactional) ─────────────────────────────────────
    meeting_id: str | None = None
    task_rows:        List[Task]       = []
    escalation_rows:  List[Escalation] = []
    risk_rows:        List[Risk]       = []
    decision_rows:    List[Decision]   = []

    if payload.save_to_db:
        meeting_id = str(uuid.uuid4())

        # Meeting record
        meeting = Meeting(
            id=meeting_id,
            title=title,
            transcript=payload.text,
            summary=intel.summary,
        )
        db.add(meeting)

        # Tasks
        for t in intel.tasks:
            row = Task(
                id=str(uuid.uuid4()),
                meeting_id=meeting_id,
                **t.model_dump(),
            )
            db.add(row)
            task_rows.append(row)

        # Escalations
        for e in intel.escalations:
            row = Escalation(
                id=str(uuid.uuid4()),
                meeting_id=meeting_id,
                **e.model_dump(),
            )
            db.add(row)
            escalation_rows.append(row)

        # Risks
        for r in intel.risks:
            row = Risk(
                id=str(uuid.uuid4()),
                meeting_id=meeting_id,
                **r.model_dump(),
            )
            db.add(row)
            risk_rows.append(row)

        # Decisions
        for d in intel.decisions:
            row = Decision(
                id=str(uuid.uuid4()),
                meeting_id=meeting_id,
                **d.model_dump(),
            )
            db.add(row)
            decision_rows.append(row)

        try:
            await db.commit()
            await db.refresh(meeting)
            logger.info("Meeting %s persisted successfully", meeting_id)
        except Exception as exc:
            await db.rollback()
            logger.exception("DB commit failed")
            raise HTTPException(
                status_code=500,
                detail=f"Database error while saving extraction: {str(exc)}",
            )

    # ── 5. Build & return the response ────────────────────────────────────────
    #
    # When save_to_db=False we convert the pydantic Create models to Response
    # models by injecting placeholder ids ("preview-<uuid>") so the schema
    # stays consistent.  The frontend can use these for display but must NOT
    # store or use these ids for further API calls.

    def _task_response(t, row: Task | None = None) -> TaskResponse:
        if row:
            return TaskResponse.model_validate(row)
        return TaskResponse(
            id=f"preview-{uuid.uuid4()}",
            meeting_id="preview",
            **t.model_dump(),
        )

    def _esc_response(e, row: Escalation | None = None) -> EscalationResponse:
        if row:
            return EscalationResponse.model_validate(row)
        return EscalationResponse(
            id=f"preview-{uuid.uuid4()}",
            meeting_id="preview",
            **e.model_dump(),
        )

    def _risk_response(r, row: Risk | None = None) -> RiskResponse:
        if row:
            return RiskResponse.model_validate(row)
        return RiskResponse(
            id=f"preview-{uuid.uuid4()}",
            meeting_id="preview",
            **r.model_dump(),
        )

    def _dec_response(d, row: Decision | None = None) -> DecisionResponse:
        if row:
            return DecisionResponse.model_validate(row)
        return DecisionResponse(
            id=f"preview-{uuid.uuid4()}",
            meeting_id="preview",
            **d.model_dump(),
        )

    if payload.save_to_db:
        tasks_out       = [_task_response(None, row) for row in task_rows]
        escalations_out = [_esc_response(None, row)  for row in escalation_rows]
        risks_out       = [_risk_response(None, row) for row in risk_rows]
        decisions_out   = [_dec_response(None, row)  for row in decision_rows]
    else:
        tasks_out       = [_task_response(t)       for t in intel.tasks]
        escalations_out = [_esc_response(e)        for e in intel.escalations]
        risks_out       = [_risk_response(r)       for r in intel.risks]
        decisions_out   = [_dec_response(d)        for d in intel.decisions]

    return ExtractionResponse(
        meeting_id=meeting_id,
        summary=intel.summary,
        counts=ExtractionCounts(
            tasks=len(tasks_out),
            escalations=len(escalations_out),
            risks=len(risks_out),
            decisions=len(decisions_out),
        ),
        tasks=tasks_out,
        escalations=escalations_out,
        risks=risks_out,
        decisions=decisions_out,
        raw_claude_output=raw_data,
    )
