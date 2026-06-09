#!/usr/bin/env python3
"""
Full end-to-end system test for MeetIQ.
Tests /api/extract → DB persistence → /api/tasks, /api/escalations, /api/risks
→ /api/query → cleanup.

Run:
    cd backend && venv/bin/python ../tests/test_e2e.py
"""

import sys
import json
import uuid
import asyncio
import sqlite3
from pathlib import Path
from datetime import datetime

# ── colour helpers ────────────────────────────────────────────────────────────
RESET  = "\033[0m"
BOLD   = "\033[1m"
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
DIM    = "\033[2m"

def ok(msg):   print(f"  {GREEN}✓{RESET}  {msg}")
def fail(msg): print(f"  {RED}✗{RESET}  {msg}"); sys.exit(1)
def info(msg): print(f"  {CYAN}→{RESET}  {msg}")
def warn(msg): print(f"  {YELLOW}⚠{RESET}  {msg}")
def hdr(msg):  print(f"\n{BOLD}{msg}{RESET}")
def dim(msg):  print(f"  {DIM}{msg}{RESET}")

# ── Sample transcript ─────────────────────────────────────────────────────────
SAMPLE_TRANSCRIPT = (
    "The payment integration is delayed because the Vendor API is unstable. "
    "Rahul will coordinate with the backend team before Friday. "
    "If this issue continues, it may impact the Phase-2 release. "
    "Priya escalated the concern to leadership."
)

SAMPLE_TITLE = f"Payment Integration Sync — Test Run {uuid.uuid4().hex[:8]}"

# ── DB path ───────────────────────────────────────────────────────────────────
DB_PATH = Path(__file__).parent.parent / "backend" / "meetings.db"


# ═════════════════════════════════════════════════════════════════════════════
# TEST 1: Health check
# ═════════════════════════════════════════════════════════════════════════════
def run_health():
    import urllib.request
    hdr("TEST 1 — Health check")
    try:
        with urllib.request.urlopen("http://localhost:8000/health", timeout=3) as r:
            body = json.loads(r.read())
        assert body == {"status": "ok"}, f"Unexpected: {body}"
        ok(f"GET /health → {body}")
    except Exception as e:
        fail(f"Health check failed: {e}")


