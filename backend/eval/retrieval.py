"""Retrieval quality: does search find the right documents? Measured on labelled questions.

Run:  uv run python -m eval.retrieval

Each question below has the documents a correct search must surface (judged by hand from the data pack).
Several are worded differently from the documents on purpose ("frustrated" vs "not acceptable"), which is
where keyword search struggles and meaning-based search or a reranker should help.

Metrics (document level, top 5 results, analyst permissions, client-scoped):
  hit@1     share of questions where the first result is a correct document
  hit@5     share of questions where any of the top 5 is correct
  recall@5  share of all correct documents that appear in the top 5 (averaged over questions)
  MRR       mean reciprocal rank of the first correct document (1 = always first)
"""
import time

from app import config
from app.stores import db
from app.stores.doc_index import DocIndex

K = 5
KESTREL, HALDEN, CORVAN = "CLT-001", "CLT-002", "CLT-003"

LABELLED = [
    # (client, question, documents that answer it)
    (KESTREL, "When does the banking agreement renew?", {"BR-1001", "EM-1002"}),
    (KESTREL, "Did we promise FX pricing, and by when?", {"NT-1001", "TR-1001", "EM-1001", "TH-1001"}),
    (KESTREL, "Is the client talking to other banks?", {"TR-1001", "TH-1001"}),
    (KESTREL, "How much extra trade finance do they need for the new warehouse?", {"EM-1003", "TR-1001", "NT-1001"}),
    (KESTREL, "What share of their sales is exported?", {"NT-1001", "TR-1001"}),
    (KESTREL, "How big is the Rotterdam distribution centre?", {"NW-1001", "NW-1003", "NW-1004"}),
    (KESTREL, "Do they want to review card fees?", {"BR-1001", "TR-1001"}),
    (KESTREL, "Is the CFO frustrated about the delay?", {"TH-1001"}),
    (KESTREL, "Why did their margins fall over the summer?", {"TR-1001", "NT-1001"}),
    (HALDEN, "Is the client unhappy with us?", {"EM-2001", "TH-2001"}),
    (HALDEN, "What caused the payroll rejections?", {"TH-2001"}),
    (HALDEN, "Do they want compensation for staff who were paid late?", {"TH-2001"}),
    (HALDEN, "Are they planning to reduce the number of banks they use?", {"NT-2002", "TR-2001", "EM-2003", "NT-2000"}),
    (HALDEN, "Who replaced the previous CFO?", {"NT-2000"}),
    (HALDEN, "Would cash pooling across the hospitals help them?", {"TR-2001"}),
    (HALDEN, "What new facility did they open?", {"NW-2001", "NW-2002"}),
    (HALDEN, "What should we bring to the next meeting?", {"EM-2003", "TR-2001"}),
    (CORVAN, "Do drivers at the new depots need fuel cards?", {"EM-3001", "TH-3001"}),
    (CORVAN, "Did we promise a card programme review?", {"NT-3001", "TH-3001"}),
    (CORVAN, "How can they pay small hauliers faster?", {"NT-3001"}),
    (CORVAN, "What new contract did they win?", {"NW-3001"}),
    (CORVAN, "Why are the corporate cards barely used?", {"NT-3001", "BR-3001"}),
]

CONFIGS = [
    ("Keyword only (BM25)", dict(mode="bm25", rerank=False), ""),
    ("Meaning only (vectors)", dict(mode="vector", rerank=False), ""),
    ("Hybrid (BM25 + vectors, RRF)", dict(mode="hybrid", rerank=False), "used by the briefing agents"),
    ("Hybrid + reranker (ms-marco MiniLM-L-12)", dict(mode="hybrid", rerank=True, model="Xenova/ms-marco-MiniLM-L-12-v2"), ""),
    ("Hybrid + reranker (Jina turbo)", dict(mode="hybrid", rerank=True, model="jinaai/jina-reranker-v1-turbo-en"), "used by chat"),
]


def _docs(hits) -> list[str]:
    """Ranked, de-duplicated document ids; a grouped news story counts as all of its outlets."""
    out = []
    for h in hits:
        for d in [h.doc_id, *(h.also_reported_by or [])]:
            if d not in out:
                out.append(d)
    return out


def score(idx: DocIndex, mode: str, rerank: bool, model: str | None = None) -> dict:
    saved = config.RERANK_MODEL
    if model:
        config.RERANK_MODEL = model
    try:
        hit1 = hit5 = rec = mrr = 0.0
        misses = []
        t = time.perf_counter()
        for client, q, gold in LABELLED:
            ranked = _docs(idx.search(q, client_id=client, k=K, mode=mode, rerank=rerank))
            top = ranked[:K]
            first = next((i for i, d in enumerate(top) if d in gold), None)
            hit1 += first == 0
            hit5 += first is not None
            rec += len(gold & set(top)) / len(gold)
            mrr += 1 / (first + 1) if first is not None else 0
            if first != 0:
                misses.append(q)
        n = len(LABELLED)
        return {"hit@1": round(hit1 / n, 3), "hit@5": round(hit5 / n, 3), "recall@5": round(rec / n, 3),
                "mrr": round(mrr / n, 3), "ms_per_query": round((time.perf_counter() - t) * 1000 / n, 1),
                "not_first": misses}
    finally:
        config.RERANK_MODEL = saved


def evaluate_retrieval(conn=None, configs=None) -> dict:
    idx = DocIndex.load(conn or db.connect(readonly=True))
    rows = []
    for name, c, role in configs or CONFIGS:
        if c["rerank"]:                                   # load the reranker once, outside the timing
            saved, config.RERANK_MODEL = config.RERANK_MODEL, c["model"]
            idx.search("warm up", client_id=KESTREL, rerank=True, k=1)
            config.RERANK_MODEL = saved
        rows.append({"config": name, "role": role, **score(idx, c["mode"], c["rerank"], c.get("model"))})
    return {"questions": len(LABELLED), "k": K, "rows": rows}


if __name__ == "__main__":
    r = evaluate_retrieval()
    print(f"\nRetrieval on {r['questions']} labelled questions (top {r['k']}, document level)\n")
    print(f"{'Configuration':<34}{'hit@1':>7}{'hit@5':>7}{'recall@5':>10}{'MRR':>7}{'ms/query':>10}")
    for row in r["rows"]:
        print(f"{row['config'][:33]:<34}{row['hit@1']:>7}{row['hit@5']:>7}{row['recall@5']:>10}{row['mrr']:>7}{row['ms_per_query']:>10}  {row['role']}")
    for row in r["rows"]:
        print(f"\n{row['config']}: first result not correct for -> {row['not_first']}")
