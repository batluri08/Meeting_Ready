"""Structured data agent: profile, material signals, what changed, deals and open actions.

Fixed, reviewed SQL queries only (Text-to-SQL is used for chat follow-ups, behind the SQL guard).
Every result becomes Evidence carrying its query and rows.
"""
import sqlite3

from app.agents.evidence import EvidenceStore, sql_source
from app.metrics.changes import changes_since_last_interaction
from app.metrics.evidence import SqlEvidence, run
from app.metrics.periods import last_interaction, latest_complete_quarters, quarter_months  # noqa: F401
from app.metrics.rules import RULES, evaluate
from app.security.permissions import UserContext


def profile(conn: sqlite3.Connection, client_id: str, user: UserContext, store: EvidenceStore) -> dict:
    ids = []
    ev = run(conn, """SELECT client_id, legal_name, industry, region, segment, tier, client_since FROM clients
                      WHERE client_id = ?""", (client_id,))
    c = ev.rows[0]
    ids.append(store.add("profile", "Client record",
                         f"{c['legal_name']}: {c['industry']}, {c['region']}, {c['segment']} segment, {c['tier']} tier, "
                         f"client since {c['client_since']}", sql_source(ev)).id)

    ev = run(conn, """SELECT u.name, u.clearance, cv.role, cv.source_ref FROM coverage cv JOIN users u USING(user_id)
                      WHERE cv.client_id = ? ORDER BY cv.role DESC""", (client_id,))
    ids.append(store.add("profile", "Coverage team",
                         "Coverage: " + "; ".join(f"{r['name']} ({r['role']})" for r in ev.rows), sql_source(ev)).id)

    ev = run(conn, """SELECT name, title, role, updated_at, source_ref FROM contacts
                      WHERE client_id = ? AND duplicate_of IS NULL AND role != 'Inactive' ORDER BY role, name""",
             (client_id,))
    ids.append(store.add("profile", "Key contacts",
                         "Contacts: " + "; ".join(f"{r['name']}, {r['title']} ({r['role']})" for r in ev.rows),
                         sql_source(ev)).id)

    ev = run(conn, """SELECT p.name, h.utilization_pct, h.opened_on, h.source_ref FROM holdings h
                      JOIN products p USING(product_code) WHERE h.client_id = ? AND h.status = 'active'
                      ORDER BY p.name""", (client_id,))
    ids.append(store.add("profile", "Products held",
                         f"{len(ev.rows)} products held: " + "; ".join(f"{r['name']} ({r['utilization_pct']}% used)" for r in ev.rows),
                         sql_source(ev)).id)

    ev = run(conn, """SELECT as_of, wallet_share_pct, satisfaction_score, primary_bank, source_ref FROM relationship_metrics
                      WHERE client_id = ? ORDER BY as_of DESC LIMIT 1""", (client_id,))
    if ev.rows:
        r = ev.rows[0]
        ids.append(store.add("profile", "Relationship metrics",
                             f"As of {r['as_of']}: share of wallet {r['wallet_share_pct']}%, satisfaction {r['satisfaction_score']}/10, "
                             f"{'primary bank' if r['primary_bank'] else 'not primary bank'}", sql_source(ev)).id)

    (y, q), _ = latest_complete_quarters()
    months = quarter_months(y, q)
    ev = run(conn, f"""SELECT SUM(revenue) AS revenue, GROUP_CONCAT(DISTINCT source_ref) AS source_ref
                       FROM revenue_monthly WHERE client_id = ? AND month IN ({','.join('?' * 3)})""", (client_id, *months))
    if ev.rows and ev.rows[0]["revenue"]:
        ids.append(store.add("profile", f"Revenue Q{q} {y}", f"Revenue in Q{q} {y}: GBP {ev.rows[0]['revenue']:,}",
                             sql_source(ev)).id)
    return {"evidence": ids, "client_name": c["legal_name"]}


def signals(conn, client_id, user: UserContext, store: EvidenceStore) -> dict:
    ids, raw = [], []
    for s in evaluate(conn, client_id, allow_restricted=user.allow_restricted):
        # the rule's verdict is part of the fact: code decided it is material, so the evidence says so
        rule = RULES.get(s.rule, {}).get("text", s.rule)
        ev = store.add("signal", s.rule, f"Material, flagged by the rule '{rule}': {s.title}", {**sql_source(s.evidence), "rule": s.rule, "severity": s.severity,
                                                   "threshold": s.threshold, "value": s.value, "record_id": s.record_id})
        ids.append(ev.id)
        raw.append({"evidence_id": ev.id, "rule": s.rule, "severity": s.severity, "record_id": s.record_id})
    return {"evidence": ids, "signals": raw}


def changes(conn, client_id, user: UserContext, store: EvidenceStore) -> dict:
    result = changes_since_last_interaction(conn, client_id, allow_restricted=user.allow_restricted)
    last = result["last_interaction"]
    since = (f"since the last interaction ({last['type']} on {last['date']})" if not result["fallback"]
             else f"in the last 90 days (no past meeting or call on record; since {result['since']})")
    ids = [store.add("change", c.kind, f"New {since}: {c.date}: {c.summary}",
                     {**sql_source(c.evidence), "date": c.date, "ref": c.ref}).id
           for c in result["changes"]]
    return {"evidence": ids, "since": result["since"], "fallback": result["fallback"],
            "last_interaction": result["last_interaction"]}


def deals_and_actions(conn, client_id, user: UserContext, store: EvidenceStore) -> dict:
    deals = run(conn, """SELECT opp_id, product_code, stage, value, expected_close, restricted, source_ref FROM pipeline
                         WHERE client_id = ? AND (restricted = 0 OR ?) ORDER BY expected_close""",
                (client_id, int(user.allow_restricted)))
    deal_ids = [store.add("deal", r["opp_id"],
                          f"{r['opp_id']}: {r['product_code']} deal, GBP {r['value']:,}, stage {r['stage']}, expected close {r['expected_close']}",
                          sql_source(SqlEvidence(deals.query, deals.params, [r], [r["source_ref"]])),
                          restricted=bool(r["restricted"])).id for r in deals.rows]
    acts = run(conn, """SELECT a.action_id, a.description, a.due_date, a.status, a.origin_doc, u.name AS owner, a.source_ref
                        FROM open_actions a LEFT JOIN users u ON u.user_id = a.owner_id
                        WHERE a.client_id = ? AND a.status = 'open' ORDER BY a.due_date""", (client_id,))
    action_rows = []
    for r in acts.rows:
        ev = store.add("action", r["action_id"],
                       f"{r['action_id']} (open, owner {r['owner']}, due {r['due_date']}): {r['description']}",
                       sql_source(SqlEvidence(acts.query, acts.params, [r], [r["source_ref"]])))
        action_rows.append({**r, "evidence_id": ev.id})
    return {"deal_evidence": deal_ids, "actions": action_rows}
