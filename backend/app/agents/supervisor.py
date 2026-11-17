"""Supervisor: plans the briefing, runs the specialist agents, and streams sections as they finish.

1. Resolve: meeting -> client (code, via the client master) and check the user may see that client.
2. Plan: Opus (low effort) picks and orders tasks from a fixed catalogue and explains
   why; code validates the plan and adds back any required task the model left out. Offline: fixed plan.
3. Run: independent tasks run in parallel; a task waits for the tasks it depends on (e.g. commitments
   waits for email extraction and the open-actions query). A failed task is retried once, then marked
   unavailable; the briefing still completes and the gap is shown in the uncertainty panel.
4. Write + verify each section as soon as the tasks it needs are done, and emit it (for streaming).
5. Assemble the uncertainty panel in code, unmask names for the authorised user, and save the audit log.
"""
import uuid
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path
from typing import Callable

from app import config
from app.agents import structured_agent as sa
from app.agents.commitments import build_commitments
from app.agents.email_agent import run_email_agent
from app.agents.evidence import EvidenceStore, sql_source
from app.agents.news_agent import run_news_agent
from app.agents.notes_agent import run_notes_agent
from app.agents.opportunities import find_opportunities
from app.agents.synthesizer import QUESTION, SECTIONS, write_section
from app.agents.verifier import verify
from app.gateway.audit import AuditLog
from app.gateway.gateway import Gateway
from app.gateway.pii import PiiMasker
from app.metrics.evidence import run as run_sql
from app.security.permissions import load_user, require_client, restricted_summary
from app.stores import db
from app.stores.doc_index import DocIndex

PLAN_VERSION = "plan-v1"

# Task catalogue: id -> (agent, depends on, what it does)
CATALOGUE = {
    "profile": ("structured", [], "Client profile, coverage, contacts, products, relationship metrics"),
    "signals": ("structured", [], "Run materiality rules on revenue, issues, actions, deals, usage, STP, surveys"),
    "changes": ("structured", [], "List everything that changed since the last meeting or call"),
    "deals_actions": ("structured", [], "Open deals and open actions"),
    "email_extract": ("email", [], "Extract asks, promises and concerns from recent emails and threads"),
    "notes": ("notes", [], "Key passages from notes and transcripts; check for stale and conflicting statements"),
    "news": ("news", [], "Approved news, one entry per story, with conflicts between outlets"),
    "opportunities": ("structured", [], "Products to discuss, each backed by data and the client's own words"),
    "commitments": ("code", ["email_extract", "deals_actions"], "Compare asks and promises with open actions"),
}
SECTION_NEEDS = {
    "profile": ["profile", "notes"], "what_changed": ["changes"], "commitments": ["commitments"], "metrics": ["signals"],
    "opportunities": ["opportunities", "deals_actions"], "news": ["news"],
}

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "tasks": {"type": "array", "items": {
            "type": "object",
            "properties": {"id": {"type": "string", "enum": list(CATALOGUE)}, "reason": {"type": "string"}},
            "required": ["id", "reason"], "additionalProperties": False}},
        "focus": {"type": "string"},
    },
    "required": ["tasks", "focus"],
    "additionalProperties": False,
}
PLAN_SYSTEM = (
    "You plan the evidence-gathering for a pre-meeting client briefing. Choose tasks from the catalogue, in a "
    "sensible order, with a one-line reason each, and give the briefing's focus given the meeting title as a short "
    "phrase of at most 10 words (e.g. 'Payroll failures, open commitments and treasury opportunities'). Tasks with "
    "dependencies will be scheduled after their dependencies automatically."
)


def make_plan(gateway: Gateway, client_name: str, meeting_title: str) -> dict:
    catalogue = "\n".join(f"- {k}: {v[2]}" + (f" (needs {', '.join(v[1])})" if v[1] else "") for k, v in CATALOGUE.items())
    fixed = {"tasks": [{"id": k, "reason": v[2]} for k, v in CATALOGUE.items()],
             "focus": f"Prepare for: {meeting_title}"}
    plan = gateway.call("plan", PLAN_VERSION, PLAN_SYSTEM,
                        f"Client: {client_name}\nMeeting: {meeting_title}\n\nTask catalogue:\n{catalogue}",
                        PLAN_SCHEMA, offline=lambda: fixed)
    chosen = [t for t in plan.get("tasks", []) if t.get("id") in CATALOGUE]
    seen = {t["id"] for t in chosen}
    for k, v in CATALOGUE.items():       # every task is required for full coverage of the 7 questions
        if k not in seen:
            chosen.append({"id": k, "reason": f"Added by policy: {v[2]}"})
    return {"tasks": [{**t, "depends_on": CATALOGUE[t["id"]][1], "agent": CATALOGUE[t["id"]][0]} for t in chosen],
            "focus": plan.get("focus", fixed["focus"])}


