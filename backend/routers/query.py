"""
POST /api/query — Natural-language querying across all stored meeting data.

Improvements over the naive implementation:
  ─ Intent detection: the question is analysed to decide which DB tables
    to pull and how much context to send, keeping prompts tight.
  ─ Owner-aware pre-filtering: names mentioned in the question are used to
    narrow DB results before sending to Claude, so the prompt stays small
    even when the database is large.
  ─ Rich source citations: the response includes the meeting titles that
    were used as context, and individual item ids for deep-linking.
  ─ Claude is instructed to answer in plain text (not JSON), with inline
    citations in the form [Meeting Title] so the frontend can render them.
  ─ The response schema carries both `answer` (plain text) and
    `structured_matches` (the raw DB rows that were sent as context).
"""

import json
import logging
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_

from database import get_db, Meeting, Task, Escalation, Risk, Decision
from schemas import QueryRequest, QueryResponse
from ai_engine import answer_nl_query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/query", tags=["query"])


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

# Keywords that hint at which category the user is asking about
_CATEGORY_HINTS: dict[str, list[str]] = {
    "tasks":       ["task", "action", "todo", "to-do", "assignment", "action item",
                    "pending", "assigned", "deadline", "due", "overdue", "complete",
                    "done", "open", "in progress", "finish", "deliver"],
    "escalations": ["escalat", "escalation", "urgent", "critical", "blocker",
                    "flag", "raise", "severity", "leadership", "unresolved"],
    "risks":       ["risk", "threat", "concern", "issue", "impact", "likelihood",
                    "mitigation", "mitigate", "danger", "exposure"],
    "decisions":   ["decision", "decided", "agreed", "approved", "chose", "choice",
                    "resolution", "concluded", "rationale"],
    "meetings":    ["meeting", "session", "call", "discuss", "summary", "summari"],
}


def _detect_intent(question: str) -> set[str]:
    """
    Return the set of categories the question is most likely about.
    Falls back to ALL categories when nothing specific is detected.
    """
    q = question.lower()
    hits: set[str] = set()
    for category, keywords in _CATEGORY_HINTS.items():
        if any(kw in q for kw in keywords):
            hits.add(category)
    return hits if hits else set(_CATEGORY_HINTS.keys())


def _extract_name_hints(question: str) -> list[str]:
    """
    Heuristically pull proper-noun tokens from the question so we can
    pre-filter DB rows by owner name before sending to Claude.
    We look for Title-Cased words that are NOT common question words.
    """
    _STOP = {
        "What", "Which", "Who", "Where", "When", "How", "Tell", "Show",
        "List", "Give", "Get", "Find", "Are", "Is", "All", "Any", "The",
        "A", "An", "For", "In", "On", "Of", "To", "From", "With",
    }
    tokens = re.findall(r"\b[A-Z][a-z]{2,}\b", question)
    return [t for t in tokens if t not in _STOP]


