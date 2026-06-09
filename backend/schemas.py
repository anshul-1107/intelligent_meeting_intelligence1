from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


# ── Shared enums-as-literals ──────────────────────────────────────────────────
Priority   = str  # low | medium | high | critical
Severity   = str
Status     = str
Impact     = str
Likelihood = str


# ── Task Schemas ──────────────────────────────────────────────────────────────
class TaskBase(BaseModel):
    description: str
    owner:       Optional[str] = None
    deadline:    Optional[str] = None
    priority:    Optional[str] = "medium"
    status:      Optional[str] = "open"


class TaskCreate(TaskBase):
    pass


class TaskUpdate(BaseModel):
    description: Optional[str] = None
    owner:       Optional[str] = None
    deadline:    Optional[str] = None
    priority:    Optional[str] = None
    status:      Optional[str] = None


class TaskResponse(TaskBase):
    id:         str
    meeting_id: str
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ── Escalation Schemas ────────────────────────────────────────────────────────
class EscalationBase(BaseModel):
    description: str
    owner:       Optional[str] = None
    severity:    Optional[str] = "medium"
    status:      Optional[str] = "open"
    due_date:    Optional[str] = None


class EscalationCreate(EscalationBase):
    pass


class EscalationUpdate(BaseModel):
    description: Optional[str] = None
    owner:       Optional[str] = None
    severity:    Optional[str] = None
    status:      Optional[str] = None
    due_date:    Optional[str] = None


class EscalationResponse(EscalationBase):
    id:         str
    meeting_id: str
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ── Risk Schemas ──────────────────────────────────────────────────────────────
class RiskBase(BaseModel):
    description: str
    impact:      Optional[str] = "medium"
    likelihood:  Optional[str] = "medium"
    mitigation:  Optional[str] = None
    owner:       Optional[str] = None


class RiskCreate(RiskBase):
    pass


class RiskResponse(RiskBase):
    id:         str
    meeting_id: str
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ── Decision Schemas ──────────────────────────────────────────────────────────
class DecisionBase(BaseModel):
    description: str
    made_by:     Optional[str] = None
    rationale:   Optional[str] = None
    decided_at:  Optional[str] = None


class DecisionCreate(DecisionBase):
    pass


class DecisionResponse(DecisionBase):
    id:         str
    meeting_id: str
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ── Meeting Schemas ───────────────────────────────────────────────────────────
class MeetingCreate(BaseModel):
    title:      str = Field(..., min_length=1, max_length=255)
    transcript: str = Field(..., min_length=10)


class MeetingResponse(BaseModel):
    id:          str
    title:       str
    transcript:  str
    summary:     Optional[str] = None
    created_at:  Optional[datetime] = None
    updated_at:  Optional[datetime] = None

    model_config = {"from_attributes": True}


class MeetingDetailResponse(MeetingResponse):
    tasks:       List[TaskResponse]       = []
    escalations: List[EscalationResponse] = []
    risks:       List[RiskResponse]       = []
    decisions:   List[DecisionResponse]   = []


class MeetingListItem(BaseModel):
    id:               str
    title:            str
    summary:          Optional[str] = None
    created_at:       Optional[datetime] = None
    task_count:       int = 0
    escalation_count: int = 0
    risk_count:       int = 0
    decision_count:   int = 0

    model_config = {"from_attributes": True}


# ── Extracted Intelligence (AI output) ───────────────────────────────────────
class ExtractedIntelligence(BaseModel):
    summary:     str
    tasks:       List[TaskCreate]       = []
    escalations: List[EscalationCreate] = []
    risks:       List[RiskCreate]       = []
    decisions:   List[DecisionCreate]   = []


# ── NL Query Schemas ──────────────────────────────────────────────────────────
class QueryRequest(BaseModel):
    question: str = Field(..., min_length=3)


class QueryResponse(BaseModel):
    question: str
    answer:   str
    sources:  List[str] = []


# ── Stats Schema ──────────────────────────────────────────────────────────────
class StatsResponse(BaseModel):
    total_meetings:    int = 0
    total_tasks:       int = 0
    open_tasks:        int = 0
    total_escalations: int = 0
    open_escalations:  int = 0
    total_risks:       int = 0
    total_decisions:   int = 0


# ── /api/extract Schemas ──────────────────────────────────────────────────────
class ExtractionRequest(BaseModel):
    """
    Input for POST /api/extract.

    - text         : Raw meeting notes or transcript (required).
    - title        : Optional human-readable title; auto-generated from the
                     first 60 chars of text if omitted.
    - save_to_db   : When True (default), persist the meeting and all extracted
                     items to the database and return a meeting_id.
                     When False, run extraction only and return results without
                     touching the database — useful for previewing.
    """
    text:       str  = Field(..., min_length=10, description="Raw meeting transcript or notes")
    title:      Optional[str] = Field(None,  max_length=255, description="Optional meeting title")
    save_to_db: bool = Field(True, description="Persist extracted data to the database")


class ExtractionCounts(BaseModel):
    """How many items were extracted in each category."""
    tasks:       int
    escalations: int
    risks:       int
    decisions:   int


class ExtractionResponse(BaseModel):
    """
    Response for POST /api/extract.

    The four keys (tasks, escalations, risks, decisions) always contain
    the full extracted objects.  summary and meeting_id are also returned
    when available.
    """
    meeting_id:   Optional[str]               = Field(None, description="DB id (null when save_to_db=False)")
    summary:      str                          = Field("",   description="Executive summary of the meeting")
    counts:       ExtractionCounts
    tasks:        List[TaskResponse]           = []
    escalations:  List[EscalationResponse]    = []
    risks:        List[RiskResponse]           = []
    decisions:    List[DecisionResponse]       = []
    # The raw JSON dict exactly as returned by Claude, for full transparency
    raw_claude_output: dict                   = Field({}, description="Verbatim parsed JSON from Claude")
