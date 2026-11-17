"""HTTP API. The current user comes from the `X-User-Id` header (or `?user=` for the event stream, since a
browser EventSource cannot set headers). Every endpoint checks what that user may see.
"""
import json
import threading
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from app import config
from app.agents import actions
from app.agents.chat import answer, evidence_from_briefing
from app.agents.supervisor import build_briefing
from app.gateway.audit import AuditLog
from app.gateway.gateway import Gateway
from app.gateway.pii import PiiMasker
from app.security.permissions import PermissionDenied, UserContext, can_view_client, load_user
from app.security.sql_guard import SqlGuard
from app.stores import db

router = APIRouter(prefix="/api")


# ---------------------------------------------------------------- helpers
def _conn(request: Request):
    return db.connect(request.app.state.db_path, readonly=True)


def current_user(request: Request, x_user_id: str | None = Header(default=None), user: str | None = Query(default=None)) -> UserContext:
    conn = _conn(request)
    try:
        return load_user(conn, x_user_id or user or "U-ANA")
    except PermissionDenied as e:
        raise HTTPException(401, str(e))
    finally:
        conn.close()


def _run_for(request: Request, run_id: str, user: UserContext):
    run = request.app.state.runs.get(run_id)
    if run is None:
        raise HTTPException(404, "Unknown briefing run")
    if run.user_id != user.user_id:
        raise HTTPException(403, "This briefing belongs to another user")
    return run


def _require_done(run):
    if not run.done or run.briefing is None:
        raise HTTPException(409, "The briefing is still being prepared" if not run.done else f"Briefing failed: {run.error}")


def _gateway_for(request: Request, run) -> Gateway:
    conn = _conn(request)
    try:
        masker = PiiMasker.from_db(conn)
    finally:
        conn.close()
    return Gateway(masker, AuditLog(run.run_id, request.app.state.audit_dir), run.briefing["mode"])


# ---------------------------------------------------------------- users and meetings
@router.get("/users")
def users(request: Request):
    conn = _conn(request)
    rows = [dict(r) for r in conn.execute("SELECT user_id, name, team, clearance FROM users ORDER BY user_id")]
    conn.close()
    return rows


@router.get("/me")
def me(user: UserContext = Depends(current_user)):
    return {"user_id": user.user_id, "name": user.name, "clearance": user.clearance, "clients": sorted(user.client_ids)}


@router.get("/meetings")
def meetings(request: Request, user: UserContext = Depends(current_user)):
    conn = _conn(request)
    rows = conn.execute("""SELECT m.meeting_id, m.client_id, c.legal_name AS client_name, m.start_time, m.title, m.attendees
                           FROM meetings m JOIN clients c USING(client_id) ORDER BY m.start_time""").fetchall()
    conn.close()
    return [dict(r) for r in rows if can_view_client(user, r["client_id"])]


@router.get("/clients")
def clients(request: Request, user: UserContext = Depends(current_user)):
    """The clients this user covers, each with a short snapshot for the home page: who they are, the next
    meeting, and what the importance rules flag (the same code-only rules the briefing uses; no model)."""
    from app.metrics.rules import evaluate
    conn = _conn(request)
    try:
        out = []
        for c in conn.execute("""SELECT c.client_id, c.legal_name AS client_name, c.industry, c.region, c.segment, c.tier,
                                        c.client_since, cv.role
                                 FROM clients c JOIN coverage cv ON cv.client_id = c.client_id AND cv.user_id = ?
                                 ORDER BY c.legal_name""", (user.user_id,)):
            if not can_view_client(user, c["client_id"]):
                continue
            meetings = [dict(m) for m in conn.execute(
                "SELECT meeting_id, start_time, title FROM meetings WHERE client_id = ? AND start_time >= ? ORDER BY start_time",
                (c["client_id"], config.TODAY.isoformat()))]
            signals = evaluate(conn, c["client_id"], allow_restricted=user.allow_restricted)
            order = {"high": 0, "medium": 1}
            signals.sort(key=lambda s: order.get(s.severity, 2))
            out.append({**dict(c), "meetings": meetings,
                        "signals": [{"rule": s.rule, "title": s.title, "severity": s.severity} for s in signals]})
        out.sort(key=lambda c: (not c["meetings"], c["meetings"][0]["start_time"] if c["meetings"] else c["client_name"]))
        return out
    finally:
        conn.close()


