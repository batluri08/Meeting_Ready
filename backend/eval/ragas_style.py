"""RAGAS-style metrics with Claude as the judge: faithfulness and answer relevancy.

These follow the RAGAS definitions (https://docs.ragas.io), implemented directly rather than through the
ragas library (which brings LangChain and a large dependency tree). They run in the live evaluation only.

Faithfulness (RAGAS): split each statement into atomic claims; the judge decides, for each claim, whether it
  is supported by the evidence that statement cites.  Score = supported claims / all claims.
  This complements the runtime verifier, which is strict on numbers and citations but cannot tell whether
  the WORDING of a sentence matches its source (e.g. "the client is happy" citing a complaint).

Answer relevancy (RAGAS): the judge writes 3 questions the answer would be a good reply to; we embed them
  and the real question with the same embedding model and average the cosine similarity. An evasive,
  non-committal answer scores 0.

All judge prompts go through the LLM gateway, so personal data is masked exactly as in production calls.
"""
import numpy as np

from app.agents.evidence import statement_text
from app.gateway.gateway import Gateway
from app.stores.embeddings import embed_query

FAITH_VERSION = "ragas-faithfulness-v1"
RELEVANCY_VERSION = "ragas-answer-relevancy-v1"
MAX_EVIDENCE_CHARS = 1500

FAITH_SYSTEM = (
    "You are a strict fact-checker evaluating a client briefing. For each statement, break it into short, "
    "self-contained factual claims (atomic claims). For each claim, decide whether it is directly supported by "
    "the evidence listed under that statement, and only that evidence. A claim is supported only if the evidence "
    "states it or it follows directly; claims that add detail, change meaning, overstate, or come from general "
    "knowledge are not supported. Ignore name tokens like [PERSON_1] when judging; treat them as names."
)
FAITH_SCHEMA_BASE = {
    "type": "object",
    "properties": {"statements": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "claims": {"type": "array", "items": {
                "type": "object",
                "properties": {"claim": {"type": "string"}, "supported": {"type": "boolean"},
                               "reason": {"type": "string"}},
                "required": ["claim", "supported", "reason"], "additionalProperties": False}},
        },
        "required": ["id", "claims"], "additionalProperties": False}}},
    "required": ["statements"], "additionalProperties": False,
}

RELEVANCY_SYSTEM = (
    "Given an answer from a bank's client-briefing assistant, write exactly 3 different questions that this answer "
    "would be a good, direct reply to. Also say whether the answer is non-committal (evasive, vague, or says it "
    "cannot answer)."
)
RELEVANCY_SCHEMA = {
    "type": "object",
    "properties": {"questions": {"type": "array", "items": {"type": "string"}},
                   "noncommittal": {"type": "boolean"}},
    "required": ["questions", "noncommittal"], "additionalProperties": False,
}


def _where(ev: dict) -> str:
    """The source label the writer saw (document id and date are part of the evidence, not just its text)."""
    src = ev.get("source", {})
    where = src.get("doc_id") or ", ".join(src.get("refs", []))
    when = src.get("date")
    return f"({where}{', ' + when if when else ''}) " if where or when else ""


def _faith_schema(ids: list[str]) -> dict:
    import copy
    s = copy.deepcopy(FAITH_SCHEMA_BASE)
    s["properties"]["statements"]["items"]["properties"]["id"] = {"type": "string", "enum": ids}
    return s


def faithfulness(briefing: dict, gateway: Gateway) -> dict:
    """Claim-level faithfulness for one briefing: one judge call per section."""
    supported = total = 0
    unsupported: list[dict] = []
    for sec in briefing["sections"]:
        # The uncertainty panel is written by code (conflict checks, access rules), not by the model, so it is
        # not a RAGAS subject; it is verified by the deterministic checks instead.
        if sec["status"] != "ok" or sec["id"] == "uncertainty":
            continue
        items = [s for s in sec["statements"] if not s.get("empty") and s.get("evidence_ids")]
        if not items:
            continue
        ids = [f"S{i + 1}" for i in range(len(items))]
        blocks = []
        for sid, st in zip(ids, items):
            ev = "\n".join(f"    [{e}] {_where(briefing['evidence'][e])}{briefing['evidence'][e]['text'][:MAX_EVIDENCE_CHARS]}"
                           for e in st["evidence_ids"] if e in briefing["evidence"])
            blocks.append(f"{sid}: {statement_text(st)}\n  Evidence:\n{ev}")
        result = gateway.call("judge", FAITH_VERSION, FAITH_SYSTEM, "\n\n".join(blocks), _faith_schema(ids),
                              offline=lambda: {"statements": []})
        by_id = dict(zip(ids, items))
        for judged in result.get("statements", []):
            for c in judged.get("claims", []):
                total += 1
                if c.get("supported"):
                    supported += 1
                else:
                    unsupported.append({"section": sec["id"], "statement": statement_text(by_id.get(judged["id"], {})),
                                        "claim": gateway.masker.unmask(c.get("claim", "")),
                                        "reason": gateway.masker.unmask(c.get("reason", ""))})
    return {"supported": supported, "claims": total, "score": round(supported / total, 3) if total else None,
            "unsupported": unsupported}


# Hand-written ideal answers, used to calibrate answer relevancy: with a small local embedding model, even a
# perfect answer does not score near 1.0, so chat answers are judged against what ideal answers achieve.
IDEAL_ANSWERS = [
    ("Why is revenue flagged?",
     "Revenue is flagged because Q3 2026 revenue fell 12.0% compared with Q2 2026, which is above the 10% threshold."),
    ("Is the client talking to other banks?",
     "Yes. The CFO said another bank has offered FX terms, and some euro collections moved to that bank over the summer."),
    ("What does the CFO want from the next meeting?",
     "The CFO wants the payroll root-cause report and a plan and timeline for moving cash management onto one bank."),
    ("Show the payments STP rate by month",
     "The payments STP rate was 98.9% each month from May to September 2026 and fell to 91.2% in October 2026."),
    ("Why are the corporate cards barely used?",
     "Only a few drivers use the corporate cards; most still claim fuel on expenses, and the promised card review has not happened."),
    ("What new contract did they win?",
     "Corvan signed a five-year contract to run chilled distribution for a national grocer, adding two depots in early 2027."),
]


def calibration_baseline(gateway: Gateway) -> dict:
    """Answer relevancy of the ideal answers: the realistic ceiling for this metric with this embedding model."""
    rows = [answer_relevancy(q, [a], gateway) for q, a in IDEAL_ANSWERS]
    return {"score": round(sum(r["score"] for r in rows) / len(rows), 3), "per_question": rows}


def answer_relevancy(question: str, answer: list[str], gateway: Gateway) -> dict:
    text = " ".join(answer)
    r = gateway.call("judge", RELEVANCY_VERSION, RELEVANCY_SYSTEM, f"Answer:\n{text}", RELEVANCY_SCHEMA,
                     offline=lambda: {"questions": [], "noncommittal": True})
    generated = [gateway.masker.unmask(q) for q in r.get("questions", [])][:3]
    if not generated or r.get("noncommittal"):
        return {"question": question, "score": 0.0, "generated": generated, "noncommittal": bool(r.get("noncommittal"))}
    q = embed_query(question)
    sims = []
    for g in generated:
        v = embed_query(g)
        sims.append(float(np.dot(q, v) / (np.linalg.norm(q) * np.linalg.norm(v))))
    return {"question": question, "score": round(float(np.mean(sims)), 3), "generated": generated, "noncommittal": False}
