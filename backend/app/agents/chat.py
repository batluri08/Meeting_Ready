"""Chat follow-ups on a briefing ("why is revenue flagged?", "revenue by month?").

Conversation management: the session keeps the resolved client, the briefing's evidence and earlier
questions, so follow-ups reuse evidence instead of re-querying everything.

For each question:
  1. Route (Claude, or keyword rules offline): does it need new numbers (SQL), documents (search), or only
     the evidence already gathered?
  2. If SQL: Claude writes a query; the SQL GUARD refuses anything unsafe and rewrites it to this client
     and this user's access before it runs on a read-only connection. Rows become evidence.
  3. If documents: hybrid search, client-scoped and permission-filtered.
  4. Claude writes the answer citing evidence ids (only ids it was given); the VERIFIER checks every
     statement, exactly as for the briefing. Names are masked for the model and restored for the user.
"""
import copy
import re

from rank_bm25 import BM25Okapi

from app import config
from app.agents.dates import describe, evidence_text, on_record, parse_dates
from app.agents.evidence import Evidence, EvidenceStore, doc_source, sql_source
from app.agents.synthesizer import SCHEMA as STATEMENTS_SCHEMA
from app.agents.verifier import verify
from app.gateway.gateway import Gateway
from app.metrics.evidence import SqlEvidence
from app.security.sql_guard import SqlGuard
from app.stores.doc_index import DocIndex, tokenize

ROUTE_VERSION = "chat-route-v1"
ANSWER_VERSION = "chat-answer-v1"

ROUTE_SCHEMA = {
    "type": "object",
    "properties": {
        "needs_sql": {"type": "boolean"},
        "sql": {"type": "string"},
        "needs_documents": {"type": "boolean"},
        "search_query": {"type": "string"},
    },
    "required": ["needs_sql", "sql", "needs_documents", "search_query"],
    "additionalProperties": False,
}
ROUTE_SYSTEM = (
    "You route a relationship manager's follow-up question about ONE client. Decide whether answering needs new "
    "numbers from the database (write ONE read-only SQLite SELECT over the tables listed; do not filter by client, "
    "that is applied automatically), and/or a document search (give a short search query). If the evidence already "
    "gathered is enough, set both to false. Never write anything except a single SELECT."
)
ANSWER_SYSTEM = (
    "Answer a relationship manager's follow-up question about one client in 1 to 4 short statements. The first "
    "statement answers the question directly; add further statements only if they bear directly on the question "
    "(no loosely related background). Use ONLY the evidence given, cite evidence ids, and copy numbers exactly. "
    "If the evidence does not answer the question, say so plainly. Names appear as tokens like [PERSON_1]; keep them."
)

# offline routing: question words -> a fixed, safe query
OFFLINE_SQL = [
    (r"\b(month|monthly|trend|over time)\b.*\brevenue\b|\brevenue\b.*\b(month|monthly|trend|over time)\b",
     "SELECT month, SUM(revenue) AS revenue FROM revenue_monthly GROUP BY month ORDER BY month"),
    (r"\b(stp|straight.through|payments processed|balance)\b",
     "SELECT month, metric, value FROM performance_monthly ORDER BY month, metric"),
    (r"\b(pipeline|deals?|opportunit)", "SELECT opp_id, product_code, stage, value, expected_close FROM pipeline"),
    (r"\b(contacts?|who (is|are)|cfo|treasurer)\b", "SELECT name, title, role, updated_at FROM contacts"),
    (r"\b(issues?|tickets?|complaints?)\b", "SELECT issue_id, severity, status, opened_at, closed_at, summary FROM service_issues"),
    (r"\b(satisfaction|wallet|survey)\b", "SELECT as_of, wallet_share_pct, satisfaction_score FROM relationship_metrics ORDER BY as_of"),
]


def _schema_text(guard: SqlGuard) -> str:
    return "\n".join(f"- {t}({', '.join(cols)})" for t, cols in sorted(guard.columns.items()))


def _relevant(question: str, store: EvidenceStore, k: int = 6) -> list[str]:
    """Evidence the briefing already gathered that fits the question, ranked with BM25 so distinctive words
    ('revenue', 'satisfaction') count for more than common ones ('client', 'bank')."""
    items = [ev for ev in store.items.values() if ev.kind not in ("system",)]
    q = tokenize(question)
    if not items or not q:
        return []
    scores = BM25Okapi([tokenize(f"{ev.title} {ev.text}") or ["_"] for ev in items]).get_scores(q)
    ranked = sorted(zip(items, scores), key=lambda p: -p[1])
    return [ev.id for ev, s in ranked[:k] if s > 0]


def _rows_text(rows: list[dict], limit: int = 40) -> str:
    shown = rows[:limit]
    body = "; ".join(", ".join(f"{k}={v}" for k, v in r.items() if k != "source_ref") for r in shown)
    more = f" (+{len(rows) - limit} more rows)" if len(rows) > limit else ""
    return f"{len(rows)} row(s): {body}{more}"