# ---------------------------------------------------------------- briefings
class BriefingRequest(BaseModel):
    meeting_id: str | None = None             # a calendar meeting, or
    client_id: str | None = None              # just a client: a catch-up briefing with no meeting booked
    mode: str | None = None                   # 'offline' to force rules/templates; default: Claude if a key is set
    fail_tasks: list[str] = []                # demo switch: force these agents to fail


@router.post("/briefings")
def start_briefing(req: BriefingRequest, request: Request, user: UserContext = Depends(current_user)):
    conn = _conn(request)
    try:
        if req.meeting_id:
            m = conn.execute("SELECT client_id FROM meetings WHERE meeting_id = ?", (req.meeting_id,)).fetchone()
            if m is None:
                raise HTTPException(404, "Unknown meeting")
            client_id = m["client_id"]
        elif req.client_id:
            if conn.execute("SELECT 1 FROM clients WHERE client_id = ?", (req.client_id,)).fetchone() is None:
                raise HTTPException(404, "Unknown client")
            client_id = req.client_id
        else:
            raise HTTPException(422, "Give a meeting_id or a client_id")
    finally:
        conn.close()
    if not can_view_client(user, client_id):
        raise HTTPException(403, f"{user.name} does not cover this client")
    mode = "offline" if req.mode == "offline" else config.resolved_llm_mode()
    run = request.app.state.runs.create(user.user_id, client_id, req.meeting_id)
    state = request.app.state

    def work():
        try:
            b = build_briefing(user.user_id, client_id=client_id, meeting_id=req.meeting_id, idx=state.index, db_path=state.db_path,
                               mode=mode, on_event=run.emit, fail_tasks=set(req.fail_tasks),
                               audit_dir=state.audit_dir, run_id=run.run_id)
            run.finish(briefing=b)
        except Exception as e:  # noqa: BLE001
            run.emit("error", {"message": f"{type(e).__name__}: {e}"})
            run.finish(error=str(e))

    threading.Thread(target=work, daemon=True).start()
    return {"run_id": run.run_id, "mode": mode}


@router.get("/briefings")
def list_briefings(request: Request, user: UserContext = Depends(current_user)):
    """The current user's own briefings, newest first (saved ones survive restarts)."""
    return request.app.state.runs.list_for_user(user.user_id, set(user.client_ids))


@router.get("/briefings/{run_id}/stream")
def stream(run_id: str, request: Request, user: UserContext = Depends(current_user)):
    """Server-Sent Events: start, plan, task (status changes), section (as each is ready), done, end."""
    run = _run_for(request, run_id, user)

    def events():
        i = 0
        while True:
            batch, done = run.wait_events(i)
            if not batch and not done:
                yield ": keep-alive\n\n"
                continue
            for kind, data in batch:
                yield f"event: {kind}\ndata: {json.dumps(data, default=str)}\n\n"
            i += len(batch)
            if done and i >= len(run.events):
                yield "event: end\ndata: {}\n\n"
                return

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/briefings/{run_id}")
def get_briefing(run_id: str, request: Request, user: UserContext = Depends(current_user)):
    run = _run_for(request, run_id, user)
    return {"run_id": run.run_id, "done": run.done, "error": run.error, "briefing": run.briefing}


@router.delete("/briefings/{run_id}")
def delete_briefing(run_id: str, request: Request, user: UserContext = Depends(current_user)):
    """Delete one of your own finished briefings. The audit log keeps a record that it existed and was deleted."""
    run = _run_for(request, run_id, user)
    if not run.done:
        raise HTTPException(409, "This briefing is still being prepared; delete it once it has finished")
    request.app.state.runs.delete(run_id)
    AuditLog(run_id, request.app.state.audit_dir).log("briefing_deleted", user=user.user_id, client=run.client_id)
    return {"status": "deleted", "run_id": run_id}


