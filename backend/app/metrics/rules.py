"""Materiality rules: which numbers matter enough to put in front of the team.

Every rule is a fixed SQL query plus a threshold, written in code (no AI). Each fired rule becomes a
Signal that carries the number, the threshold and the evidence (query + rows), so it can be re-checked.

Thresholds live in RULES below, so they are easy to read, discuss and change.
"""
import sqlite3
from dataclasses import asdict, dataclass
from datetime import date

from app import config
from app.metrics.evidence import SqlEvidence, run
from app.metrics.periods import latest_complete_quarters, quarter_months

RULES = {
    "revenue_qoq": {"threshold": 10.0, "text": "Revenue changed more than 10% quarter on quarter"},
    "issue_aged": {"threshold": 14, "text": "Severity 1-2 service issue open more than 14 days"},
    "action_past_due": {"threshold": 0, "text": "Open action past its due date"},
    "pipeline_closing": {"threshold": 60, "text": "Pipeline deal expected to close within 60 days"},
    "low_utilization": {"threshold": 30, "text": "Product utilization below 30%"},
    "stp_low": {"threshold": 95.0, "text": "Payments STP rate below 95% in the latest month"},
    "satisfaction_drop": {"threshold": 2.0, "text": "Client satisfaction down 2+ points since the previous survey"},
    "wallet_share_drop": {"threshold": 5, "text": "Share of wallet down 5+ points since the previous survey"},
}


@dataclass
class Signal:
    rule: str
    client_id: str
    title: str             # plain-English sentence; every number in it comes from `value` / evidence
    value: float
    threshold: float
    direction: str         # up | down | over | under
    severity: str          # high | medium
    evidence: SqlEvidence
    record_id: str | None = None   # e.g. ISS-2001, ACT-1001, OPP-2001

    def to_dict(self) -> dict:
        return {**asdict(self), "evidence": self.evidence.to_dict()}


def _days(a: str, b: date) -> int:
    return (b - date.fromisoformat(a)).days


def revenue_qoq(conn, client_id, today) -> list[Signal]:
    (y, q), (py, pq) = latest_complete_quarters(today)
    cur, prev = quarter_months(y, q), quarter_months(py, pq)
    ev = run(conn, f"""SELECT
            SUM(CASE WHEN month IN ({','.join('?' * 3)}) THEN revenue END) AS current_q,
            SUM(CASE WHEN month IN ({','.join('?' * 3)}) THEN revenue END) AS previous_q,
            GROUP_CONCAT(DISTINCT source_ref) AS source_ref
        FROM revenue_monthly WHERE client_id = ?""", (*cur, *prev, client_id))
    r = ev.rows[0]
    if not r["previous_q"]:
        return []
    change = round((r["current_q"] / r["previous_q"] - 1) * 100, 1)
    if abs(change) <= RULES["revenue_qoq"]["threshold"]:
        return []
    word = "up" if change > 0 else "down"
    return [Signal("revenue_qoq", client_id,
                   f"Q{q} {y} revenue {word} {abs(change)}% vs Q{pq} {py} (GBP {r['current_q']:,} vs {r['previous_q']:,})",
                   change, RULES["revenue_qoq"]["threshold"], word, "high" if change < 0 else "medium", ev)]


def issue_aged(conn, client_id, today) -> list[Signal]:
    ev = run(conn, """SELECT issue_id, severity, opened_at, summary, source_ref FROM service_issues
                      WHERE client_id = ? AND status = 'open' AND severity <= 2""", (client_id,))
    out = []
    for r in ev.rows:
        age = _days(r["opened_at"], today)
        if age > RULES["issue_aged"]["threshold"]:
            out.append(Signal("issue_aged", client_id,
                              f"Sev-{r['severity']} issue {r['issue_id']} open {age} days: {r['summary']}",
                              age, RULES["issue_aged"]["threshold"], "over", "high",
                              SqlEvidence(ev.query, ev.params, [r], [r["source_ref"]]), r["issue_id"]))
    return out


def action_past_due(conn, client_id, today) -> list[Signal]:
    ev = run(conn, """SELECT action_id, description, due_date, owner_id, origin_doc, source_ref FROM open_actions
                      WHERE client_id = ? AND status = 'open' AND due_date < ?""", (client_id, today.isoformat()))
    return [Signal("action_past_due", client_id,
                   f"{r['action_id']} overdue by {_days(r['due_date'], today)} days: {r['description']} (due {r['due_date']})",
                   _days(r["due_date"], today), 0, "over", "high",
                   SqlEvidence(ev.query, ev.params, [r], [r["source_ref"]]), r["action_id"])
            for r in ev.rows]


