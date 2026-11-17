"""'What changed since the last interaction?' Pure date logic over the warehouse (no AI).

The cut-off is the latest past meeting or call (periods.last_interaction). Everything dated after it is
a change: issues opened or closed, documents received, deals updated, new survey results, actions that
fell due. Restricted deals and documents are left out unless the user may see them.
"""
import sqlite3
from dataclasses import asdict, dataclass
from datetime import date

from app import config
from app.metrics.evidence import SqlEvidence, run
from app.metrics.periods import last_interaction


@dataclass
class Change:
    kind: str          # issue_opened | issue_closed | document | deal_updated | survey | action_due
    date: str
    summary: str
    ref: str           # record id, e.g. ISS-1001, EM-1003, OPP-1001
    evidence: SqlEvidence

    def to_dict(self) -> dict:
        return {**asdict(self), "evidence": self.evidence.to_dict()}


def changes_since_last_interaction(conn: sqlite3.Connection, client_id: str, allow_restricted: bool = False,
                                   today: date | None = None) -> dict:
    today = today or config.TODAY
    last = last_interaction(conn, client_id, today)
    since, t = last["date"], today.isoformat()
    out: list[Change] = []

    def one(ev: SqlEvidence, row: dict) -> SqlEvidence:
        return SqlEvidence(ev.query, ev.params, [row], [row["source_ref"]] if row.get("source_ref") else [])

    ev = run(conn, """SELECT issue_id, opened_at, closed_at, severity, status, summary, source_ref FROM service_issues
                      WHERE client_id = ? AND ((opened_at > ? AND opened_at <= ?) OR (closed_at > ? AND closed_at <= ?))""",
             (client_id, since, t, since, t))
    for r in ev.rows:
        if r["opened_at"] > since:
            out.append(Change("issue_opened", r["opened_at"], f"Sev-{r['severity']} issue opened: {r['summary']}", r["issue_id"], one(ev, r)))
        if r["closed_at"] and r["closed_at"] > since:
            out.append(Change("issue_closed", r["closed_at"], f"Issue closed: {r['summary']}", r["issue_id"], one(ev, r)))

    ev = run(conn, """SELECT d.doc_id, d.type, d.date, d.title, d.sender, d.story_id, d.source_ref,
                             (SELECT COUNT(*) FROM documents s WHERE s.story_id = d.doc_id) - 1 AS other_outlets
                      FROM documents d
                      WHERE d.client_id = ? AND d.date > ? AND d.date <= ? AND d.duplicate_of IS NULL
                        AND (d.restricted = 0 OR ?)
                        AND (d.story_id IS NULL OR d.story_id = d.doc_id)   -- one entry per news story
                      ORDER BY d.date""", (client_id, since, t, int(allow_restricted)))
    for r in ev.rows:
        who = f" from {r['sender'].split('<')[0].strip()}" if r["sender"] else ""
        more = f" (also reported by {r['other_outlets']} other outlets)" if r["other_outlets"] > 0 else ""
        out.append(Change("document", r["date"], f"New {r['type']}{who}: {r['title']}{more}", r["doc_id"], one(ev, r)))

    ev = run(conn, """SELECT opp_id, product_code, stage, value, expected_close, updated_at, source_ref FROM pipeline
                      WHERE client_id = ? AND updated_at > ? AND updated_at <= ? AND (restricted = 0 OR ?)""",
             (client_id, since, t, int(allow_restricted)))
    for r in ev.rows:
        out.append(Change("deal_updated", r["updated_at"],
                          f"{r['opp_id']} ({r['product_code']}) now at {r['stage']}, GBP {r['value']:,}", r["opp_id"], one(ev, r)))

    ev = run(conn, """SELECT as_of, wallet_share_pct, satisfaction_score, source_ref FROM relationship_metrics
                      WHERE client_id = ? AND as_of > ? AND as_of <= ?""", (client_id, since, t))
    for r in ev.rows:
        out.append(Change("survey", r["as_of"],
                          f"New survey: satisfaction {r['satisfaction_score']}, share of wallet {r['wallet_share_pct']}%",
                          f"rel:{r['as_of']}", one(ev, r)))

    ev = run(conn, """SELECT action_id, description, due_date, status, source_ref FROM open_actions
                      WHERE client_id = ? AND due_date > ? AND due_date <= ?""", (client_id, since, t))
    for r in ev.rows:
        state = "still open" if r["status"] == "open" else r["status"]
        out.append(Change("action_due", r["due_date"], f"{r['action_id']} fell due ({state}): {r['description']}",
                          r["action_id"], one(ev, r)))

    return {
        "since": since,
        "last_interaction": last,
        "fallback": last["fallback"],      # True = no past meeting found; the 90-day window is flagged as uncertain
        "changes": sorted(out, key=lambda c: c.date),
    }