def build_briefing(user_id: str, client_id: str | None = None, meeting_id: str | None = None, *,
                   idx: DocIndex, db_path: Path | None = None, mode: str | None = None,
                   on_event: Callable[[str, dict], None] | None = None, fail_tasks: set[str] | None = None,
                   audit_dir: Path | None = None, run_id: str | None = None) -> dict:
    emit = on_event or (lambda kind, data: None)
    fail_tasks = fail_tasks or set()
    db_path = Path(db_path or config.DB_PATH)
    conn = db.connect(db_path, readonly=True)
    run_id = run_id or f"run-{uuid.uuid4().hex[:10]}"
    audit = AuditLog(run_id, audit_dir)

    # ---- 1. resolve and authorise (code)
    user = load_user(conn, user_id)
    meeting_title = "Client catch-up (no meeting booked)"   # briefing on a client without a calendar meeting
    if meeting_id:
        m = conn.execute("SELECT client_id, title, start_time FROM meetings WHERE meeting_id = ?", (meeting_id,)).fetchone()
        client_id, meeting_title = m["client_id"], f"{m['title']} ({m['start_time']})"
    require_client(user, client_id)
    client_name = conn.execute("SELECT legal_name FROM clients WHERE client_id = ?", (client_id,)).fetchone()[0]
    masker = PiiMasker.from_db(conn)
    gateway = Gateway(masker, audit, mode)
    store = EvidenceStore()
    audit.log("briefing_start", user=user_id, clearance=user.clearance, client=client_id, meeting=meeting_id,
              mode=gateway.mode)
    emit("start", {"run_id": run_id, "client_id": client_id, "client_name": client_name, "meeting": meeting_title,
                   "user": {"id": user.user_id, "name": user.name, "clearance": user.clearance}, "mode": gateway.mode})

    # ---- 2. plan
    plan = make_plan(gateway, client_name, meeting_title)
    audit.log("plan", plan=plan)
    emit("plan", plan)

    # ---- 3. run tasks
    def task_fn(task_id: str, results: dict):
        c = db.connect(db_path, readonly=True)          # one read-only connection per task
        try:
            if task_id in fail_tasks:
                raise RuntimeError("forced failure (demo switch)")
            if task_id == "profile":
                return sa.profile(c, client_id, user, store)
            if task_id == "signals":
                return sa.signals(c, client_id, user, store)
            if task_id == "changes":
                return sa.changes(c, client_id, user, store)
            if task_id == "deals_actions":
                return sa.deals_and_actions(c, client_id, user, store)
            if task_id == "email_extract":
                return run_email_agent(c, client_id, user, store, gateway)
            if task_id == "notes":
                return run_notes_agent(c, idx, client_id, user, store)
            if task_id == "news":
                return run_news_agent(c, client_id, store)
            if task_id == "opportunities":
                return find_opportunities(c, idx, client_id, user, store)
            if task_id == "commitments":
                since = sa.last_interaction(c, client_id)["date"]
                return build_commitments(results["deals_actions"]["actions"], results["email_extract"]["items"],
                                         since, lambda eid: store.get(eid).source.get("date") or "")
            raise KeyError(task_id)
        finally:
            c.close()

    def attempt(task_id, results):
        for n in (1, 2):
            try:
                out = task_fn(task_id, results)
                audit.log("task", task=task_id, status="done", attempt=n)
                return out
            except Exception as e:  # noqa: BLE001
                audit.log("task", task=task_id, status="failed", attempt=n, error=f"{type(e).__name__}: {e}")
        raise RuntimeError(f"{task_id} failed twice")

    results: dict[str, dict] = {}
    unavailable: dict[str, str] = {}
    sections: dict[str, dict] = {}
    pending = {t["id"] for t in plan["tasks"]}

    def section_payload(sec: str) -> dict:
        if sec == "commitments":
            c = results["commitments"]
            ids = [a["evidence_id"] for a in c["open_actions"]] + [i["evidence_id"] for i in
                                                                   c["untracked_asks"] + c["concerns"] + c["promises"]]
            return {"evidence": list(dict.fromkeys(ids)), "commitments": c}
        if sec == "opportunities":   # products to propose + the open pipeline (restricted deals only for senior)
            deals = results["deals_actions"]["deal_evidence"]
            return {"evidence": results["opportunities"]["evidence"] + deals,
                    "opportunities": results["opportunities"]["opportunities"], "deals": deals}
        if sec == "profile":     # facts from the record, plus what the client has said matters to them
            context = results["notes"]["evidence"][:6] if "notes" in results else []
            return {"evidence": results["profile"]["evidence"] + context}
        return {"evidence": results[SECTION_NEEDS[sec][0]]["evidence"]}

    def finish_section(sec: str):
        if any(t in unavailable for t in SECTION_NEEDS[sec]):
            sections[sec] = {"id": sec, "question": QUESTION[sec], "status": "unavailable", "statements": [],
                             "dropped": []}
        else:
            payload = section_payload(sec)
            # tell the writer which facts are disputed or out of date (with their evidence, so it can cite them)
            caveats = [f for k in ("notes", "news") for f in results.get(k, {}).get("findings", [])]
            payload["caveats"] = caveats
            payload["caveat_ids"] = {e for f in caveats for e in f["evidence"]} - set(payload["evidence"])
            payload["evidence"] = list(dict.fromkeys(payload["evidence"] + sorted(payload["caveat_ids"])))
            written_sec = write_section(sec, payload, store, gateway)
            kept, dropped = verify(sec, written_sec["statements"], set(payload["evidence"]), store, audit)
            sections[sec] = {"id": sec, "question": QUESTION[sec], "status": "ok", "layout": written_sec["layout"],
                             "statements": kept, "dropped": dropped}
        emit("section", _with_evidence(_render(sections[sec], masker), store))

    written: set[str] = set()

    def write_ready_sections():
        for sec, needs in SECTION_NEEDS.items():   # write sections whose inputs are complete (done or unavailable)
            if sec not in written and all(n in results or n in unavailable for n in needs):
                written.add(sec)
                finish_section(sec)

    with ThreadPoolExecutor(max_workers=6) as pool:
        running = {}
        while pending or running:
            for t in list(pending):
                deps = CATALOGUE[t][1]
                if any(d in unavailable for d in deps):
                    pending.discard(t)
                    unavailable[t] = f"depends on unavailable task {[d for d in deps if d in unavailable]}"
                    emit("task", {"id": t, "status": "unavailable"})
                elif all(d in results for d in deps):
                    pending.discard(t)
                    emit("task", {"id": t, "status": "running"})
                    running[pool.submit(attempt, t, results)] = t
            if not running:
                break
            done, _ = wait(running, return_when=FIRST_COMPLETED)
            for fut in done:
                t = running.pop(fut)
                try:
                    results[t] = fut.result()
                    emit("task", {"id": t, "status": "done"})
                except Exception as e:  # noqa: BLE001
                    unavailable[t] = str(e)
                    emit("task", {"id": t, "status": "unavailable"})
            write_ready_sections()
    # A task can be marked unavailable on the final pass (its dependency failed last), after which the loop
    # exits; write any section that only became ready then. (Found by a test that failed ~1 run in 10.)
    write_ready_sections()

    # ---- 5. uncertainty (code only)
    unc = build_uncertainty(conn, client_id, user, results, unavailable, store)
    kept, dropped = verify("uncertainty", unc, {e for s in unc for e in s["evidence_ids"]}, store, audit)
    sections["uncertainty"] = {"id": "uncertainty", "question": QUESTION["uncertainty"], "status": "ok",
                               "statements": kept, "dropped": dropped}
    emit("section", _with_evidence(_render(sections["uncertainty"], masker), store))

    briefing = {
        "run_id": run_id, "client_id": client_id, "client_name": client_name, "meeting": meeting_title,
        "user": {"id": user.user_id, "name": user.name, "clearance": user.clearance}, "mode": gateway.mode,
        "plan": plan, "unavailable": unavailable,
        "sections": [_render(sections[s], masker) for s, _ in SECTIONS if s in sections],
        "evidence": {k: v.to_dict() for k, v in store.items.items()},
        "audit_path": str(audit.path),
    }
    audit.log("briefing_done", sections=len(briefing["sections"]),
              statements=sum(len(s["statements"]) for s in briefing["sections"]),
              dropped=sum(len(s["dropped"]) for s in briefing["sections"]))
    emit("done", {"run_id": run_id, "unavailable": unavailable})
    conn.close()
    return briefing


