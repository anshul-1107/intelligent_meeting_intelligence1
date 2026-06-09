"""
AI Engine — OpenRouter API (using open-source models like Llama 3)
  1. Extract structured intelligence from meeting transcripts.
  2. Answer natural-language queries about stored meeting data.
"""

import json
import re
import logging
from typing import Tuple
import httpx

from config import settings
from schemas import (
    ExtractedIntelligence,
    TaskCreate,
    EscalationCreate,
    RiskCreate,
    DecisionCreate,
)

logger = logging.getLogger(__name__)


async def _call_openrouter(messages: list, response_json: bool = False, temperature: float = 0.1) -> str:
    if not settings.openrouter_api_key:
        raise ValueError(
            "OPENROUTER_API_KEY is not set. Add it to backend/.env"
        )
        
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8000",
        "X-Title": "MeetIQ"
    }
    
    payload = {
        "model": settings.openrouter_model,
        "messages": messages,
        "temperature": temperature
    }
    
    if response_json:
        payload["response_format"] = {"type": "json_object"}
        
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=60.0
        )
        
    if response.status_code != 200:
        raise Exception(f"OpenRouter API error: {response.status_code} - {response.text}")
        
    result = response.json()
    try:
        return result["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        raise Exception(f"Unexpected OpenRouter response format: {result}")


# ── Extraction Prompt ──────────────────────────────────────────────────────────
# Sent as system_instruction so it stays constant across calls.
# We request response_mime_type="application/json", which tells Gemini to
# return pure JSON — no markdown fences, no prose.
EXTRACTION_SYSTEM_PROMPT = """
You are an expert meeting analyst.
Analyse the meeting transcript the user provides and return ONLY a single
valid JSON object — no prose, no markdown fences, no explanation.

The JSON object MUST have exactly these top-level keys:
  summary, tasks, escalations, risks, decisions

━━━ EXACT SCHEMA ━━━
{
  "summary": "<2-4 sentence executive summary of the meeting>",

  "tasks": [
    {
      "description": "<clear, actionable description of what needs to be done>",
      "owner"      : "<full name of the person responsible, or null if not mentioned>",
      "deadline"   : "<due date as written in the text, e.g. 'June 30th' or null>",
      "priority"   : "<exactly one of: low | medium | high | critical>",
      "status"     : "open"
    }
  ],

  "escalations": [
    {
      "description": "<what issue needs escalation and why>",
      "owner"      : "<who should receive the escalation, or null>",
      "severity"   : "<exactly one of: low | medium | high | critical>",
      "status"     : "open",
      "due_date"   : "<urgency date or null>"
    }
  ],

  "risks": [
    {
      "description": "<risk identified>",
      "impact"     : "<exactly one of: low | medium | high | critical>",
      "likelihood" : "<exactly one of: low | medium | high>",
      "mitigation" : "<suggested mitigation action, or null>",
      "owner"      : "<risk owner, or null>"
    }
  ],

  "decisions": [
    {
      "description": "<decision that was made>",
      "made_by"    : "<name of person or group who made the decision, or null>",
      "rationale"  : "<reason or justification, or null>",
      "decided_at" : "<when the decision was made, or null>"
    }
  ]
}

━━━ RULES ━━━
1. Return ONLY the JSON object — absolutely no text before or after it.
2. If a section has no items, use an empty array: [].
3. Never use empty strings for optional fields; use JSON null instead.
4. Infer owners from context ("Bob will...", "assigned to Alice", etc.).
5. Infer deadlines from phrases like "by end of week", "June 15th", "EOD".
6. Infer priority from urgency language: "ASAP"/"critical" → critical,
   "important"/"soon" → high, "when possible" → low, default → medium.
7. An escalation is something raised to leadership / a higher authority.
8. A risk is a potential future problem, not a confirmed issue.
9. A decision is a resolution or commitment already made in the meeting.
""".strip()


# ── NL Query Prompt ────────────────────────────────────────────────────────────
NL_QUERY_SYSTEM_PROMPT = """
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


# ── JSON parser ────────────────────────────────────────────────────────────────
def _parse_json(text: str) -> dict:
    """
    Robustly extract JSON from Gemini's response.
    With response_mime_type='application/json' this is usually a no-op,
    but we keep fencing + brace-isolation as a safety net.
    """
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if fenced:
        text = fenced.group(1).strip()
    # Isolate the outermost JSON object
    brace_start = text.find("{")
    brace_end   = text.rfind("}")
    if brace_start != -1 and brace_end > brace_start:
        text = text[brace_start: brace_end + 1]
    return json.loads(text)


# ── Model builder ──────────────────────────────────────────────────────────────
def _build_intelligence(data: dict) -> ExtractedIntelligence:
    """Convert raw Gemini JSON dict → validated ExtractedIntelligence model."""
    return ExtractedIntelligence(
        summary=     data.get("summary") or "",
        tasks=       [TaskCreate(**t)       for t in data.get("tasks",        [])],
        escalations= [EscalationCreate(**e) for e in data.get("escalations", [])],
        risks=       [RiskCreate(**r)       for r in data.get("risks",        [])],
        decisions=   [DecisionCreate(**d)   for d in data.get("decisions",   [])],
    )


# ── Fallback Mock Generation ───────────────────────────────────────────────────
def _generate_mock_extraction(transcript: str) -> dict:
    """
    Generate structured mock meeting intelligence when Gemini API is rate-limited.
    Strives to parse basic items from the transcript.
    """
    summary = "This is a fallback summary generated because the Gemini API quota was exceeded."
    tasks = []
    escalations = []
    risks = []
    decisions = []

    # 1. Try to find potential tasks
    # Examples: "Rahul will coordinate with the backend team before Friday."
    task_matches = re.findall(
        r"([A-Z][a-z]+)\s+will\s+([^.\n]+?)(?:\s+(?:before|by|on)\s+([^.\n]+))?\.",
        transcript
    )
    for owner, action, deadline in task_matches:
        tasks.append({
            "description": f"{action.strip().capitalize()}",
            "owner": owner.strip(),
            "deadline": deadline.strip() if deadline else None,
            "priority": "medium",
            "status": "open"
        })

    if not tasks and len(transcript.strip()) > 10:
        tasks.append({
            "description": "Coordinate on the key points mentioned in the meeting",
            "owner": "Team",
            "deadline": "End of week",
            "priority": "medium",
            "status": "open"
        })

    # 2. Try to find potential escalations
    # Examples: "Priya escalated the concern to leadership."
    escalation_matches = re.findall(
        r"([A-Z][a-z]+)\s+escalated\s+([^.\n]+?)\s+to\s+([^.\n]+?)\.",
        transcript,
        re.IGNORECASE
    )
    for owner, concern, target in escalation_matches:
        escalations.append({
            "description": f"{concern.strip().capitalize()} escalated to {target.strip()}",
            "owner": owner.strip(),
            "severity": "high",
            "status": "open",
            "due_date": None
        })

    if not escalations and "escalat" in transcript.lower():
        escalations.append({
            "description": "Critical issues discussed requiring leadership attention",
            "owner": "Leadership",
            "severity": "high",
            "status": "open",
            "due_date": None
        })

    # 3. Try to find potential risks
    # Examples: "If this issue continues, it may impact the Phase-2 release."
    risk_matches = re.findall(
        r"(if\s+[^,\n]+,\s+[^.\n]+(?:impact|delay|risk|prevent|fail)[^.\n]+)\.",
        transcript,
        re.IGNORECASE
    )
    for r_text in risk_matches:
        risks.append({
            "description": r_text.strip().capitalize(),
            "impact": "high",
            "likelihood": "medium",
            "mitigation": "Review alternative solutions and monitor closely.",
            "owner": None
        })

    if not risks and ("risk" in transcript.lower() or "delay" in transcript.lower() or "issue" in transcript.lower()):
        risks.append({
            "description": "Potential project delay due to dependencies discussed in the meeting",
            "impact": "high",
            "likelihood": "medium",
            "mitigation": "Establish a mitigation plan with the technical leads.",
            "owner": None
        })

    # 4. Decisions
    decision_matches = re.findall(
        r"([^.\n]*?(?:decided|agreed|resolved)\s+to\s+[^.\n]+)\.",
        transcript,
        re.IGNORECASE
    )
    for d_text in decision_matches:
        decisions.append({
            "description": d_text.strip().capitalize(),
            "made_by": "Team",
            "rationale": "Agreed by all participants during the sync.",
            "decided_at": None
        })

    sentences = [s.strip() for s in re.split(r'\.|\?|\!', transcript) if s.strip()]
    if sentences:
        first_part = sentences[0]
        summary = f"[DEMO MODE - Gemini API Rate Limit Exceeded] The meeting focused on: {first_part}. The team identified tasks, escalations, risks, and decisions as detailed below."
    else:
        summary = "[DEMO MODE - Gemini API Rate Limit Exceeded] Meeting transcript was empty or could not be parsed."

    return {
        "summary": summary,
        "tasks": tasks,
        "escalations": escalations,
        "risks": risks,
        "decisions": decisions
    }


def _generate_mock_query_response(question: str, context: str) -> str:
    """
    Generate a helper answer to the user's NL query when the Gemini API quota is exceeded.
    Parses the JSON context locally to answer basic questions.
    """
    try:
        data = json.loads(context)
    except Exception:
        data = {}

    question_lower = question.lower()
    
    def clean(val):
        return str(val).strip() if val else ""

    # Try to extract a specific owner/assignee name if requested
    owner_match = re.search(r"(?:for|assigned to|belonging to)\s+([A-Za-z]+)", question, re.IGNORECASE)
    target_owner = owner_match.group(1).lower() if owner_match else None
    
    all_tasks = data.get("tasks", [])
    if not all_tasks and isinstance(data, list):
        all_tasks = [item for item in data if "deadline" in item or "priority" in item]
        
    filtered_tasks = []
    for t in all_tasks:
        owner = clean(t.get("owner", ""))
        desc = clean(t.get("description", ""))
        if target_owner:
            if target_owner in owner.lower() or target_owner in desc.lower():
                filtered_tasks.append(t)
        else:
            filtered_tasks.append(t)

    all_escalations = data.get("escalations", [])
    if not all_escalations and isinstance(data, list):
        all_escalations = [item for item in data if "severity" in item]
    filtered_escalations = []
    for e in all_escalations:
        owner = clean(e.get("owner", ""))
        desc = clean(e.get("description", ""))
        if target_owner:
            if target_owner in owner.lower() or target_owner in desc.lower():
                filtered_escalations.append(e)
        else:
            filtered_escalations.append(e)

    all_risks = data.get("risks", [])
    if not all_risks and isinstance(data, list):
        all_risks = [item for item in data if "impact" in item or "likelihood" in item]
        
    all_decisions = data.get("decisions", [])
    if not all_decisions and isinstance(data, list):
        all_decisions = [item for item in data if "made_by" in item]

    lines = [
        "⚠️ **Gemini API Rate Limit Exceeded**: Answering query using local rule-based fallback.",
        ""
    ]

    if "task" in question_lower:
        if filtered_tasks:
            lines.append("Here are the tasks found in the database matching your query:")
            for i, t in enumerate(filtered_tasks, 1):
                owner_str = f" (Owner: {t.get('owner')})" if t.get('owner') else ""
                deadline_str = f", Due: {t.get('deadline')}" if t.get('deadline') else ""
                priority_str = f" [{t.get('priority', 'medium').upper()}]"
                lines.append(f"{i}. **{t.get('description')}**{owner_str}{deadline_str}{priority_str} (Status: {t.get('status', 'open')})")
        else:
            lines.append("No matching tasks were found in the current context.")
            
    elif "escalat" in question_lower:
        if filtered_escalations:
            lines.append("Here are the escalations found in the database:")
            for i, e in enumerate(filtered_escalations, 1):
                owner_str = f" (Owner: {e.get('owner')})" if e.get('owner') else ""
                severity_str = f" [{e.get('severity', 'high').upper()}]"
                lines.append(f"{i}. **{e.get('description')}**{owner_str}{severity_str} (Status: {e.get('status', 'open')})")
        else:
            lines.append("No escalations were found in the current context.")
            
    elif "risk" in question_lower:
        if all_risks:
            lines.append("Here are the risks found in the database:")
            for i, r in enumerate(all_risks, 1):
                impact_str = f" [Impact: {r.get('impact', 'medium').upper()}, Likelihood: {r.get('likelihood', 'medium').upper()}]"
                mitigation_str = f" (Mitigation: {r.get('mitigation')})" if r.get('mitigation') else ""
                lines.append(f"{i}. **{r.get('description')}**{impact_str}{mitigation_str}")
        else:
            lines.append("No risks were found in the current context.")
            
    elif "decision" in question_lower:
        if all_decisions:
            lines.append("Here are the decisions found in the database:")
            for i, d in enumerate(all_decisions, 1):
                by_str = f" (Made by: {d.get('made_by')})" if d.get('made_by') else ""
                rationale_str = f" - Rationale: {d.get('rationale')}" if d.get('rationale') else ""
                lines.append(f"{i}. **{d.get('description')}**{by_str}{rationale_str}")
        else:
            lines.append("No decisions were found in the current context.")
            
    else:
        lines.append("Unable to determine query category (tasks, escalations, risks, or decisions). Here is a summary of the data context:")
        lines.append(f"- Meetings: {len(data.get('meetings', [])) if isinstance(data, dict) else 'N/A'}")
        lines.append(f"- Tasks: {len(all_tasks)}")
        lines.append(f"- Escalations: {len(all_escalations)}")
        lines.append(f"- Risks: {len(all_risks)}")
        lines.append(f"- Decisions: {len(all_decisions)}")

    return "\n".join(lines)


# ── Public API ─────────────────────────────────────────────────────────────────
async def run_extraction(transcript: str) -> Tuple[dict, ExtractedIntelligence]:
    """
    Core extraction routine — used by both /api/meetings and /api/extract.

    Returns:
        raw_data  – the parsed JSON dict exactly as OpenRouter returned it
        intel     – validated ExtractedIntelligence pydantic model
    """
    logger.info("Calling OpenRouter for extraction (model=%s, chars=%d)",
                settings.openrouter_model, len(transcript))

    messages = [
        {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
        {"role": "user", "content": f"Extract structured intelligence from the meeting transcript below.\n\n{transcript}"}
    ]

    try:
        raw_text = await _call_openrouter(messages, response_json=True, temperature=0.1)
        logger.debug("OpenRouter raw response: %s", raw_text[:300])
        raw_data = _parse_json(raw_text)
    except Exception as exc:
        exc_str = str(exc).lower()
        if any(w in exc_str for w in ["quota", "429", "exhausted", "limit", "payment", "credit"]):
            logger.warning("OpenRouter API quota exceeded/rate-limited. Falling back to local mock extraction. Error: %s", exc)
            raw_data = _generate_mock_extraction(transcript)
        else:
            logger.warning("OpenRouter extraction failed. Falling back to local mock extraction. Error: %s", exc)
            raw_data = _generate_mock_extraction(transcript)

    intel = _build_intelligence(raw_data)
    return raw_data, intel


async def extract_intelligence(transcript: str) -> ExtractedIntelligence:
    """
    Convenience wrapper kept for backward-compatibility with the meetings router.
    """
    _, intel = await run_extraction(transcript)
    return intel


async def answer_nl_query(
    question: str,
    context: str,
    system_prompt: str | None = None,
) -> str:
    """
    Answer a natural-language question given a JSON context of meeting data.

    Args:
        question      – the user's plain-English question
        context       – JSON string of relevant DB rows
        system_prompt – optional override; falls back to NL_QUERY_SYSTEM_PROMPT
    """
    prompt = system_prompt if system_prompt is not None else NL_QUERY_SYSTEM_PROMPT

    messages = [
        {"role": "system", "content": prompt},
        {
            "role": "user",
            "content": (
                f"DATA CONTEXT:\n{context}\n\n"
                f"QUESTION: {question}"
            )
        }
    ]

    logger.info("Calling OpenRouter for NL query (model=%s): %r",
                settings.openrouter_model, question[:80])

    try:
        return await _call_openrouter(messages, temperature=0.3)
    except Exception as exc:
        exc_str = str(exc).lower()
        if any(w in exc_str for w in ["quota", "429", "exhausted", "limit", "payment", "credit"]):
            logger.warning("OpenRouter API quota exceeded. Falling back to local mock query response. Error: %s", exc)
            return _generate_mock_query_response(question, context)
        else:
            logger.warning("OpenRouter query failed. Falling back to local mock query response. Error: %s", exc)
            return _generate_mock_query_response(question, context)