@router.get("/briefings/{run_id}/evidence/{evidence_id}")
def evidence(run_id: str, evidence_id: str, request: Request, user: UserContext = Depends(current_user)):
    run = _run_for(request, run_id, user)
    _require_done(run)
    store = run.store or evidence_from_briefing(run.briefing)
    ev = store.get(evidence_id)
    if ev is None:
        raise HTTPException(404, "Unknown evidence id")
    return ev.to_dict()


@router.get("/briefings/{run_id}/export.pdf")
def export_pdf(run_id: str, request: Request, user: UserContext = Depends(current_user)):
    """The briefing as a printable PDF one-pager (with numbered sources)."""
    run = _run_for(request, run_id, user)
    _require_done(run)
    filename, pdf = actions.export_pdf(run.briefing)
    AuditLog(run.run_id, request.app.state.audit_dir).log("action", type="export_pdf", bytes=len(pdf))
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/briefings/{run_id}/audit")
def audit(run_id: str, request: Request, user: UserContext = Depends(current_user)):
    run = _run_for(request, run_id, user)
    path = request.app.state.audit_dir / f"{run.run_id}.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []


# ---------------------------------------------------------------- chat
class ChatRequest(BaseModel):
    question: str


@router.post("/briefings/{run_id}/chat")
def chat(run_id: str, req: ChatRequest, request: Request, user: UserContext = Depends(current_user)):
    run = _run_for(request, run_id, user)
    _require_done(run)
    if run.store is None:
        run.store = evidence_from_briefing(run.briefing)
    conn = _conn(request)
    try:
        result = answer(req.question, client_id=run.client_id, user=user, store=run.store, history=run.chat,
                        guard=SqlGuard(conn), idx=request.app.state.index, gateway=_gateway_for(request, run))
    finally:
        conn.close()
    run.chat.append({"question": req.question, "answer": result["answer"]})
    request.app.state.runs.save(run)
    return result


@router.post("/briefings/{run_id}/chat/reset")
def chat_reset(run_id: str, request: Request, user: UserContext = Depends(current_user)):
    run = _run_for(request, run_id, user)
    run.chat.clear()
    run.store = None
    return {"status": "conversation cleared"}


# ---------------------------------------------------------------- actions
class ActionRequest(BaseModel):
    description: str | None = None
    due_date: str | None = None
    hours_before: int = 24
    refresh: bool = False                     # suggest_tasks: ask the model again instead of reusing


