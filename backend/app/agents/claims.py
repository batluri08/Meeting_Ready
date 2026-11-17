"""Stale and conflicting statements: extract simple claims from documents, then COMPARE THEM IN CODE.

A claim is (topic, value, document, date). Two policies decide what a disagreement means:

  fixed facts   (agreement renewal date)      -> different values = CONFLICT; show both, pick none
  changing facts (who the CFO is, stance on hedging) -> the newest wins; older different values are
                                                        STALE and are flagged, not used

The CFO claim is also checked against the contact master (the system of record).

Extraction here uses patterns, which is enough for the prototype's data and runs offline. In production
the same claims would be extracted by the model into a fixed schema; the comparison stays in code.
"""
import re
import sqlite3

from app.security.permissions import UserContext

MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
PATTERNS = {
    "agreement_renewal": (re.compile(rf"(?:agreement|contract)[^.]{{0,40}}?renews? in ({MONTHS}) (\d{{4}})", re.I),
                          lambda m: f"{m.group(1).title()} {m.group(2)}", "fixed"),
    "cfo": (re.compile(r"\bCFO is ([A-Z]\.? ?[A-Z][a-z]+|[A-Z][a-z]+ [A-Z][a-z]+)"), lambda m: m.group(1), "latest"),
    # the client's position on FX hedging: a 2025 "no" is superseded by a 2026 request for pricing
    "hedging_stance": (re.compile(r"(not looking at hedging|hedging pricing|rolling programme)", re.I),
                       lambda m: "not interested" if m.group(1).lower().startswith("not looking") else "interested",
                       "latest"),
}


def extract_claims(conn: sqlite3.Connection, client_id: str, user: UserContext) -> list[dict]:
    rows = conn.execute(
        """SELECT c.chunk_id, c.doc_id, c.text, d.date, d.type FROM chunks c JOIN documents d USING(doc_id)
           WHERE d.client_id = ? AND d.duplicate_of IS NULL AND (c.restricted = 0 OR ?)""",
        (client_id, int(user.allow_restricted))).fetchall()
    claims = []
    for r in rows:
        for topic, (rx, value_of, policy) in PATTERNS.items():
            for m in rx.finditer(r["text"]):
                claims.append({"topic": topic, "value": value_of(m), "policy": policy, "doc_id": r["doc_id"],
                               "chunk_id": r["chunk_id"], "date": r["date"], "quote": m.group(0)})
    return claims


def current_cfo(conn: sqlite3.Connection, client_id: str) -> dict | None:
    row = conn.execute(
        """SELECT contact_id, name, title, updated_at, source_ref FROM contacts
           WHERE client_id = ? AND duplicate_of IS NULL AND role != 'Inactive'
             AND (title LIKE '%Chief Financial Officer%' OR title = 'CFO')
           ORDER BY updated_at DESC LIMIT 1""", (client_id,)).fetchone()
    return dict(row) if row else None


def _same_person(a: str, b: str) -> bool:
    a, b = a.replace(".", "").lower().split(), b.replace(".", "").lower().split()
    return a[-1] == b[-1] and a[0][0] == b[0][0]


def compare(claims: list[dict], cfo_record: dict | None) -> list[dict]:
    """Return findings: {'kind': 'conflict'|'stale', 'topic', 'detail', 'claims': [...], 'record': ...}"""
    findings = []
    by_topic: dict[str, list[dict]] = {}
    for c in claims:
        by_topic.setdefault(c["topic"], []).append(c)

    for topic, cs in by_topic.items():
        policy = cs[0]["policy"]
        values = {c["value"] for c in cs}
        if policy == "fixed" and len(values) > 1:
            detail = " vs ".join(f"{v} ({', '.join(sorted({c['doc_id'] for c in cs if c['value'] == v}))})" for v in sorted(values))
            findings.append({"kind": "conflict", "topic": topic, "detail": detail, "claims": cs})
        elif policy == "latest":
            if topic == "cfo" and cfo_record:
                for c in cs:
                    if not _same_person(c["value"], cfo_record["name"]):
                        findings.append({"kind": "stale", "topic": topic, "claims": [c], "record": cfo_record,
                                         "detail": f"{c['doc_id']} ({c['date']}) says the CFO is {c['value']}; the "
                                                   f"contact record (updated {cfo_record['updated_at']}) says {cfo_record['name']}"})
                continue
            newest = max(cs, key=lambda c: c["date"])
            for c in cs:
                if c["value"] != newest["value"] and c["date"] < newest["date"]:
                    findings.append({"kind": "stale", "topic": topic, "claims": [c, newest],
                                     "detail": f"{c['doc_id']} ({c['date']}) says '{c['value']}'; newer {newest['doc_id']} "
                                               f"({newest['date']}) says '{newest['value']}'"})
    return findings