def answer(question: str, *, client_id: str, user, store: EvidenceStore, history: list[dict], guard: SqlGuard,
           idx: DocIndex, gateway: Gateway) -> dict:
    audit = gateway.audit
    audit.log("chat_question", question=gateway.masker.mask(question))
    history_txt = "\n".join(f"Q: {h['question']}\nA: {' '.join(s['text'] for s in h['answer'])}" for h in history[-3:])

    # ---- 1. route
    def offline_route():
        sql = next((q for pat, q in OFFLINE_SQL if re.search(pat, question, re.I)), "")
        return {"needs_sql": bool(sql), "sql": sql, "needs_documents": True, "search_query": question}

    route = gateway.call("sql", ROUTE_VERSION, ROUTE_SYSTEM,
                         f"Tables you may query:\n{_schema_text(guard)}\n\nEarlier in this conversation:\n{history_txt or '(none)'}"
                         f"\n\nQuestion: {question}", ROUTE_SCHEMA, offline=offline_route)

    sql_ids, doc_ids, sql_result = [], [], None
    # ---- 2. SQL through the guard
    if route.get("needs_sql") and route.get("sql", "").strip():
        sql_result = guard.run(route["sql"], client_id, user.allow_restricted)
        audit.log("text_to_sql", original=sql_result.original_sql, rewritten=sql_result.rewritten_sql,
                  ok=sql_result.ok, reason=sql_result.reason, rows=sql_result.row_count)
        if sql_result.ok and sql_result.rows:
            ev = store.add("sql", "Query result", _rows_text(sql_result.rows),
                           sql_source(SqlEvidence(sql_result.rewritten_sql, (), sql_result.rows,
                                                  sorted({r.get("source_ref") for r in sql_result.rows if r.get("source_ref")}))))
            sql_ids.append(ev.id)

    # ---- 2b. dates in the question: code lists everything on record in that period (search cannot match
    # "13th of November" to "2026-11-13", and a model-written query may miss a table)
    periods = parse_dates(question, config.TODAY)
    date_ids, date_note = [], ""
    if periods:
        for start, end in periods[:3]:          # the guard's connection is read-only; the query is fixed code
            rec = on_record(guard.conn, client_id, start, end, user.allow_restricted)
            date_ids.append(store.add("sql", f"Records dated {describe(start, end)}", evidence_text(rec, start, end),
                                      sql_source(rec)).id)
        audit.log("chat_dates", periods=[[s.isoformat(), e.isoformat()] for s, e in periods[:3]])
        date_note = ("\n\nThe question is about this period: " + "; ".join(f"{describe(s, e)} ({s.isoformat()}"
                     + ("" if s == e else f" to {e.isoformat()}") + ")" for s, e in periods[:3])
                     + ". Answer only with what is dated in that period. If nothing is on record for it, say so plainly "
                     "in the first statement; you may then mention the nearest dated items, saying clearly that they are "
                     "on other dates.")

    # ---- 3. evidence the briefing already gathered (reused, not re-queried), then documents
    # (dates are added to the search words in the form records use: '2026-11-13')
    reused = _relevant(question + " " + " ".join(s.isoformat() for s, e in periods if s == e), store)
    if route.get("needs_documents") and route.get("search_query"):
        for h in idx.search(route["search_query"], client_id=client_id, allow_restricted=user.allow_restricted, k=3,
                            rerank=config.CHAT_RERANK):          # one question: put the best passage first
            doc_ids.append(store.add("doc", f"{h.doc_id} p{h.page}", h.text, doc_source(
                {"chunk_id": h.chunk_id, "doc_id": h.doc_id, "page": h.page, "date": h.date, "doc_type": h.doc_type,
                 "text": h.text})).id)

    # ---- 4. answer + verify: new numbers first, then what the briefing already knew, then documents
    ids = list(dict.fromkeys(date_ids + sql_ids + reused + doc_ids))
    if not ids:
        return {"answer": [{"text": "I could not find anything in this client's records that answers that.",
                            "evidence_ids": [], "empty": True}], "sql": sql_result.to_dict() if sql_result else None,
                "evidence": {}}

    def offline_answer():
        return {"statements": [{"text": store.get(i).text if store.get(i).kind != "doc"
                                else f"From {store.get(i).source['doc_id']}: {store.get(i).text[:240]}",
                                "evidence_ids": [i]} for i in ids[:4]]}

    schema = copy.deepcopy(STATEMENTS_SCHEMA)
    schema["properties"]["statements"]["items"]["properties"]["evidence_ids"]["items"] = {"type": "string", "enum": ids}
    result = gateway.call("chat", ANSWER_VERSION, ANSWER_SYSTEM,
                          f"Question: {question}\n\nEarlier in this conversation:\n{history_txt or '(none)'}\n\n"
                          f"Evidence:\n{store.for_prompt(ids)}{date_note}", schema, offline=offline_answer,
                          restricted=any(store.get(i).restricted for i in ids))
    statements = result.get("statements", [])
    kept, dropped = verify("chat", statements, set(ids), store, audit)
    if date_ids and statements and dropped and statements[0] not in kept:
        # the direct answer to a date question was removed: open with the code-built record of that date
        # instead, so the reply never starts mid-thought ("This survey…")
        kept = [{"text": store.get(i).text, "evidence_ids": [i]} for i in date_ids] + kept
    kept = [{**s, "text": gateway.masker.unmask(s["text"])} for s in kept]
    if not kept:   # everything was unsupported (e.g. a refusal with no citation): never leave the user with a blank answer
        kept = [{"text": "I can't answer that from this client's records. I can only answer questions about this client, "
                         "using its data and documents.", "evidence_ids": [], "empty": True}]
    return {"answer": kept, "dropped": dropped, "sql": sql_result.to_dict() if sql_result else None,
            "evidence": {i: store.get(i).to_dict() for i in ids}}


def evidence_from_briefing(briefing: dict) -> EvidenceStore:
    """Rebuild the session's evidence store from a finished briefing (ids unchanged)."""
    store = EvidenceStore()
    for eid, e in sorted(briefing["evidence"].items(), key=lambda kv: int(kv[0][1:])):
        store.items[eid] = Evidence(**e)
    return store
