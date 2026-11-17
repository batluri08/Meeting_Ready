# MeetingReady

**Walk into every client meeting already briefed.**

Before a client meeting, a relationship team digs through CRM records, billing data, emails, call notes
and news to work out what has changed and what to raise. MeetingReady does that in about a minute: one
briefing that answers the seven questions the team actually asks, with every sentence linked to its source.

- **Nothing made up.** Numbers come from database queries, not the AI, and a verifier removes any sentence
  its source doesn't support.
- **Honest about gaps.** Conflicting, out-of-date and restricted information is flagged, never hidden.
- **Safe by design.** People see only the clients they cover, and names are masked before anything reaches
  the AI.

A supervisor sends four agents to gather evidence in parallel, and an AI model reads the emails and
writes the briefing. Follow-up chat, suggested tasks and PDF export are built in. A prototype, running on a
synthetic data pack.

## Run it

Needs Python 3.12 with [uv](https://docs.astral.sh/uv/), and Node 20+.

**1. Backend** (terminal 1)

```
cd backend
uv sync
uv run python -m app.data_gen.generate     # write the synthetic data pack
uv run python -m app.ingest.run            # build the database and search index (first run downloads small local models)
uv run uvicorn app.main:app --port 8000
```

For live AI, create `backend/.env` from the example and set `ANTHROPIC_API_KEY` in it
(`copy .env.example .env` on Windows, `cp .env.example .env` on Mac/Linux, from `backend`). Without it the
app runs offline.

**2. Frontend** (terminal 2)

```
cd frontend
npm install
npm run dev
```

Open http://localhost:3000. Switch users at the bottom of the sidebar (Priya and Leo are analysts, Daniel
is senior) and click a client card to prepare its briefing. Data quality, Evaluation and both architecture
diagrams are in the sidebar too.

## Test

```
cd backend
uv run pytest -q                  # all tests (offline, free)
uv run python -m eval.run         # evaluation scorecard, offline
uv run python -m eval.run --live  # with Opus 5.5 + Haiku 5.5 (about $1)
```

## Layout

```
backend/
  app/          agents, api, gateway (AI calls), ingest, resolution, security, stores, metrics, data_gen
  eval/         evaluation suite and answer key
  tests/
  data/         generated: synthetic data, database, saved briefings, audit logs
frontend/       Next.js app (app/ pages, components/, lib/)
docs/           DESIGN, DATA and EVALUATION notes
architecture/   interactive diagrams: prototype and production
screenshots&Outputs/  screenshots of the app and sample briefing PDFs
```

## Screenshots

| Clients | Briefing | Chat with guarded SQL |
|---|---|---|
| ![Clients](screenshots&Outputs/1-clients.png) | ![Briefing](screenshots&Outputs/3-briefing.png) | ![Chat](screenshots&Outputs/5-chat-guarded-sql.png) |

More in [screenshots&Outputs/](screenshots&Outputs/). Sample briefing PDFs: [analyst](screenshots&Outputs/sample-briefing-kestrel-analyst.pdf),
[senior, with restricted data](screenshots&Outputs/sample-briefing-halden-senior.pdf).

## Docs

| | |
|---|---|
| [Architecture: prototype](architecture/prototype/prototype.html) · [production](architecture/production/production.html) | Interactive diagrams (also linked from the app) |
| [DESIGN](docs/DESIGN.md) | How it works: ingestion, agents, retrieval, security, where AI is and is not used, production |
| [DATA](docs/DATA.md) | The synthetic data pack and the 16 planted problems |
| [EVALUATION](docs/EVALUATION.md) | How it is tested, and the latest results |

Diagrams were made with [Archify](https://github.com/tt-a1i/archify) (not included; install it into
`.claude/skills/` to rebuild one from its `candidate.json`).