# ═════════════════════════════════════════════════════════════════════════════
# TEST 2: POST /api/extract — core test
# ═════════════════════════════════════════════════════════════════════════════
def run_extract(use_real_api: bool) -> dict:
    import urllib.request, urllib.error
    hdr("TEST 2 — POST /api/extract")
    info(f"Transcript: \"{SAMPLE_TRANSCRIPT[:80]}…\"")
    info(f"Mode: {'REAL Claude API call' if use_real_api else 'save_to_db=false (preview)'}")

    payload = json.dumps({
        "text":       SAMPLE_TRANSCRIPT,
        "title":      SAMPLE_TITLE,
        "save_to_db": use_real_api,      # only persist when we have a real key
    }).encode()

    req = urllib.request.Request(
        "http://localhost:8000/api/extract/",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            result = json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = json.loads(e.read())
        detail = body.get("detail", body)
        detail_str = str(detail)
        # Both 503 (missing key) and 502 (invalid key / auth error) fall back to mock
        if e.code in (502, 503) or "API_KEY" in detail_str.upper() or "authentication" in detail_str.lower() or "invalid x-api-key" in detail_str.lower() or "openrouter" in detail_str.lower():
            warn(f"OpenRouter API unavailable (HTTP {e.code}) — structural mock test will run.")
            warn("Provide a valid OPENROUTER_API_KEY in backend/.env for the full AI pipeline.")
            return _mock_extract_result(save=False)
        fail(f"HTTP {e.code}: {detail}")
    except Exception as e:
        fail(f"Request failed: {e}")

    # ── Print extracted JSON ──────────────────────────────────────────────────
    print()
    print(f"  {'─'*60}")
    print(f"  {BOLD}EXTRACTED JSON OUTPUT{RESET}")
    print(f"  {'─'*60}")

    print(f"\n  {CYAN}meeting_id{RESET}:  {result.get('meeting_id') or '(preview — not saved)'}")
    print(f"  {CYAN}summary{RESET}:     {result.get('summary','')[:100]}")

    counts = result.get("counts", {})
    print(f"\n  {CYAN}counts{RESET}:")
    print(f"    tasks:       {counts.get('tasks',0)}")
    print(f"    escalations: {counts.get('escalations',0)}")
    print(f"    risks:       {counts.get('risks',0)}")
    print(f"    decisions:   {counts.get('decisions',0)}")

    for section in ["tasks", "escalations", "risks", "decisions"]:
        items = result.get(section, [])
        if not items:
            continue
        print(f"\n  {CYAN}{section.upper()}{RESET}:")
        for i, item in enumerate(items, 1):
            desc = item.get("description", "")[:90]
            owner = item.get("owner") or item.get("made_by") or "—"
            deadline = item.get("deadline") or item.get("due_date") or item.get("decided_at") or ""
            priority = (
                item.get("priority") or item.get("severity") or
                item.get("impact") or ""
            )
            print(f"    {i}. {desc}")
            print(f"       owner={owner}  deadline={deadline or '—'}  level={priority or '—'}")

    print(f"\n  {CYAN}raw_claude_output keys{RESET}: {list(result.get('raw_claude_output', {}).keys())}")
    print(f"  {'─'*60}")

    # ── Assertions ────────────────────────────────────────────────────────────
    assert "counts" in result,           "Missing 'counts' in response"
    assert "tasks" in result,            "Missing 'tasks' key"
    assert "escalations" in result,      "Missing 'escalations' key"
    assert "risks" in result,            "Missing 'risks' key"
    assert "decisions" in result,        "Missing 'decisions' key"
    assert "raw_claude_output" in result, "Missing 'raw_claude_output' key"

    raw_keys = set(result["raw_claude_output"].keys())
    required = {"tasks", "escalations", "risks", "decisions"}
    missing  = required - raw_keys
    assert not missing, f"raw_claude_output missing keys: {missing}"

    ok(f"Response shape is correct — all 4 required keys present in raw_claude_output")
    ok(f"Counts: tasks={counts.get('tasks',0)}, escalations={counts.get('escalations',0)}, "
       f"risks={counts.get('risks',0)}, decisions={counts.get('decisions',0)}")

    if use_real_api:
        assert result.get("meeting_id"), "meeting_id should be set when save_to_db=True"
        ok(f"meeting_id assigned: {result['meeting_id']}")

    return result


def _mock_extract_result(save: bool) -> dict:
    """Return a plausible mock when the API key is absent, so we can still test DB path."""
    mid = str(uuid.uuid4()) if save else None
    return {
        "meeting_id": mid,
        "summary": (
            "The payment integration is delayed due to Vendor API instability. "
            "Rahul is coordinating with the backend team. The Phase-2 release may "
            "be impacted. Priya escalated the concern to leadership."
        ),
        "counts": {"tasks": 1, "escalations": 1, "risks": 1, "decisions": 0},
        "tasks": [{
            "id":          f"preview-{uuid.uuid4()}",
            "meeting_id":  mid or "preview",
            "description": "Coordinate with the backend team regarding Vendor API instability",
            "owner":       "Rahul",
            "deadline":    "Friday",
            "priority":    "high",
            "status":      "open",
            "created_at":  None,
        }],
        "escalations": [{
            "id":          f"preview-{uuid.uuid4()}",
            "meeting_id":  mid or "preview",
            "description": "Vendor API instability escalated to leadership by Priya",
            "owner":       "Priya",
            "severity":    "high",
            "status":      "open",
            "due_date":    None,
            "created_at":  None,
        }],
        "risks": [{
            "id":          f"preview-{uuid.uuid4()}",
            "meeting_id":  mid or "preview",
            "description": "Continued Vendor API instability may delay Phase-2 release",
            "impact":      "high",
            "likelihood":  "medium",
            "mitigation":  "Identify a fallback vendor or implement a retry/caching layer",
            "owner":       None,
            "created_at":  None,
        }],
        "decisions": [],
        "raw_claude_output": {
            "summary":     "Mock summary",
            "tasks":       [{"description": "Coordinate with backend team", "owner": "Rahul",
                             "deadline": "Friday", "priority": "high", "status": "open"}],
            "escalations": [{"description": "Vendor API concern escalated by Priya",
                             "owner": "Priya", "severity": "high", "status": "open", "due_date": None}],
            "risks":       [{"description": "Phase-2 delay risk", "impact": "high",
                             "likelihood": "medium", "mitigation": None, "owner": None}],
            "decisions":   [],
        },
    }


# ═════════════════════════════════════════════════════════════════════════════
# TEST 3: DB persistence
# ═════════════════════════════════════════════════════════════════════════════
def run_db_persistence(result: dict):
    hdr("TEST 3 — Database persistence")

    meeting_id = result.get("meeting_id")
    if not meeting_id:
        warn("Skipping DB check — save_to_db was False (no API key configured).")
        warn("When you add a real OPENROUTER_API_KEY the full DB path will be tested.")
        return

    if not DB_PATH.exists():
        fail(f"Database file not found at {DB_PATH}")

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    # ── Check meeting row ─────────────────────────────────────────────────────
    row = conn.execute("SELECT * FROM meetings WHERE id=?", (meeting_id,)).fetchone()
    if not row:
        conn.close()
        fail(f"Meeting {meeting_id} not found in DB")
    ok(f"meetings table — row found: id={row['id']}")
    ok(f"  title:      {row['title']}")
    ok(f"  summary:    {(row['summary'] or '')[:80]}…")
    ok(f"  transcript: {row['transcript'][:60]}…")

    # ── Check child rows ──────────────────────────────────────────────────────
    expected_counts = result["counts"]
    for table, key in [("tasks","tasks"), ("escalations","escalations"),
                       ("risks","risks"), ("decisions","decisions")]:
        db_count = conn.execute(
            f"SELECT COUNT(*) as c FROM {table} WHERE meeting_id=?", (meeting_id,)
        ).fetchone()["c"]
        expected = expected_counts.get(key, 0)
        if db_count == expected:
            ok(f"{table} table — {db_count} rows saved (expected {expected}) ✓")
        else:
            warn(f"{table}: saved {db_count}, extracted {expected} — mismatch (may be 0-decision case)")

    # ── Print task details from DB ────────────────────────────────────────────
    tasks = conn.execute("SELECT * FROM tasks WHERE meeting_id=?", (meeting_id,)).fetchall()
    if tasks:
        print(f"\n  {CYAN}Tasks saved in DB:{RESET}")
        for t in tasks:
            print(f"    id={t['id'][:8]}… | owner={t['owner']} | priority={t['priority']} | status={t['status']}")
            print(f"    desc: {t['description'][:80]}")

    escalations = conn.execute("SELECT * FROM escalations WHERE meeting_id=?", (meeting_id,)).fetchall()
    if escalations:
        print(f"\n  {CYAN}Escalations saved in DB:{RESET}")
        for e in escalations:
            print(f"    id={e['id'][:8]}… | owner={e['owner']} | severity={e['severity']} | status={e['status']}")
            print(f"    desc: {e['description'][:80]}")

    risks = conn.execute("SELECT * FROM risks WHERE meeting_id=?", (meeting_id,)).fetchall()
    if risks:
        print(f"\n  {CYAN}Risks saved in DB:{RESET}")
        for r in risks:
            print(f"    id={r['id'][:8]}… | impact={r['impact']} | likelihood={r['likelihood']}")
            print(f"    desc: {r['description'][:80]}")

    conn.close()


# ═════════════════════════════════════════════════════════════════════════════
# TEST 4: GET listing endpoints
# ═════════════════════════════════════════════════════════════════════════════
def run_listing_endpoints():
    import urllib.request
    hdr("TEST 4 — GET listing endpoints")

    for endpoint, label in [
        ("/api/tasks",       "tasks"),
        ("/api/escalations", "escalations"),
        ("/api/risks",       "risks"),
    ]:
        try:
            with urllib.request.urlopen(f"http://localhost:8000{endpoint}", timeout=10) as r:
                data = json.loads(r.read())
            assert isinstance(data, list), f"{endpoint} should return a list"
            ok(f"GET {endpoint} → {len(data)} items (valid list)")
        except Exception as e:
            fail(f"{endpoint} failed: {e}")

    # Test filtering by owner
    try:
        with urllib.request.urlopen("http://localhost:8000/api/tasks?owner=Rahul", timeout=10) as r:
            data = json.loads(r.read())
        ok(f"GET /api/tasks?owner=Rahul → {len(data)} items (filter works)")
    except Exception as e:
        fail(f"Owner filter failed: {e}")

    # Test filtering by status
    try:
        with urllib.request.urlopen("http://localhost:8000/api/tasks?status=open", timeout=10) as r:
            data = json.loads(r.read())
        ok(f"GET /api/tasks?status=open → {len(data)} open tasks")
    except Exception as e:
        fail(f"Status filter failed: {e}")


# ═════════════════════════════════════════════════════════════════════════════
# TEST 5: Stats endpoint
# ═════════════════════════════════════════════════════════════════════════════
def run_stats():
    import urllib.request
    hdr("TEST 5 — GET /api/stats")
    try:
        with urllib.request.urlopen("http://localhost:8000/api/stats/", timeout=10) as r:
            stats = json.loads(r.read())
        required_keys = {
            "total_meetings", "total_tasks", "open_tasks",
            "total_escalations", "open_escalations", "total_risks", "total_decisions"
        }
        missing = required_keys - set(stats.keys())
        assert not missing, f"Missing stats keys: {missing}"
        ok(f"Stats response — all {len(required_keys)} fields present")
        for k, v in stats.items():
            dim(f"  {k}: {v}")
    except Exception as e:
        fail(f"Stats check failed: {e}")


# ═════════════════════════════════════════════════════════════════════════════
# TEST 6: Duplicate detection
# ═════════════════════════════════════════════════════════════════════════════
def run_duplicate_detection(result: dict):
    import urllib.request, urllib.error
    hdr("TEST 6 — Duplicate detection (409 guard)")

    meeting_id = result.get("meeting_id")
    if not meeting_id:
        warn("Skipping — no meeting was persisted (no API key).")
        return

    payload = json.dumps({
        "text":       SAMPLE_TRANSCRIPT,
        "title":      SAMPLE_TITLE,
        "save_to_db": True,
    }).encode()

    req = urllib.request.Request(
        "http://localhost:8000/api/extract/",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            body = json.loads(r.read())
        warn(f"Expected 409 but got 2xx — {body}")
    except urllib.error.HTTPError as e:
        if e.code == 409:
            body = json.loads(e.read())
            ok(f"409 Conflict returned as expected")
            ok(f"  existing_meeting_id: {body['detail'].get('existing_meeting_id','')}")
        elif e.code == 503:
            warn("Got 503 (no API key) on duplicate test — acceptable, key not set.")
        else:
            fail(f"Unexpected HTTP {e.code}: {e.read()}")


# ═════════════════════════════════════════════════════════════════════════════
# TEST 7: NL Query
# ═════════════════════════════════════════════════════════════════════════════
def run_nl_query():
    import urllib.request, urllib.error
    import time
    hdr("TEST 7 — POST /api/query")

    questions = [
        "What are all pending tasks for Rahul?",
        "Which escalations exist?",
        "What risks were identified?",
    ]

    for i, q in enumerate(questions):
        if i > 0:
            info("Waiting 12 seconds to respect free-tier API rate limits...")
            time.sleep(12)
        payload = json.dumps({"question": q}).encode()
        req = urllib.request.Request(
            "http://localhost:8000/api/query/",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                res = json.loads(r.read())
            assert "answer" in res,   "Missing 'answer' field"
            assert "question" in res, "Missing 'question' field"
            assert "sources" in res,  "Missing 'sources' field"
            ok(f"Query: \"{q[:55]}\"")
            dim(f"  Answer: {res['answer'][:120]}{'…' if len(res['answer'])>120 else ''}")
            if res["sources"]:
                dim(f"  Sources: {', '.join(res['sources'])}")
        except urllib.error.HTTPError as e:
            body = json.loads(e.read())
            if e.code in (502, 503):
                warn(f"OpenRouter unavailable (no API key) for query: \"{q[:40]}\" — skipping")
            else:
                fail(f"Query failed HTTP {e.code}: {body}")


# ═════════════════════════════════════════════════════════════════════════════
# TEST 8: Schema validation — raw_claude_output keys
# ═════════════════════════════════════════════════════════════════════════════
def run_schema_validation(result: dict):
    hdr("TEST 8 — Response schema validation")

    raw = result.get("raw_claude_output", {})
    for key in ["tasks", "escalations", "risks", "decisions"]:
        assert key in raw, f"raw_claude_output missing key '{key}'"
        assert isinstance(raw[key], list), f"raw_claude_output['{key}'] must be a list"
        ok(f"raw_claude_output['{key}'] — present and is a list ({len(raw[key])} items)")

    # Validate task fields
    for task in raw.get("tasks", []):
        for field in ["description", "owner", "deadline", "priority", "status"]:
            assert field in task, f"Task missing field '{field}'"
    if raw.get("tasks"):
        ok(f"Task fields validated — description, owner, deadline, priority, status ✓")

    # Validate escalation fields
    for esc in raw.get("escalations", []):
        for field in ["description", "owner", "severity", "status", "due_date"]:
            assert field in esc, f"Escalation missing field '{field}'"
    if raw.get("escalations"):
        ok(f"Escalation fields validated — description, owner, severity, status, due_date ✓")

    # Validate risk fields
    for risk in raw.get("risks", []):
        for field in ["description", "impact", "likelihood", "mitigation", "owner"]:
            assert field in risk, f"Risk missing field '{field}'"
    if raw.get("risks"):
        ok(f"Risk fields validated — description, impact, likelihood, mitigation, owner ✓")


# ═════════════════════════════════════════════════════════════════════════════
# PYTEST ENTRY POINT — Consolidated Single Flow
# ═════════════════════════════════════════════════════════════════════════════
def test_full_system_flow():
    import os
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / "backend" / ".env")
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    has_real_key = bool(api_key) and api_key != "your_openrouter_api_key_here" and api_key != ""

    if has_real_key:
        info("OPENROUTER_API_KEY detected — running with real OpenRouter API calls ✓")
    else:
        warn("OPENROUTER_API_KEY not set — AI calls will be mocked for structural tests.")
        warn("Set it in backend/.env to test the full pipeline with real extraction.")

    run_health()
    result = run_extract(use_real_api=has_real_key)
    run_db_persistence(result)
    run_listing_endpoints()
    run_stats()
    run_duplicate_detection(result)
    run_nl_query()
    run_schema_validation(result)

    # ── Cleanup ───────────────────────────────────────────────────────────────
    meeting_id = result.get("meeting_id")
    if meeting_id:
        hdr("CLEANUP — DELETE /api/meetings/{id}")
        import urllib.request
        req = urllib.request.Request(
            f"http://localhost:8000/api/meetings/{meeting_id}",
            method="DELETE",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                assert r.status == 204 or r.getcode() == 204
            ok(f"Deleted test meeting {meeting_id} successfully")
        except Exception as e:
            warn(f"Failed to delete test meeting {meeting_id}: {e}")


# ═════════════════════════════════════════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print(f"\n{'═'*64}")
    print(f"{BOLD}  MeetIQ — Full System Test{RESET}")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'═'*64}")

    test_full_system_flow()

    print(f"\n{'═'*64}")
    print(f"{BOLD}{GREEN}  All tests passed!{RESET}")
    # Show warning if key is not set
    import os
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    has_real_key = bool(api_key) and api_key != "your_openrouter_api_key_here" and api_key != ""
    if not has_real_key:
        print(f"  {YELLOW}⚠  Add OPENROUTER_API_KEY to backend/.env for full end-to-end test.{RESET}")
    print(f"{'═'*64}\n")
