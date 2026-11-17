# MeetingReady

Prepares a cited, trustworthy briefing before a client meeting from messy bank data: emails, call notes,
CRM and billing records, news. Every sentence links to its source and every number is checked.
This is a prototype running on a synthetic data pack.

- Answers 7 questions per client: who they are, what changed, open asks, material metrics, opportunities,
  news, and what is uncertain.
- A supervisor runs 4 agents in parallel; Claude (Opus 5.5, Haiku 5.5) writes; a verifier checks.
- Chat for follow-ups (guarded Text-to-SQL), tasks, PDF export, and an evaluation scorecard.
- Works offline (rules and templates) when no API key is set.

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

For live AI, copy `backend/.env.example` to `backend/.env` and set `ANTHROPIC_API_KEY`. Without it the app
runs offline.

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
