"""Synthesizer: turn evidence into short, cited statements for each briefing question.

Online: Opus writes an answer, labelled points and 'why it matters' per section from the masked evidence, citing ids,
copying numbers exactly. Offline: deterministic templates built from the same evidence.
Either way the verifier checks every statement before it is shown.

The uncertainty section is assembled by code only (conflicts, stale facts, restricted data, failed
tasks, low-confidence matches, injection attempts): it is never left to the model to decide what is
uncertain.
"""
import copy

from app.agents.evidence import EvidenceStore
from app.gateway.gateway import Gateway

PROMPT_VERSION = "write-section-v2"     # v2: direct answer first, labelled points, optional "why it matters"

SECTIONS = [
    ("profile", "Who is the client and what matters in the relationship?"),
    ("what_changed", "What changed since the last interaction?"),
    ("commitments", "What did the client ask, say or commit to, and what remains open?"),
    ("metrics", "Which metrics or performance are material?"),
    ("opportunities", "Which opportunities should the team discuss, and what evidence supports them?"),
    ("news", "Which recent news or events should shape the conversation?"),
    ("uncertainty", "What is uncertain, conflicting or unavailable?"),
]
QUESTION = dict(SECTIONS)

SCHEMA = {
    "type": "object",
    "properties": {
        "statements": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"text": {"type": "string"},
                               "evidence_ids": {"type": "array", "items": {"type": "string"}}},
                "required": ["text", "evidence_ids"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["statements"],
    "additionalProperties": False,
}

# The writer's output: a direct answer, labelled supporting points, an optional "why it matters", and a layout.
# (Chat answers keep the plain SCHEMA above.)
SECTION_SCHEMA = {
    "type": "object",
    "properties": {
        "layout": {"type": "string", "enum": ["bullets", "table"]},
        "statements": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"role": {"type": "string", "enum": ["answer", "point", "why"]},
                               "label": {"type": "string"},
                               "text": {"type": "string"},
                               "evidence_ids": {"type": "array", "items": {"type": "string"}}},
                "required": ["role", "label", "text", "evidence_ids"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["layout", "statements"],
    "additionalProperties": False,
}

SYSTEM = (
    "You write one section of a pre-meeting client briefing for a bank's relationship team. The reader has two "
    "minutes before the meeting and must see at once how the section answers its question.\n\n"
    "Structure:\n"
    "1. First, exactly one statement with role 'answer' and an empty label: a direct answer to the section question "
    "in one or two plain sentences that make sense on their own. Example, for 'What changed since the last "
    "interaction?': 'Since the call on 2 October 2026, revenue has fallen and the client has complained about "
    "payroll.' Cite every evidence item it draws on.\n"
    "2. Then statements with role 'point': the supporting detail, one idea each, about 30 words at most; usually two "
    "to five, but when the section brief says to list every item, list every one. "
    "Give each a short label (one to four words) naming its topic, e.g. 'Revenue', 'Payroll issue', 'Client asked'.\n"
    "3. Optionally, last, one statement with role 'why' and an empty label: why this matters for the meeting, using "
    "only reasons stated in the evidence (a rule threshold that was crossed, a deadline or close date, an overdue "
    "action, the client's own words). Never your own judgement.\n"
    "Choose layout 'table' when the points are parallel items (metrics, dated changes, asks and actions), "
    "otherwise 'bullets'.\n\n"
    "Writing: plain English, as a senior banker would brief a colleague. Write dates in words (17 January 2022), "
    "money with its currency and thousands separators (GBP 34,000), and product names instead of codes (Cash "
    "Management, not CASH_MGMT). No database field names or jargon.\n\n"
    "Rules: use ONLY the evidence given; every part of every statement (label included) must be stated in the "
    "evidence it cites; cite every evidence item a statement draws on, and the item that actually contains each "
    "fact (when you give a person's role, such as CFO, also cite the evidence that states the role); copy every "
    "number exactly as it appears in the evidence (formatting such as separators or dates in words "
    "is fine); never calculate new numbers, including counts, totals and differences; do not add rankings, "
    "priorities or opinions the evidence does not state (no 'most urgent', 'lead opportunity', 'key risk'); do not "
    "comment on what evidence is missing (gaps are reported separately). Cite only the bracketed evidence ids (E1, "
    "E2...). Names appear as tokens like [PERSON_1]; keep them as is."
)

# What a good answer looks like for each question.
SECTION_GUIDE = {
    "profile": "Answer: who the client is (business, segment, how long with the bank) and what the client has raised "
               "with the bank recently, as the evidence states it. Points: products and how much they are used; "
               "relationship health (share of wallet, satisfaction, primary bank); key contacts and their roles; what "
               "the client has asked about or said recently.",
    "what_changed": "Answer: the main changes since the last interaction, saying when that interaction was (the "
                    "evidence states it). Points: list every change, one per point, newest first, labelled with its "
                    "date in words. Layout: table.",
    "commitments": "Answer: what the client is waiting for from the bank, and what is still open. Points: list every "
                   "item, labelled 'Client asked', 'We promised', 'Open action', 'Not tracked' or 'Client concern', "
                   "each with its due date if the evidence gives one. Layout: table.",
    "metrics": "Answer: what the importance rules flagged as material, and which way the numbers moved. The rules "
               "flag numbers (revenue, payment success rate, product usage, survey scores) AND items: overdue "
               "actions, service issues open too long, deals closing soon. Points: list EVERY flagged item in the "
               "evidence, one per point, none left out, labelled with what it is (e.g. 'Revenue', 'Payments STP "
               "rate', 'Overdue action', 'Open service issue', 'Deal closing soon'); give the value or the days, what "
               "it is compared with, and the rule that flagged it. Layout: table.",
    "opportunities": "Answer: which products the opportunity rules identified to discuss, and the main evidence for "
                     "them. Points: labelled with the product; the data behind it and the client's own words. Mention "
                     "every open pipeline deal with its stage, value and close date.",
    "news": "Answer: what recent news there is about the client and what it reports. Points: labelled with the "
            "outlet and date; one story per point, noting any outlets that disagree.",
}


def _templates(section: str, payload: dict, store: EvidenceStore) -> list[dict]:
    st = []
    if section == "commitments":
        c = payload["commitments"]
        for a in c["open_actions"]:
            st.append({"text": store.get(a["evidence_id"]).text, "evidence_ids": [a["evidence_id"]]})
        for a in c["untracked_asks"]:
            st.append({"text": f"Client ask not tracked as an action: {a['summary']}", "evidence_ids": [a["evidence_id"]]})
        for a in c["concerns"]:
            st.append({"text": f"Client concern: {a['summary']}", "evidence_ids": [a["evidence_id"]]})
        for a in c["promises"]:
            st.append({"text": f"We said: {a['summary']}", "evidence_ids": [a["evidence_id"]]})
        return st
    if section == "opportunities":
        st = [{"text": f"Discuss {o['proposal']} ({o['reason']}).", "evidence_ids": o["evidence"]}
              for o in payload["opportunities"]]
        for eid in payload.get("deals", []):
            ev = store.get(eid)
            st.append({"text": f"Open deal: {ev.text}" + (" [restricted]" if ev.restricted else ""), "evidence_ids": [eid]})
        return st
    quoted = 0
    for eid in payload["evidence"]:
        if eid in payload.get("caveat_ids", set()):
            continue                  # conflict evidence is there to be cited, not listed as content
        ev = store.get(eid)
        if ev.kind == "doc":    # a passage: quote its opening sentences (at most two), cite the document
            quoted += 1
            if quoted > 2:
                continue
            st.append({"text": f"From {ev.source['doc_id']} ({ev.source.get('date')}): \"{_opening(ev.text)}\"",
                       "evidence_ids": [eid]})
        else:   # signals and changes carry a "why it is here" prefix for the model; the template shows the fact
            text = ev.text.split(": ", 1)[1] if ev.kind in ("signal", "change") and ": " in ev.text else ev.text
            st.append({"text": text, "evidence_ids": [eid]})
    return st


def _opening(text: str, limit: int = 220) -> str:
    """First sentences of a passage, up to ~limit characters, never cutting a sentence."""
    import re
    out = ""
    for sent in re.split(r"(?<=[.!?])\s+", " ".join(text.split())):
        if out and len(out) + len(sent) > limit:
            return out + " …"
        out = f"{out} {sent}".strip()
    return out


def write_section(section: str, payload: dict, store: EvidenceStore, gateway: Gateway) -> dict:
    """payload: {'evidence': [ids], plus section-specific structured facts}.
    Returns {'layout': 'bullets' | 'table', 'statements': [{role, label, text, evidence_ids}]}."""
    ids = payload["evidence"]
    if not ids:
        return {"layout": "bullets",
                "statements": [{"text": "Nothing on record for this question.", "evidence_ids": [], "empty": True}]}
    hints = ""
    if section == "commitments":
        c = payload["commitments"]
        action_ids = ", ".join(a["evidence_id"] for a in c["open_actions"])
        hints = ("\nStructured facts found by code (use them; cite their evidence ids):\n"
                 + "\n".join(f"- open action [{a['evidence_id']}]" for a in c["open_actions"])
                 + "".join(f"\n- UNTRACKED client ask [{a['evidence_id']}]: {a['summary']} (code compared it with the "
                           f"open actions [{action_ids or 'none'}] and none covers it; when you say it is untracked, "
                           f"cite those action ids too)" for a in c["untracked_asks"])
                 + "".join(f"\n- client concern [{a['evidence_id']}]: {a['summary']}" for a in c["concerns"]))
    if section == "opportunities":
        hints = "\nOpportunities found by code:\n" + "\n".join(
            f"- {o['proposal']} ({o['reason']}) evidence {o['evidence']}" for o in payload["opportunities"])
        hints += "\nOpen pipeline deals (mention each): " + ", ".join(payload.get("deals", []))
    if payload.get("caveats"):
        hints += ("\nKnown conflicting or out-of-date statements, found by code (also reported in the uncertainty "
                  "panel). Do NOT state the disputed facts as settled; leave them out, or say they are disputed and "
                  "cite the evidence ids given here:\n"
                  + "\n".join(f"- {c['detail']} [{', '.join(c['evidence'])}]" for c in payload["caveats"]))
    content = (f"Section question: {QUESTION[section]}\nWhat a good answer looks like: {SECTION_GUIDE.get(section, '')}"
               f"\n\nEvidence:\n{store.for_prompt(ids)}\n{hints}")
    restricted = any(store.get(i).restricted for i in ids)
    schema = copy.deepcopy(SECTION_SCHEMA)        # citations restricted to this section's evidence ids
    schema["properties"]["statements"]["items"]["properties"]["evidence_ids"]["items"] = {"type": "string", "enum": ids}
    result = gateway.call("write", PROMPT_VERSION, SYSTEM, content, schema,
                          offline=lambda: {"layout": "bullets", "statements": _templates(section, payload, store)},
                          restricted=restricted)
    statements = [{**s, "role": s.get("role") or "point", "label": s.get("label") or ""}
                  for s in result.get("statements", [])]
    statements.sort(key=lambda s: {"answer": 0, "point": 1, "why": 2}.get(s["role"], 1))   # answer first, why last
    return {"layout": result.get("layout") if result.get("layout") in ("bullets", "table") else "bullets",
            "statements": statements}