async def _build_context(question: str, db: AsyncSession) -> tuple[dict[str, Any], list[str]]:
    """
    Fetch relevant DB rows and return:
      context_dict  – JSON-serialisable dict passed to Claude
      source_titles – unique meeting titles referenced
    """
    categories  = _detect_intent(question)
    name_hints  = _extract_name_hints(question)

    ctx: dict[str, Any] = {}
    meeting_ids_seen: set[str] = set()

    # ── Tasks ─────────────────────────────────────────────────────────────────
    if "tasks" in categories:
        q = select(Task)
        if name_hints:
            q = q.where(or_(*[Task.owner.ilike(f"%{n}%") for n in name_hints]))
        q = q.order_by(Task.created_at.desc()).limit(150)
        tasks = (await db.execute(q)).scalars().all()
        # If name-filtered result is empty, fall back to all tasks (capped)
        if not tasks and name_hints:
            tasks = (await db.execute(
                select(Task).order_by(Task.created_at.desc()).limit(150)
            )).scalars().all()
        ctx["tasks"] = [
            {
                "id":          t.id,
                "description": t.description,
                "owner":       t.owner,
                "deadline":    t.deadline,
                "priority":    t.priority,
                "status":      t.status,
                "meeting_id":  t.meeting_id,
            }
            for t in tasks
        ]
        meeting_ids_seen.update(t.meeting_id for t in tasks)

    # ── Escalations ───────────────────────────────────────────────────────────
    if "escalations" in categories:
        q = select(Escalation)
        if name_hints:
            q = q.where(or_(*[Escalation.owner.ilike(f"%{n}%") for n in name_hints]))
        q = q.order_by(Escalation.created_at.desc()).limit(100)
        escalations = (await db.execute(q)).scalars().all()
        if not escalations and name_hints:
            escalations = (await db.execute(
                select(Escalation).order_by(Escalation.created_at.desc()).limit(100)
            )).scalars().all()
        ctx["escalations"] = [
            {
                "id":          e.id,
                "description": e.description,
                "owner":       e.owner,
                "severity":    e.severity,
                "status":      e.status,
                "due_date":    e.due_date,
                "meeting_id":  e.meeting_id,
            }
            for e in escalations
        ]
        meeting_ids_seen.update(e.meeting_id for e in escalations)

    # ── Risks ─────────────────────────────────────────────────────────────────
    if "risks" in categories:
        q = select(Risk)
        if name_hints:
            q = q.where(or_(*[Risk.owner.ilike(f"%{n}%") for n in name_hints]))
        q = q.order_by(Risk.created_at.desc()).limit(100)
        risks = (await db.execute(q)).scalars().all()
        if not risks and name_hints:
            risks = (await db.execute(
                select(Risk).order_by(Risk.created_at.desc()).limit(100)
            )).scalars().all()
        ctx["risks"] = [
            {
                "id":          r.id,
                "description": r.description,
                "impact":      r.impact,
                "likelihood":  r.likelihood,
                "mitigation":  r.mitigation,
                "owner":       r.owner,
                "meeting_id":  r.meeting_id,
            }
            for r in risks
        ]
        meeting_ids_seen.update(r.meeting_id for r in risks)

    # ── Decisions ─────────────────────────────────────────────────────────────
    if "decisions" in categories:
        decisions = (await db.execute(
            select(Decision).order_by(Decision.created_at.desc()).limit(100)
        )).scalars().all()
        ctx["decisions"] = [
            {
                "id":          d.id,
                "description": d.description,
                "made_by":     d.made_by,
                "rationale":   d.rationale,
                "decided_at":  d.decided_at,
                "meeting_id":  d.meeting_id,
            }
            for d in decisions
        ]
        meeting_ids_seen.update(d.meeting_id for d in decisions)

    # ── Meeting metadata (for title resolution + summaries) ───────────────────
    meetings_q = select(Meeting)
    if meeting_ids_seen:
        meetings_q = meetings_q.where(Meeting.id.in_(list(meeting_ids_seen)))
    else:
        meetings_q = meetings_q.order_by(Meeting.created_at.desc()).limit(30)
    meetings = (await db.execute(meetings_q)).scalars().all()

    ctx["meetings"] = [
        {
            "id":         m.id,
            "title":      m.title,
            "summary":    m.summary,
            "created_at": str(m.created_at),
        }
        for m in meetings
    ]

    source_titles = [m.title for m in meetings]
    return ctx, source_titles


# ── System prompt ─────────────────────────────────────────────────────────────
_NL_SYSTEM_PROMPT = """
You are a smart assistant for a Meeting Intelligence platform.

You are given a JSON context that contains data extracted from meeting transcripts:
meetings, tasks, escalations, risks, and decisions.

Answer the user's question accurately using ONLY the data in the context.

Formatting rules:
1. Answer in plain, readable English — no JSON, no code blocks.
2. When referencing a specific item, include its owner or description briefly.
3. When referencing a meeting, cite it as [Meeting Title].
4. If the question asks to list items, use a numbered or bulleted list.
5. If the data has no relevant information, say so honestly and clearly.
6. Be concise but complete — do not pad the answer with filler.
7. If asked about a person (e.g. "tasks for Rahul"), filter to that person only.
""".strip()


# ─────────────────────────────────────────────────────────────────────────────
# Endpoint
# ─────────────────────────────────────────────────────────────────────────────
@router.post(
    "/",
    response_model=QueryResponse,
    summary="Ask a natural-language question about your meeting data",
    description=(
        "Accepts a plain-English question such as *'What are all pending tasks for Rahul?'* "
        "The system builds a smart DB context, sends it to Claude, and returns a precise "
        "plain-text answer with inline meeting citations."
    ),
)
async def nl_query(
    payload: QueryRequest,
    db: AsyncSession = Depends(get_db),
) -> QueryResponse:

    question = payload.question.strip()
    logger.info("NL query received: %r", question)

    # 1. Build intent-aware context
    try:
        ctx_dict, source_titles = await _build_context(question, db)
    except Exception as exc:
        logger.exception("Context build failed")
        raise HTTPException(status_code=500, detail=f"Context build error: {exc}")

    context_json = json.dumps(ctx_dict, default=str, indent=2)

    total_items = sum(
        len(v) for v in ctx_dict.values() if isinstance(v, list)
    )
    logger.info(
        "Context built — %d total items across %d categories for query %r",
        total_items, len(ctx_dict), question,
    )

    # 2. Ask Claude
    try:
        answer = await answer_nl_query(
            question=question,
            context=context_json,
            system_prompt=_NL_SYSTEM_PROMPT,
        )
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        logger.exception("Claude NL query failed")
        raise HTTPException(status_code=502, detail=f"Claude API error: {exc}")

    logger.info("NL query answered — %d source meetings", len(source_titles))

    return QueryResponse(
        question=question,
        answer=answer,
        sources=list(dict.fromkeys(source_titles)),   # deduplicated, order-preserved
    )
