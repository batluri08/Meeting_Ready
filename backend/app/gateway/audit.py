"""Audit log: one JSON line per event (plan, tool call, model call, verifier drop, injection caught).

Stored per briefing run in data/audit/<run_id>.jsonl. Prompts are logged AFTER masking, so the log
itself contains no personal data.
"""
import json
import threading
from datetime import datetime, timezone
from pathlib import Path

from app import config

_lock = threading.Lock()


class AuditLog:
    def __init__(self, run_id: str, directory: Path | None = None):
        self.run_id = run_id
        self.dir = Path(directory or config.AUDIT_DIR)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / f"{run_id}.jsonl"
        self.events: list[dict] = []

    def log(self, event: str, **data) -> None:
        rec = {"ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"), "run_id": self.run_id,
               "event": event, **data}
        with _lock:
            self.events.append(rec)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec, default=str) + "\n")
