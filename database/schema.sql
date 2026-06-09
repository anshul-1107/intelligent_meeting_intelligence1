-- ============================================================
-- Intelligent Meeting Intelligence & Escalation Tracking
-- Database Schema
-- ============================================================

-- Meetings: stores raw transcript + AI-generated summary
CREATE TABLE IF NOT EXISTS meetings (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    transcript  TEXT NOT NULL,
    summary     TEXT,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tasks extracted from meetings
CREATE TABLE IF NOT EXISTS tasks (
    id          TEXT PRIMARY KEY,
    meeting_id  TEXT NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    description TEXT NOT NULL,
    owner       TEXT,
    deadline    TEXT,
    priority    TEXT CHECK(priority IN ('low', 'medium', 'high', 'critical')) DEFAULT 'medium',
    status      TEXT CHECK(status IN ('open', 'in_progress', 'done', 'cancelled')) DEFAULT 'open',
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Escalations extracted from meetings
CREATE TABLE IF NOT EXISTS escalations (
    id          TEXT PRIMARY KEY,
    meeting_id  TEXT NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    description TEXT NOT NULL,
    owner       TEXT,
    severity    TEXT CHECK(severity IN ('low', 'medium', 'high', 'critical')) DEFAULT 'medium',
    status      TEXT CHECK(status IN ('open', 'acknowledged', 'resolved')) DEFAULT 'open',
    due_date    TEXT,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Risks extracted from meetings
CREATE TABLE IF NOT EXISTS risks (
    id          TEXT PRIMARY KEY,
    meeting_id  TEXT NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    description TEXT NOT NULL,
    impact      TEXT CHECK(impact IN ('low', 'medium', 'high', 'critical')) DEFAULT 'medium',
    likelihood  TEXT CHECK(likelihood IN ('low', 'medium', 'high')) DEFAULT 'medium',
    mitigation  TEXT,
    owner       TEXT,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Decisions extracted from meetings
CREATE TABLE IF NOT EXISTS decisions (
    id          TEXT PRIMARY KEY,
    meeting_id  TEXT NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    description TEXT NOT NULL,
    made_by     TEXT,
    rationale   TEXT,
    decided_at  TEXT,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_tasks_meeting_id    ON tasks(meeting_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status        ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_owner         ON tasks(owner);
CREATE INDEX IF NOT EXISTS idx_escalations_meeting ON escalations(meeting_id);
CREATE INDEX IF NOT EXISTS idx_escalations_status  ON escalations(status);
CREATE INDEX IF NOT EXISTS idx_risks_meeting       ON risks(meeting_id);
CREATE INDEX IF NOT EXISTS idx_decisions_meeting   ON decisions(meeting_id);
