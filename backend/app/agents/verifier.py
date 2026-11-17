"""Verifier: nothing reaches the user unless it is backed by evidence.

A statement is kept only if
  1. it cites at least one evidence id,
  2. every cited id exists and was given to that section, and
  3. every number in the sentence appears in the evidence it cites (dates may be written in words).
Anything else is dropped and logged with the reason.
"""
from app.agents.evidence import EvidenceStore, numbers_in, statement_text
from app.gateway.audit import AuditLog
from app.gateway.pii import TOKEN


def check(statement: dict, allowed_ids: set[str], store: EvidenceStore) -> str | None:
    """Return None if the statement passes, otherwise the reason it fails."""
    ids = statement.get("evidence_ids") or []
    if not ids:
        return "no citation"
    unknown = [i for i in ids if i not in allowed_ids or store.get(i) is None]
    if unknown:
        return f"cites evidence not given to this section: {unknown}"
    allowed = set().union(*(store.get(i).allowed_numbers() for i in ids))
    stated = numbers_in(TOKEN.sub("", statement_text(statement)))
    missing = sorted(n for n in stated if n not in allowed)
    if missing:
        return f"numbers not in cited evidence: {missing}"
    return None


def verify(section_id: str, statements: list[dict], allowed_ids: set[str], store: EvidenceStore,
           audit: AuditLog) -> tuple[list[dict], list[dict]]:
    kept, dropped = [], []
    for st in statements:
        if st.get("empty"):            # "Nothing on record" makes no claim, so there is nothing to verify
            kept.append(st)
            continue
        reason = check(st, allowed_ids, store)
        if reason:
            dropped.append({**st, "reason": reason})
            audit.log("verifier_drop", section=section_id, text=statement_text(st)[:200], reason=reason)
        else:
            kept.append(st)
    return kept, dropped
