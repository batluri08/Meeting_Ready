"""Commitments: what the client asked for, what we promised, and what is still open (code).

Combines the open-actions table with what the email agent extracted, then finds client asks that no
open action covers ("untracked asks"), e.g. Halden's request for staff compensation, which exists only
in an email. Matching is a simple shared-keyword check on purpose: it is explainable and errs towards
showing an ask rather than hiding it.
"""
import re

GENERIC = {"please", "send", "share", "want", "would", "like", "can", "could", "you", "we", "our", "the", "a", "an",
           "to", "for", "of", "on", "in", "by", "and", "is", "it", "this", "that", "be", "with", "us", "me", "i",
           "also", "still", "discuss", "talk", "about", "get", "getting", "all", "your", "they", "them", "have",
           "has", "had", "next", "before", "end", "meeting", "november", "october", "december", "let", "know"}


def _words(text: str) -> set[str]:
    return {w.rstrip("s") for w in re.findall(r"[a-z]+", text.lower()) if w not in GENERIC and len(w) > 2}


def build_commitments(actions: list[dict], items: list[dict], since: str = "", date_of=lambda eid: "") -> dict:
    """`since`: date of the last interaction. Asks made before it were presumably handled in that meeting,
    so only later asks can be 'untracked'. `date_of(evidence_id)` gives the message date."""
    asks = [i for i in items if i["kind"] == "ask"]
    promises = [i for i in items if i["kind"] == "commitment"]
    concerns = [i for i in items if i["kind"] == "concern"]
    untracked = []
    for a in asks:
        if date_of(a["evidence_id"]) <= since:
            continue
        if not any(_words(a["summary"]) & _words(act["description"]) for act in actions):
            untracked.append(a)
    return {"open_actions": actions, "asks": asks, "promises": promises, "concerns": concerns, "untracked_asks": untracked}