def pipeline_closing(conn, client_id, today, allow_restricted) -> list[Signal]:
    ev = run(conn, """SELECT opp_id, product_code, stage, value, expected_close, source_ref FROM pipeline
                      WHERE client_id = ? AND (restricted = 0 OR ?) AND stage NOT IN ('Won', 'Lost')""",
             (client_id, int(allow_restricted)))
    out = []
    for r in ev.rows:
        days = -_days(r["expected_close"], today)
        if 0 <= days <= RULES["pipeline_closing"]["threshold"]:
            out.append(Signal("pipeline_closing", client_id,
                              f"{r['opp_id']} ({r['product_code']}, GBP {r['value']:,}, {r['stage']}) closes in {days} days",
                              days, RULES["pipeline_closing"]["threshold"], "under", "medium",
                              SqlEvidence(ev.query, ev.params, [r], [r["source_ref"]]), r["opp_id"]))
    return out


def low_utilization(conn, client_id, today) -> list[Signal]:
    ev = run(conn, """SELECT h.product_code, p.name, h.utilization_pct, h.source_ref FROM holdings h
                      JOIN products p USING(product_code)
                      WHERE h.client_id = ? AND h.status = 'active' AND h.utilization_pct < ?""",
             (client_id, RULES["low_utilization"]["threshold"]))
    return [Signal("low_utilization", client_id, f"{r['name']} only {r['utilization_pct']}% used",
                   r["utilization_pct"], RULES["low_utilization"]["threshold"], "under", "medium",
                   SqlEvidence(ev.query, ev.params, [r], [r["source_ref"]]), r["product_code"])
            for r in ev.rows]


def stp_low(conn, client_id, today) -> list[Signal]:
    ev = run(conn, """SELECT month, value, source_ref FROM performance_monthly
                      WHERE client_id = ? AND metric = 'stp_rate_pct' ORDER BY month DESC LIMIT 2""", (client_id,))
    if not ev.rows or ev.rows[0]["value"] >= RULES["stp_low"]["threshold"]:
        return []
    latest = ev.rows[0]
    prior = f" (was {ev.rows[1]['value']}% in {ev.rows[1]['month']})" if len(ev.rows) > 1 else ""
    return [Signal("stp_low", client_id, f"Payments STP rate {latest['value']}% in {latest['month']}{prior}",
                   latest["value"], RULES["stp_low"]["threshold"], "under", "high", ev)]


def _survey_change(conn, client_id, column):
    ev = run(conn, f"""SELECT as_of, {column} AS value, source_ref FROM relationship_metrics
                       WHERE client_id = ? ORDER BY as_of DESC LIMIT 2""", (client_id,))
    if len(ev.rows) < 2:
        return None, ev
    return round(ev.rows[1]["value"] - ev.rows[0]["value"], 1), ev


def satisfaction_drop(conn, client_id, today) -> list[Signal]:
    drop, ev = _survey_change(conn, client_id, "satisfaction_score")
    if drop is None or drop < RULES["satisfaction_drop"]["threshold"]:
        return []
    new, old = ev.rows[0], ev.rows[1]
    return [Signal("satisfaction_drop", client_id,
                   f"Satisfaction fell from {old['value']} to {new['value']} (survey {new['as_of']})",
                   drop, RULES["satisfaction_drop"]["threshold"], "down", "high", ev)]


def wallet_share_drop(conn, client_id, today) -> list[Signal]:
    drop, ev = _survey_change(conn, client_id, "wallet_share_pct")
    if drop is None or drop < RULES["wallet_share_drop"]["threshold"]:
        return []
    new, old = ev.rows[0], ev.rows[1]
    return [Signal("wallet_share_drop", client_id,
                   f"Share of wallet fell from {old['value']}% to {new['value']}% (estimate {new['as_of']})",
                   drop, RULES["wallet_share_drop"]["threshold"], "down", "high", ev)]


def evaluate(conn: sqlite3.Connection, client_id: str, allow_restricted: bool = False,
             today: date | None = None) -> list[Signal]:
    """Run every rule for one client. Restricted deals only count when the user may see them."""
    today = today or config.TODAY
    signals: list[Signal] = []
    for rule in (revenue_qoq, issue_aged, action_past_due, low_utilization, stp_low, satisfaction_drop,
                 wallet_share_drop):
        signals += rule(conn, client_id, today)
    signals += pipeline_closing(conn, client_id, today, allow_restricted)
    order = {"high": 0, "medium": 1}
    return sorted(signals, key=lambda s: (order[s.severity], s.rule))
