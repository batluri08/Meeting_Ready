"""SQLite warehouse: schema + connection helper.

Clean tables are keyed by client_id (from entity resolution). Every row keeps `source_ref`
(e.g. 'crm:CRM-1012', 'billing:BIL-7001') so any number in a briefing can be traced to its source record.
"""
import sqlite3
from pathlib import Path

from app import config

SCHEMA = """
CREATE TABLE clients (
    client_id     TEXT PRIMARY KEY,
    legal_name    TEXT NOT NULL,
    domain        TEXT,
    industry      TEXT,
    region        TEXT,
    segment       TEXT,
    tier          TEXT,
    client_since  TEXT
);

-- Every source-system account and how it was matched to a client (the "customer master" crosswalk).
CREATE TABLE client_xref (
    source_system        TEXT NOT NULL,          -- crm | billing
    source_id            TEXT NOT NULL,
    source_name          TEXT NOT NULL,
    source_domain        TEXT,
    client_id            TEXT REFERENCES clients(client_id),   -- NULL unless merged / master
    candidate_client_id  TEXT REFERENCES clients(client_id),   -- best guess, for the review queue
    match_method         TEXT NOT NULL,          -- master | domain+name | domain | name_only | domain_conflict
    confidence           REAL NOT NULL,
    status               TEXT NOT NULL,          -- master | merged | review | unmatched
    reason               TEXT NOT NULL,
    PRIMARY KEY (source_system, source_id)
);

CREATE TABLE users (
    user_id    TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    team       TEXT,
    clearance  TEXT NOT NULL                     -- analyst | senior
);

CREATE TABLE coverage (
    client_id   TEXT NOT NULL REFERENCES clients(client_id),
    user_id     TEXT NOT NULL REFERENCES users(user_id),
    role        TEXT,
    start_date  TEXT,
    source_ref  TEXT NOT NULL
);

CREATE TABLE contacts (
    contact_id    TEXT PRIMARY KEY,
    client_id     TEXT NOT NULL REFERENCES clients(client_id),
    name          TEXT NOT NULL,
    email         TEXT,
    title         TEXT,
    role          TEXT,
    updated_at    TEXT,
    duplicate_of  TEXT REFERENCES contacts(contact_id),   -- set when the same person appears twice
    source_ref    TEXT NOT NULL
);

CREATE TABLE products (
    product_code  TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    family        TEXT
);

CREATE TABLE holdings (
    client_id        TEXT NOT NULL REFERENCES clients(client_id),
    product_code     TEXT NOT NULL REFERENCES products(product_code),
    status           TEXT,
    opened_on        TEXT,
    utilization_pct  INTEGER,
    source_ref       TEXT NOT NULL
);

CREATE TABLE revenue_monthly (
    client_id     TEXT REFERENCES clients(client_id),     -- NULL when the billing account is unresolved
    month         TEXT NOT NULL,
    product_code  TEXT NOT NULL REFERENCES products(product_code),
    revenue       INTEGER NOT NULL,
    source_ref    TEXT NOT NULL
);

CREATE TABLE performance_monthly (
    client_id   TEXT NOT NULL REFERENCES clients(client_id),
    month       TEXT NOT NULL,
    metric      TEXT NOT NULL,
    value       REAL NOT NULL,
    source_ref  TEXT NOT NULL
);

CREATE TABLE relationship_metrics (
    client_id           TEXT NOT NULL REFERENCES clients(client_id),
    as_of               TEXT NOT NULL,
    wallet_share_pct    INTEGER,
    satisfaction_score  REAL,
    primary_bank        INTEGER,
    source_ref          TEXT NOT NULL
);

CREATE TABLE pipeline (
    opp_id          TEXT PRIMARY KEY,
    client_id       TEXT NOT NULL REFERENCES clients(client_id),
    product_code    TEXT REFERENCES products(product_code),
    stage           TEXT,
    value           INTEGER,
    expected_close  TEXT,
    updated_at      TEXT,
    restricted      INTEGER NOT NULL DEFAULT 0,
    source_ref      TEXT NOT NULL
);

CREATE TABLE service_issues (
    issue_id    TEXT PRIMARY KEY,
    client_id   TEXT NOT NULL REFERENCES clients(client_id),
    opened_at   TEXT,
    closed_at   TEXT,
    severity    INTEGER,
    status      TEXT,
    summary     TEXT,
    source_ref  TEXT NOT NULL
);

CREATE TABLE open_actions (
    action_id    TEXT PRIMARY KEY,
    client_id    TEXT NOT NULL REFERENCES clients(client_id),
    owner_id     TEXT REFERENCES users(user_id),
    description  TEXT,
    due_date     TEXT,
    status       TEXT,
    origin_doc   TEXT,                          -- the email / note the action came from
    source_ref   TEXT NOT NULL
);

CREATE TABLE interactions (
    interaction_id  TEXT PRIMARY KEY,
    client_id       TEXT NOT NULL REFERENCES clients(client_id),
    date            TEXT,
    type            TEXT,
    summary_doc_id  TEXT,
    source_ref      TEXT NOT NULL
);

CREATE TABLE meetings (
    meeting_id  TEXT PRIMARY KEY,
    client_id   TEXT NOT NULL REFERENCES clients(client_id),
    start_time  TEXT,
    title       TEXT,
    attendees   TEXT,
    source_ref  TEXT NOT NULL
);

CREATE TABLE documents (
    doc_id           TEXT PRIMARY KEY,
    type             TEXT NOT NULL,             -- email | note | briefing | research | news
    date             TEXT,
    client_id        TEXT REFERENCES clients(client_id),   -- NULL for general research
    match_method     TEXT NOT NULL,             -- account_id | email_domain | none
    match_confidence REAL,
    sender           TEXT,
    recipient        TEXT,
    title            TEXT,
    source           TEXT,
    restricted       INTEGER NOT NULL DEFAULT 0,
    content_hash     TEXT NOT NULL,
    duplicate_of     TEXT REFERENCES documents(doc_id),
    injection_flag   INTEGER NOT NULL DEFAULT 0,  -- text that tries to instruct the AI (kept as data)
    body             TEXT NOT NULL,
    source_ref       TEXT NOT NULL,
    story_id         TEXT                         -- news: the story this item belongs to (lead doc id)
);

-- The same news story reported by several outlets; `conflict` lists figures that disagree.
CREATE TABLE news_stories (
    story_id   TEXT PRIMARY KEY,
    client_id  TEXT REFERENCES clients(client_id),
    doc_ids    TEXT NOT NULL,                   -- comma-separated
    sources    TEXT NOT NULL,
    conflict   TEXT
);

CREATE TABLE chunks (
    chunk_id    TEXT PRIMARY KEY,               -- e.g. NT-1001#p2, RS-9001#p3.2 (second part of page 3)
    doc_id      TEXT NOT NULL REFERENCES documents(doc_id),
    client_id   TEXT REFERENCES clients(client_id),
    page        INTEGER NOT NULL,
    part        INTEGER NOT NULL DEFAULT 1,
    section     TEXT,                           -- '### ' heading (research)
    text        TEXT NOT NULL,                  -- original words, quoted in citations
    context     TEXT NOT NULL,                  -- header + text: what is embedded and keyword-indexed
    restricted  INTEGER NOT NULL DEFAULT 0
);

-- Embedding of each chunk (float32 bytes). Loaded into the vector database (Qdrant) at startup.
CREATE TABLE chunk_vectors (
    chunk_id  TEXT PRIMARY KEY REFERENCES chunks(chunk_id),
    model     TEXT NOT NULL,
    dim       INTEGER NOT NULL,
    vector    BLOB NOT NULL
);

CREATE TABLE ingest_runs (
    run_at   TEXT NOT NULL,
    summary  TEXT NOT NULL
);

CREATE INDEX ix_revenue_client ON revenue_monthly(client_id, month);
CREATE INDEX ix_perf_client ON performance_monthly(client_id, month);
CREATE INDEX ix_docs_client ON documents(client_id, type);
CREATE INDEX ix_chunks_client ON chunks(client_id);
"""


def connect(path: Path | None = None, readonly: bool = False) -> sqlite3.Connection:
    """Open the warehouse. readonly=True opens it in SQLite read-only mode (used by agents and Text-to-SQL)."""
    p = Path(path or config.DB_PATH)
    if readonly:
        conn = sqlite3.connect(f"file:{p.as_posix()}?mode=ro", uri=True, check_same_thread=False)
    else:
        conn = sqlite3.connect(p, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
