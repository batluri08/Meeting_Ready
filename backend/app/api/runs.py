"""Briefing runs: each runs in a background thread and records its events, so the browser can stream them.

Every event is kept in order. A stream subscriber reads from the start and then waits for new events,
so a page that connects late (or reconnects) still receives the whole briefing.

Finished runs are saved to disk (data/runs/<run_id>.json), so a server restart does not lose briefings
that are open in someone's browser: they are reloaded on demand, events and all.
"""
import json
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Run:
    run_id: str
    user_id: str
    client_id: str
    meeting_id: str | None
    events: list[tuple[str, dict]] = field(default_factory=list)
    done: bool = False
    briefing: dict | None = None
    error: str | None = None
    chat: list[dict] = field(default_factory=list)       # conversation history for follow-ups
    tasks: list[dict] = field(default_factory=list)      # tasks created from the briefing (mock CRM)
    suggestions: list[dict] | None = None                # tasks Opus suggested (asked once, then kept)
    store: Any = None                                    # chat session evidence (built from the briefing)
    created_at: str = field(default_factory=_now)
    cond: threading.Condition = field(default_factory=threading.Condition, repr=False)
    on_finish: Any = field(default=None, repr=False)     # set by the registry: saves the run to disk

    def emit(self, kind: str, data: dict) -> None:
        with self.cond:
            self.events.append((kind, data))
            self.cond.notify_all()

    def finish(self, briefing: dict | None = None, error: str | None = None) -> None:
        with self.cond:
            self.briefing, self.error, self.done = briefing, error, True
            self.cond.notify_all()
        if self.on_finish:
            self.on_finish(self)

    def wait_events(self, start: int, timeout: float = 15.0) -> tuple[list[tuple[str, dict]], bool]:
        """Events from index `start` on; blocks up to `timeout` if there are none yet."""
        with self.cond:
            if len(self.events) <= start and not self.done:
                self.cond.wait(timeout)
            return self.events[start:], self.done

    def to_json(self) -> dict:
        return {"run_id": self.run_id, "user_id": self.user_id, "client_id": self.client_id,
                "meeting_id": self.meeting_id, "created_at": self.created_at, "events": self.events,
                "briefing": self.briefing, "error": self.error, "chat": self.chat, "tasks": self.tasks,
                "suggestions": self.suggestions}

    def summary(self) -> dict:
        """What the 'Recent briefings' list shows."""
        b = self.briefing or {}
        start = next((d for k, d in self.events if k == "start"), {})
        sections = b.get("sections", [])
        return {
            "run_id": self.run_id, "client_id": self.client_id, "meeting_id": self.meeting_id,
            "client_name": b.get("client_name") or start.get("client_name"),
            "meeting": b.get("meeting") or start.get("meeting"),
            "mode": b.get("mode") or start.get("mode"), "created_at": self.created_at,
            "status": "failed" if self.error else ("complete" if self.done else "in progress"),
            "unavailable": sorted((b.get("unavailable") or {}).keys()),
            "statements": sum(len(s["statements"]) for s in sections),
            "questions_asked": len(self.chat), "tasks_created": len(self.tasks),
        }


class RunRegistry:
    def __init__(self, persist_dir: Path | None = None):
        self._runs: dict[str, Run] = {}
        self._lock = threading.Lock()
        self.schedules: list[dict[str, Any]] = []
        self.persist_dir = Path(persist_dir) if persist_dir else None
        if self.persist_dir:
            self.persist_dir.mkdir(parents=True, exist_ok=True)

    def create(self, user_id: str, client_id: str, meeting_id: str | None) -> Run:
        run = Run(f"run-{uuid.uuid4().hex[:10]}", user_id, client_id, meeting_id, on_finish=self.save)
        with self._lock:
            self._runs[run.run_id] = run
        return run

    def save(self, run: Run) -> None:
        """Persist a finished run (briefing, events, chat history, tasks)."""
        if not self.persist_dir or not run.done:
            return
        path = self.persist_dir / f"{run.run_id}.json"
        path.write_text(json.dumps(run.to_json(), default=str), encoding="utf-8")

    def get(self, run_id: str) -> Run | None:
        run = self._runs.get(run_id)
        if run is not None or not self.persist_dir:
            return run
        path = self.persist_dir / f"{run_id}.json"            # e.g. after a server restart
        if not path.exists() or not run_id.replace("-", "").isalnum():
            return None
        run = self._load(path)
        with self._lock:
            self._runs[run_id] = run
        return run

    def _load(self, path: Path) -> Run:
        d = json.loads(path.read_text(encoding="utf-8"))
        created = d.get("created_at") or datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(timespec="seconds")
        return Run(d["run_id"], d["user_id"], d["client_id"], d["meeting_id"],
                   events=[tuple(e) for e in d["events"]], done=True, briefing=d["briefing"], error=d["error"],
                   chat=d["chat"], tasks=d["tasks"], suggestions=d.get("suggestions"), created_at=created,
                   on_finish=self.save)

    def delete(self, run_id: str) -> bool:
        """Remove a briefing from memory and storage. The audit log is kept (it is the compliance record)."""
        with self._lock:
            found = self._runs.pop(run_id, None) is not None
        if self.persist_dir:
            path = self.persist_dir / f"{run_id}.json"
            if path.exists():
                path.unlink()
                found = True
        return found

    def tasks_for_user(self, user_id: str, client_ids: set[str]) -> list[tuple[dict, dict]]:
        """(task, context) pairs for all of a user's tasks; context says which briefing and client it came from."""
        out = []
        for run in self._user_runs(user_id).values():
            if run.client_id not in client_ids:
                continue
            s = run.summary()
            for t in run.tasks:
                out.append((t, {"run_id": run.run_id, "client_name": s["client_name"], "meeting": s["meeting"]}))
        return out

    def _user_runs(self, user_id: str) -> dict[str, Run]:
        runs = {r.run_id: r for r in list(self._runs.values()) if r.user_id == user_id}
        if self.persist_dir:
            for path in self.persist_dir.glob("run-*.json"):
                if path.stem in runs:
                    continue
                try:
                    r = self._load(path)
                except (ValueError, KeyError):
                    continue                      # unreadable file: skip rather than break the list
                if r.user_id == user_id:
                    runs[r.run_id] = r
        return runs

    def list_for_user(self, user_id: str, client_ids: set[str], limit: int = 20) -> list[dict]:
        """The user's own briefings (saved and in progress), newest first, for clients they still cover."""
        rows = [r.summary() for r in self._user_runs(user_id).values() if r.client_id in client_ids]
        return sorted(rows, key=lambda x: x["created_at"], reverse=True)[:limit]
