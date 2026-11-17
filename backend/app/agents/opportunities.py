"""Opportunities: which products should the team discuss, and what evidence supports each one?

Code, not AI. A product is an opportunity when BOTH:
  1. there is a business reason in the data: not held today, held but under-used (< 50%), or an open deal; and
  2. the client's own words support it: an email, note or transcript passage that mentions the need.
Relevant research or product updates are attached as supporting material.
"""
import sqlite3

from app.agents.evidence import EvidenceStore, doc_source, sql_source
from app.metrics.evidence import SqlEvidence, run
from app.security.permissions import UserContext
from app.stores.doc_index import DocIndex

UNDER_USED = 50
CATALOGUE = {
    # product: (what to propose, search query, words that must appear in the client's text)
    "FX_HEDGE": ("FX hedging programme for foreign-currency receivables", "currency exposure and FX hedging",
                 ["hedg", "currency", "euro"]),
    "TRADE_FIN": ("larger trade finance limits", "trade finance limits for imports and letters of credit",
                  ["trade finance", "letters of credit", "letter of credit"]),
    "SUPPLY_FIN": ("supply chain finance to pay suppliers faster", "paying suppliers and hauliers faster",
                   ["smaller hauliers", "suppliers faster", "supply chain finance"]),
    "CARD": ("corporate cards for all drivers, with fuel-only controls", "fuel cards for drivers",
             ["cards to all drivers", "drivers", "fuel"]),
    "CASH_MGMT": ("single-bank cash management with cash pooling", "consolidate banks and cash pooling",
                  ["cash pooling", "one bank", "consolidat"]),
}


def find_opportunities(conn: sqlite3.Connection, idx: DocIndex, client_id: str, user: UserContext,
                       store: EvidenceStore) -> dict:
    holdings = run(conn, """SELECT h.product_code, p.name, h.utilization_pct, h.source_ref FROM holdings h
                            JOIN products p USING(product_code) WHERE h.client_id = ? AND h.status = 'active'""", (client_id,))
    deals = run(conn, """SELECT opp_id, product_code, stage, value, expected_close, source_ref FROM pipeline
                         WHERE client_id = ? AND (restricted = 0 OR ?) AND stage NOT IN ('Won', 'Lost')""",
                (client_id, int(user.allow_restricted)))
    held = {r["product_code"]: r for r in holdings.rows}
    open_deal = {r["product_code"]: r for r in deals.rows}

    out = []
    for product, (proposal, query, cues) in CATALOGUE.items():
        h, d = held.get(product), open_deal.get(product)
        if h is None:
            reason = "not held today"
        elif h["utilization_pct"] < UNDER_USED:
            reason = f"held but only {h['utilization_pct']}% used"
        elif d is None:
            continue
        else:
            reason = "already held"
        if d:
            reason += f"; open deal {d['opp_id']} (GBP {d['value']:,}, {d['stage']}, close {d['expected_close']})"

        hits = [x for x in idx.search(query, client_id=client_id, allow_restricted=user.allow_restricted,
                                      doc_types={"email", "note", "transcript", "briefing"}, k=6)
                if any(c in x.text.lower() for c in cues)][:2]
        if not hits:
            continue                                   # no client-side evidence: not proposed
        research = [x for x in idx.search(query, client_id=client_id, doc_types={"research"}, include_general=True, k=3)
                    if any(c in x.text.lower() for c in cues)][:1]

        rows = [r for r in (h, d) if r]
        basis_sql = SqlEvidence(f"{holdings.query} ; {deals.query}", holdings.params + deals.params, rows,
                                sorted({r["source_ref"] for r in rows}))
        basis = store.add("opportunity", f"{product} basis",
                          f"Opportunity to discuss, identified by the opportunity rules: {product}: {reason}",
                          sql_source(basis_sql))
        support = [store.add("doc", f"{x.doc_id} p{x.page}", x.text,
                             doc_source({"chunk_id": x.chunk_id, "doc_id": x.doc_id, "page": x.page, "date": x.date,
                                         "doc_type": x.doc_type, "text": x.text})).id for x in hits + research]
        out.append({"product": product, "proposal": proposal, "reason": reason, "evidence": [basis.id, *support]})
    return {"opportunities": out, "evidence": [e for o in out for e in o["evidence"]]}