@router.post("/briefings/{run_id}/actions/{action}")
def action(run_id: str, action: str, req: ActionRequest, request: Request, user: UserContext = Depends(current_user)):
    run = _run_for(request, run_id, user)
    _require_done(run)
    b = run.briefing
    if action == "draft_email":
        return actions.draft_email(b, _gateway_for(request, run))
    if action == "export":
        return actions.export_markdown(b)
    if action == "create_task":
        if not req.description:
            raise HTTPException(422, "description is required")
        task = {"task_id": f"TASK-{len(run.tasks) + 1:03d}", "client_id": run.client_id, "owner": user.name,
                "description": req.description, "due_date": req.due_date, "status": "open",
                "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "system": "mock CRM (production: the bank's CRM via crm-mcp, after approval)"}
        run.tasks.append(task)
        request.app.state.runs.save(run)
        AuditLog(run.run_id, request.app.state.audit_dir).log("action", type="create_task", task=task)
        return task
    if action == "suggest_tasks":
        # asked once per briefing, then kept with it (no model call each time the page opens)
        if run.suggestions is None or req.refresh:
            conn = _conn(request)
            m = conn.execute("SELECT start_time FROM meetings WHERE meeting_id = ?", (run.meeting_id,)).fetchone()
            conn.close()
            run.suggestions = actions.suggest_tasks(b, run.tasks, m["start_time"] if m else None, config.TODAY,
                                                    _gateway_for(request, run))["suggestions"]
            request.app.state.runs.save(run)
        made = {t["description"] for t in run.tasks}            # hide suggestions already added as tasks
        return {"suggestions": [s for s in run.suggestions if s["description"] not in made],
                "source": "opus" if b.get("mode") == "anthropic" else "rules"}     # who made them, for the label
    if action == "schedule":
        conn = _conn(request)
        m = conn.execute("SELECT meeting_id, start_time FROM meetings WHERE meeting_id = ?", (run.meeting_id,)).fetchone()
        conn.close()
        if m is None:
            raise HTTPException(409, "This briefing is not linked to a calendar meeting")
        sched = actions.schedule_briefing(dict(m), req.hours_before)
        request.app.state.runs.schedules.append({**sched, "user_id": user.user_id})
        return sched
    raise HTTPException(404, f"Unknown action '{action}'")


# ---------------------------------------------------------------- tasks
def _task_view(task: dict) -> dict:
    """Older tasks were saved with a descriptive status; treat anything not 'done' as open."""
    return {**task, "status": "done" if task.get("status") == "done" else "open"}


@router.get("/briefings/{run_id}/tasks")
def briefing_tasks(run_id: str, request: Request, user: UserContext = Depends(current_user)):
    run = _run_for(request, run_id, user)
    return [_task_view(t) for t in run.tasks]


class TaskUpdate(BaseModel):
    status: str                                # open | done


@router.patch("/briefings/{run_id}/tasks/{task_id}")
def update_task(run_id: str, task_id: str, req: TaskUpdate, request: Request, user: UserContext = Depends(current_user)):
    if req.status not in ("open", "done"):
        raise HTTPException(422, "status must be 'open' or 'done'")
    run = _run_for(request, run_id, user)
    task = next((t for t in run.tasks if t["task_id"] == task_id), None)
    if task is None:
        raise HTTPException(404, "Unknown task")
    task["status"] = req.status
    task["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    request.app.state.runs.save(run)
    AuditLog(run.run_id, request.app.state.audit_dir).log("task_update", task_id=task_id, status=req.status)
    return _task_view(task)


@router.get("/tasks")
def my_tasks(request: Request, user: UserContext = Depends(current_user)):
    """All of the current user's tasks, across their briefings (for clients they still cover)."""
    return [{**_task_view(t), **ctx} for t, ctx in request.app.state.runs.tasks_for_user(user.user_id, set(user.client_ids))]


# ---------------------------------------------------------------- data quality and evaluation
@router.get("/review-queue")
def review_queue(request: Request, user: UserContext = Depends(current_user)):
    conn = _conn(request)
    rows = conn.execute("""SELECT x.source_system, x.source_id, x.source_name, x.source_domain, x.candidate_client_id,
                                  c.legal_name AS candidate_name, x.confidence, x.match_method, x.reason
                           FROM client_xref x LEFT JOIN clients c ON c.client_id = x.candidate_client_id
                           WHERE x.status = 'review'""").fetchall()
    conn.close()
    return [dict(r) for r in rows if can_view_client(user, r["candidate_client_id"])]


@router.get("/matches")
def matches(request: Request, user: UserContext = Depends(current_user)):
    """The customer master crosswalk for the user's clients: how every source account was matched."""
    conn = _conn(request)
    rows = conn.execute("""SELECT x.*, c.legal_name AS client_name FROM client_xref x
                           LEFT JOIN clients c ON c.client_id = COALESCE(x.client_id, x.candidate_client_id)
                           ORDER BY COALESCE(x.client_id, x.candidate_client_id), x.source_system, x.source_id""").fetchall()
    conn.close()
    return [dict(r) for r in rows if can_view_client(user, r["client_id"] or r["candidate_client_id"])]


@router.get("/eval/latest")
def eval_latest(mode: str | None = None):
    """The latest scorecard: the live run (the real system) by default, falling back to offline.
    A later offline run (e.g. the test suite) no longer hides the live results."""
    results = config.EVAL_DIR / "results"
    names = [f"latest-{mode}.json"] if mode else ["latest-anthropic.json", "latest-offline.json", "latest.json"]
    path = next((results / n for n in names if (results / n).exists()), None)
    if path is None:
        raise HTTPException(404, "No evaluation has been run yet")
    out = json.loads(path.read_text(encoding="utf-8"))
    out["other_modes"] = sorted(m for m in ("anthropic", "offline") if (results / f"latest-{m}.json").exists())
    return out
