# Design

How MeetingReady turns messy bank data into a cited briefing. Diagrams:
[prototype](../architecture/prototype/prototype.html) · [production](../architecture/production/production.html).

**Rule throughout: the model writes and extracts words; code decides facts, numbers and access.**

## 1. Flow

```
synthetic data pack → ingestion (once) → SQLite + Qdrant
banker opens a client → supervisor plans 9 tasks → 4 agents gather evidence in parallel
→ section writer answers 7 questions → verifier checks every sentence → streamed to the app
```

## 2. Ingestion ([app/ingest](../backend/app/ingest), [app/resolution](../backend/app/resolution))

| Step | What it does |
|---|---|
| Load | 15 CSV tables and 54 markdown documents |
| Client matching | Website domain + cleaned name. Same domain merges; name-only matches (≤ 0.85) go to a review queue; different domains never merge |
| Clean and dedupe | Strip quoted replies, sign-offs, disclaimers; split threads into messages; hash to drop repeats |
| Chunk | By type: one email message, one thread message, speaker-turn windows (1-turn overlap), page or section. Max 220 words, 1-sentence overlap, plus a header (client · type · date · page) |
| Embed | bge-small-en-v1.5, 384-d, local (fastembed) |
| News | Same story = similarity ≥ 0.85, same client, ≤ 7 days; outlets that disagree on figures are flagged |

Everything is stored in SQLite (`backend/data/briefing.db`), vectors included. Qdrant runs in memory and
is loaded from SQLite at startup: one source of truth, a disposable index.

## 3. Agents ([app/agents](../backend/app/agents))

One supervisor, 4 agents and one code check share 9 tasks, run in parallel on a thread pool. No agent
framework: the flow is a fixed graph, so plain Python keeps every step predictable and auditable.

| Agent | Tasks | Model |
|---|---|---|
| Supervisor | Plans the tasks, sets the focus; retries a failed task once, then marks it unavailable | Opus 5.5 |
| Structured agent | profile, signals, changes, deals and actions, opportunities (SQL + 8 importance rules) | none |
| Email agent | Asks, promises and concerns from the last 120 days | Haiku 5.5 |
| Notes agent | Notes and transcripts; flags stale or conflicting statements | none |
| News agent | Approved news, one entry per story | none |
| Commitments check | Client asks vs open actions → untracked asks | none |
| Section writer | Per question: a direct answer, labelled points, "why it matters" | Opus 5.5 |
| Verifier | Drops any sentence without a valid citation or with a number not in its source | none |
| Uncertainty panel | Conflicts, stale facts, restricted data, failed tasks, injection attempts | none |
| Chat | Routes each question; writes one SQL query; answers in 1–4 cited statements | Opus 5.5 |

Importance rules: revenue change > 10% a quarter, Sev 1–2 issue open > 14 days, overdue action, deal closing
within 60 days, product use < 30%, STP < 95%, satisfaction drop ≥ 2, wallet share drop ≥ 5.

## 4. Retrieval and context

- **Hybrid search:** BM25 + vectors, fused by rank (RRF, k = 60). Client, clearance and document type are
  filters applied before ranking.
- **Reranker:** Jina turbo cross-encoder on the top 20, chat only (more precise first result; about 1 s
  slower, so the briefing's ~15 searches skip it).
- **Text-to-SQL:** Opus writes one SELECT; the SQL guard (sqlglot) allows listed tables and columns only,
  rewrites every table to this client and access level, runs read-only, max 200 rows, 2 s.
- **Date questions** ("what happened on 13 November?") are answered by code from every dated table.
- **Context:** every fact is an evidence item (E1, E2…) with its source; the writer sees only its section's
  evidence and may cite only those ids (enforced by JSON schema). Chat keeps the client, the briefing's
  evidence and the last 3 questions.

## 5. Security and guardrails

| Where | Control |
|---|---|
| API | Users see only clients they cover (403 otherwise) |
| Search | Filtered by client and clearance before ranking |
| SQL | Guard rescopes every query; read-only connection |
| Restricted data | Senior only; analysts see a count |
| AI gateway ([app/gateway](../backend/app/gateway)) | Names and emails masked before any prompt; documents wrapped as untrusted text; allowed-id schemas; model routing; audit log; offline fallback |
| Output | Verifier; uncertainty panel built by code |

## 6. App ([frontend](../frontend)) and API ([app/api](../backend/app/api))

Clients home (cards with the next meeting; catch-up briefing when none) → briefing page that streams
section by section (SSE), with sources one click away, chat beside it, tasks with suggestions from Opus,
PDF export and an email draft. Sidebar: Clients, Tasks, Data quality, Evaluation, architecture diagrams.
Main endpoints: `GET /api/clients`, `POST /api/briefings`, `GET /api/briefings/{id}/stream`,
`POST /api/briefings/{id}/chat`, `POST /api/briefings/{id}/actions/{name}`, `GET /api/eval/latest`.

## 7. Production

Same engine; what changes around it:

| Prototype | Production |
|---|---|
| Synthetic CSV + markdown | CRM, core banking, Microsoft 365 (Graph), SharePoint, licensed news |
| Ingestion script | CDC/ELT, dbt with data-quality tests, client master (MDM), access + PII tagging, Airflow or Dagster |
| SQLite, in-memory Qdrant | Snowflake or Databricks (row-level security), PostgreSQL, Qdrant cluster |
| Python functions | MCP servers, called with the banker's own token |
| In-process run | Temporal workflow, started by a calendar event 24 h before the meeting |
| User dropdown | Entra ID sign-in, information barriers |
| Script + tests | CI gate, live eval on every change, sampled RAGAS judge, analyst feedback |