def _with_evidence(section: dict, store: EvidenceStore) -> dict:
    """Streamed sections carry the evidence they cite, so the drawer works before the briefing finishes."""
    ids = {e for s in section["statements"] for e in s.get("evidence_ids", [])}
    return {**section, "evidence": {i: store.get(i).to_dict() for i in sorted(ids, key=lambda x: int(x[1:]))}}


def _render(section: dict, masker: PiiMasker) -> dict:
    """Restore real names for the authorised user, only at the very end."""
    return {**section, "statements": [{**s, "text": masker.unmask(s["text"]), **({"label": masker.unmask(s["label"])} if s.get("label") else {})}
                                      for s in section["statements"]]}


def build_uncertainty(conn, client_id, user, results, unavailable, store: EvidenceStore) -> list[dict]:
    items = []
    for key in ("notes", "news"):
        for f in results.get(key, {}).get("findings", []):
            label = {"conflict": "Conflicting information", "stale": "Out of date"}[f["kind"]]
            items.append({"text": f"{label}: {f['detail']}", "evidence_ids": f["evidence"], "kind": f["kind"]})

    rs = restricted_summary(conn, client_id)
    if rs["exists"] and not user.allow_restricted:
        counts = run_sql(conn, """SELECT (SELECT COUNT(*) FROM pipeline WHERE client_id = ? AND restricted = 1) AS restricted_deals,
                                         (SELECT COUNT(*) FROM documents WHERE client_id = ? AND restricted = 1) AS restricted_documents""",
                         (client_id, client_id))
        ev = store.add("restricted", "Restricted records (count only)",
                       f"Restricted records exist: {rs['restricted_deals']} deal(s), {rs['restricted_documents']} document(s)",
                       sql_source(counts))
        items.append({"text": f"Restricted information exists for this client ({rs['restricted_deals']} deal(s), "
                              f"{rs['restricted_documents']} document(s)) and is hidden at your access level.",
                      "evidence_ids": [ev.id], "kind": "restricted"})

    ch = results.get("changes")
    if ch and ch["fallback"]:
        ev = store.add("system", "No recent meeting", f"No past meeting or call on record; changes shown since {ch['since']}",
                       {"type": "sql", "query": "SELECT * FROM interactions WHERE client_id = ?", "params": [client_id],
                        "rows": [], "refs": []})
        items.append({"text": f"No past meeting is on record, so 'what changed' covers the last 90 days (since {ch['since']}).",
                      "evidence_ids": [ev.id], "kind": "gap"})

    review = run_sql(conn, """SELECT source_system, source_id, source_name, confidence, reason FROM client_xref
                              WHERE candidate_client_id = ? AND status = 'review'""", (client_id,))
    for r in review.rows:
        ev = store.add("match", f"Review: {r['source_id']}",
                       f"{r['source_system']} account {r['source_id']} '{r['source_name']}' may belong to this client "
                       f"(confidence {r['confidence']}); awaiting review", sql_source(review))
        items.append({"text": f"Possible match awaiting review: {r['source_system']} account {r['source_id']} "
                              f"'{r['source_name']}' (confidence {r['confidence']}); its data is excluded until confirmed.",
                      "evidence_ids": [ev.id], "kind": "low_confidence"})

    by_domain = run_sql(conn, """SELECT doc_id, match_method, match_confidence, sender FROM documents
                                 WHERE client_id = ? AND match_method = 'email_domain'""", (client_id,))
    for r in by_domain.rows:
        ev = store.add("match", f"{r['doc_id']} matched by domain",
                       f"{r['doc_id']} had no account ID; matched by sender email domain (confidence {r['match_confidence']})",
                       sql_source(by_domain))
        items.append({"text": f"{r['doc_id']} had no account ID and was linked to this client by the sender's email "
                              f"domain (confidence {r['match_confidence']}).", "evidence_ids": [ev.id], "kind": "low_confidence"})

    inj = run_sql(conn, "SELECT doc_id, date FROM documents WHERE client_id = ? AND injection_flag = 1", (client_id,))
    for r in inj.rows:
        ev = store.add("security", f"{r['doc_id']} injection", f"{r['doc_id']} ({r['date']}) contains instructions aimed at the AI",
                       sql_source(inj))
        items.append({"text": f"{r['doc_id']} contained text trying to instruct the AI; it was treated as data and ignored.",
                      "evidence_ids": [ev.id], "kind": "security"})

    for task, reason in unavailable.items():
        ev = store.add("system", f"Task {task} unavailable", f"Task '{task}' could not complete: {reason}",
                       {"type": "system", "task": task, "reason": reason})
        items.append({"text": f"Unavailable: '{task}' could not be completed ({reason}); related content may be missing.",
                      "evidence_ids": [ev.id], "kind": "unavailable"})
    if not items:
        items.append({"text": "No conflicts, stale statements, restricted records or gaps were found.", "evidence_ids": [],
                      "empty": True})
    return items
