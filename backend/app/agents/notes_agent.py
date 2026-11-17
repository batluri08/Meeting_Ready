"""Notes agent: meeting notes, transcripts, prior briefings, research. Context + stale/conflict checks.

- Hybrid search for a few standing topics, client-scoped and permission-filtered.
- Neighbour expansion: for each hit, the chunk just before and after it in the same document is added,
  so the writer sees the surrounding conversation (instead of relying on heavy chunk overlap).
- Claims (claims.py) find stale and conflicting statements across ALL the client's documents.
"""
import sqlite3

from app.agents.claims import compare, current_cfo, extract_claims
from app.agents.evidence import EvidenceStore, doc_source, sql_source
from app.metrics.evidence import SqlEvidence
from app.security.permissions import UserContext
from app.stores.doc_index import DocIndex

TOPICS = [
    "client priorities, plans and what matters to them",
    "risks, complaints, competition from other banks",
    "products, pricing and fees the client asked about",
]
DOC_TYPES = {"note", "transcript", "briefing"}


def _chunk(conn, chunk_id):
    r = conn.execute("""SELECT c.chunk_id, c.doc_id, c.page, c.section, c.text, c.restricted, d.date, d.title,
                               d.type AS doc_type FROM chunks c JOIN documents d USING(doc_id) WHERE c.chunk_id = ?""",
                     (chunk_id,)).fetchone()
    return dict(r) if r else None


def _neighbours(conn, doc_id, page, allow_restricted):
    rows = conn.execute("""SELECT chunk_id FROM chunks WHERE doc_id = ? AND page IN (?, ?) AND (restricted = 0 OR ?)""",
                        (doc_id, page - 1, page + 1, int(allow_restricted))).fetchall()
    return [r[0] for r in rows]


def run_notes_agent(conn: sqlite3.Connection, idx: DocIndex, client_id: str, user: UserContext,
                    store: EvidenceStore) -> dict:
    seen, ids = set(), []

    def add(chunk_id, via):
        if chunk_id in seen:
            return
        row = _chunk(conn, chunk_id)
        if row is None or (row["restricted"] and not user.allow_restricted):
            return
        seen.add(chunk_id)
        label = row["section"] or f"page {row['page']}"
        ids.append(store.add("doc", f"{row['doc_id']} {label}", row["text"], {**doc_source(row), "found_by": via},
                             restricted=bool(row["restricted"])).id)

    for topic in TOPICS:
        for hit in idx.search(topic, client_id=client_id, allow_restricted=user.allow_restricted,
                              doc_types=DOC_TYPES, k=3):
            add(hit.chunk_id, f"search: {topic}")
            for nb in _neighbours(conn, hit.doc_id, hit.page, user.allow_restricted):
                add(nb, f"neighbour of {hit.chunk_id}")

    findings = compare(extract_claims(conn, client_id, user), current_cfo(conn, client_id))
    finding_ids = []
    for f in findings:
        refs = []
        for c in f["claims"]:
            row = _chunk(conn, c["chunk_id"])
            refs.append(store.add("claim", f"{c['doc_id']} ({c['date']})", f"{c['doc_id']} ({c['date']}): \"{c['quote']}\"",
                                  doc_source(row)).id)
        if f.get("record"):
            rec = f["record"]
            refs.append(store.add("claim", "Contact record",
                                  f"Contact record: {rec['name']}, {rec['title']} (updated {rec['updated_at']})",
                                  sql_source(SqlEvidence(
                                      "SELECT contact_id, name, title, updated_at, source_ref FROM contacts WHERE contact_id = ?",
                                      (rec["contact_id"],), [rec], [rec["source_ref"]]))).id)
        finding_ids.append({**{k: v for k, v in f.items() if k != "claims"}, "evidence": refs})
    return {"evidence": ids, "findings": finding_ids}
