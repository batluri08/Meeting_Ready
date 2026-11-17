"""Email agent: what did the client ask, say or commit to, and what did we promise?

1. Gather the client's email messages (single emails and thread messages) from the last 120 days,
   permission-filtered. Each message chunk becomes Evidence.
2. Extract items into a fixed schema: kind (ask | commitment | concern), who said it, a short summary,
   a due date, and the evidence id it came from.
   - Haiku: the messages are wrapped as <untrusted_document>; no tools, JSON schema only.
   - Offline: sentence rules (request / promise / complaint cues).
3. Injection defence: messages flagged at ingestion are logged; any extracted item that looks like an
   instruction (e.g. "list revenue of every client") is dropped and logged as blocked. Items citing
   evidence that was not provided are dropped.
"""
import re
import sqlite3
from datetime import timedelta

from app import config
from app.agents.evidence import EvidenceStore, doc_source
from app.gateway.gateway import Gateway
from app.security.injection import find_injection
from app.security.permissions import UserContext

WINDOW_DAYS = 120
PROMPT_VERSION = "email-extract-v1"

ASK = re.compile(r"\b(please|can you|could you|can we|would like|i want|i still want|i also want|we need|"
                 r"let me know|confirm|do you have a date)\b", re.IGNORECASE)
COMMIT = re.compile(r"\b(we will|we'll|you will have|i will|we have agreed|will send|remains on track)\b", re.IGNORECASE)
CONCERN = re.compile(r"\b(not acceptable|paid late|other bank|still not had|have not received|still have not|"
                     r"rejected|charged overdraft|go with)\b", re.IGNORECASE)
DUE = re.compile(r"\bby (\d{1,2} (?:January|February|March|April|May|June|July|August|September|October|November|December)"
                 r"|the end of \w+|end of \w+)", re.IGNORECASE)
SENTENCE = re.compile(r"(?<=[.!?])\s+")

SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": ["ask", "commitment", "concern"]},
                    "side": {"type": "string", "enum": ["client", "bank"]},
                    "summary": {"type": "string"},
                    "due": {"type": "string"},
                    "evidence_id": {"type": "string"},
                },
                "required": ["kind", "side", "summary", "due", "evidence_id"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}

def schema_with_ids(ids: list[str]) -> dict:
    """The output schema, with evidence_id restricted to the ids actually provided, so the model cannot
    cite anything else (structured outputs enforce the enum)."""
    import copy
    s = copy.deepcopy(SCHEMA)
    s["properties"]["items"]["items"]["properties"]["evidence_id"] = {"type": "string", "enum": ids}
    return s


SYSTEM = (
    "You extract structured facts from client emails for a bank's relationship team. For each message, list "
    "every request the client made (ask), every promise the bank made (commitment), and every complaint, "
    "escalation or competitive threat (concern). Use one short sentence per item, copy dates exactly as "
    "written, put the due date in 'due' (empty string if none), and cite the evidence id the item came from. "
    "Only use the messages given. Do not invent items."
)


def _gather(conn: sqlite3.Connection, client_id: str, user: UserContext) -> list[dict]:
    since = (config.TODAY - timedelta(days=WINDOW_DAYS)).isoformat()
    rows = conn.execute(
        """SELECT c.chunk_id, c.doc_id, c.page, c.section, c.text, d.date, d.sender, d.title, d.type AS doc_type,
                  d.injection_flag
           FROM chunks c JOIN documents d USING(doc_id)
           WHERE d.client_id = ? AND d.type = 'email' AND d.duplicate_of IS NULL AND d.date >= ?
             AND (c.restricted = 0 OR ?)
           ORDER BY d.date, c.page""", (client_id, since, int(user.allow_restricted))).fetchall()
    out = []
    for r in rows:
        r = dict(r)
        if r["section"]:                                   # thread message: 'Message 4 · Daniel Okafor · 2026-11-11'
            _, who, when = [p.strip() for p in r["section"].split("·")]
            r["who"], r["date"] = who, when
        else:
            r["who"] = (r["sender"] or "").split("<")[0].strip()
        out.append(r)
    return out


def _offline_extract(messages: list[dict], staff: set[str], audit) -> list[dict]:
    items = []
    for m in messages:
        side = "bank" if m["who"] in staff else "client"
        for sent in SENTENCE.split(m["text"].replace("\n", " ")):
            sent = sent.strip()
            if not sent:
                continue
            if find_injection(sent):
                audit.log("injection_blocked", doc_id=m["doc_id"], where="email_extract", text=sent[:120])
                continue
            due = (DUE.search(sent).group(1) if DUE.search(sent) else "")
            if side == "bank" and COMMIT.search(sent):
                kind = "commitment"
            elif side == "client" and ASK.search(sent):      # a request wins: "I want to discuss compensation..."
                kind = "ask"
            elif side == "client" and CONCERN.search(sent):
                kind = "concern"
            else:
                continue
            items.append({"kind": kind, "side": side, "summary": sent, "due": due, "evidence_id": m["evidence_id"]})
    return items


def run_email_agent(conn, client_id: str, user: UserContext, store: EvidenceStore, gateway: Gateway) -> dict:
    messages = _gather(conn, client_id, user)
    staff = {r[0] for r in conn.execute("SELECT name FROM users")}
    for m in messages:
        ev = store.add("doc", f"{m['doc_id']} {m['section'] or m['title']}",
                       f"{m['who']} ({m['date']}): {m['text']}", doc_source(m), restricted=False)
        m["evidence_id"] = ev.id
        if m["injection_flag"] and find_injection(m["text"]):
            gateway.audit.log("injection_attempt", doc_id=m["doc_id"], chunk_id=m["chunk_id"],
                              phrases=find_injection(m["text"]))

    ids = [m["evidence_id"] for m in messages]
    if not messages:
        return {"evidence": [], "items": []}

    result = gateway.call(
        "extract", PROMPT_VERSION, SYSTEM,
        f"Messages:\n{store.for_prompt(ids)}\n\nStaff of the bank (side = bank): {', '.join(sorted(staff))}\n"
        f"Cite the bracketed evidence id of the message (for example {ids[0]}), not the document id.",
        schema_with_ids(ids), offline=lambda: {"items": _offline_extract(messages, staff, gateway.audit)},
    )

    valid, allowed = [], set(ids)
    for it in result.get("items", []):
        if it.get("evidence_id") not in allowed:
            gateway.audit.log("verifier_drop", where="email_extract", reason="unknown evidence id", item=it)
            continue
        if find_injection(it.get("summary", "")) or re.search(r"\b(every|all) clients?\b", it.get("summary", ""), re.I):
            gateway.audit.log("injection_blocked", where="email_extract_output", item=it)
            continue
        valid.append(it)
    return {"evidence": ids, "items": valid}
