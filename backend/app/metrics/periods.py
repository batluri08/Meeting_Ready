"""Date logic (code, not AI): quarters and 'since the last interaction'."""
import sqlite3
from datetime import date, timedelta

from app import config

FALLBACK_DAYS = 90


def quarter_months(year: int, q: int) -> list[str]:
    start = 3 * (q - 1) + 1
    return [f"{year}-{m:02d}" for m in range(start, start + 3)]


def latest_complete_quarters(today: date | None = None) -> tuple[tuple[int, int], tuple[int, int]]:
    """((year, q) of the latest complete quarter, (year, q) of the one before).
    On 2026-11-16 the latest complete quarter is Q3 2026, compared with Q2 2026."""
    today = today or config.TODAY
    q_now = (today.month - 1) // 3 + 1
    y, q = (today.year, q_now - 1) if q_now > 1 else (today.year - 1, 4)
    prev = (y, q - 1) if q > 1 else (y - 1, 4)
    return (y, q), prev


def last_interaction(conn: sqlite3.Connection, client_id: str, today: date | None = None) -> dict:
    """The most recent past meeting or call. If none exists, fall back to the last 90 days and say so."""
    today = today or config.TODAY
    row = conn.execute(
        """SELECT interaction_id, date, type, summary_doc_id, source_ref FROM interactions
           WHERE client_id = ? AND date < ? ORDER BY date DESC LIMIT 1""",
        (client_id, today.isoformat()),
    ).fetchone()
    if row:
        return {**dict(row), "fallback": False}
    since = (today - timedelta(days=FALLBACK_DAYS)).isoformat()
    return {"interaction_id": None, "date": since, "type": None, "summary_doc_id": None,
            "source_ref": None, "fallback": True}
