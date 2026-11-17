"""Hybrid search over document chunks: keyword (BM25) + meaning (Qdrant vectors), then a reranker. The "R" in RAG.

Both retrievers get the same permission and client filters BEFORE ranking, so chunks the caller may
not see are never scored. Their rankings are merged with Reciprocal Rank Fusion (RRF): a chunk that
ranks well in either list rises; one that ranks well in both rises most. Then (by default) a
cross-encoder reads the question together with each of the top candidates and reorders them.

mode="hybrid" (default) | "bm25" | "vector";  rerank=True/False (default from config)
"""
import re
import sqlite3
import threading
from dataclasses import dataclass

from rank_bm25 import BM25Okapi

from app import config
from app.stores import db
from app.stores.embeddings import rerank_scores
from app.stores.vector_store import VectorStore

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "have", "in", "is", "it", "its",
    "of", "on", "or", "our", "so", "that", "the", "their", "this", "to", "we", "was", "were", "will", "with",
    "you", "your", "they", "what", "did", "do", "about",
}
RRF_K = 60  # standard RRF constant: dampens the gap between rank 1 and rank 2


def tokenize(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOPWORDS]


@dataclass
class Hit:
    chunk_id: str
    doc_id: str
    client_id: str | None
    doc_type: str
    date: str
    page: int
    text: str
    score: float                 # fused score (hybrid) or the single retriever's score
    bm25_rank: int | None = None  # 1 = best; None = not returned by that retriever
    vector_rank: int | None = None
    also_reported_by: list[str] | None = None   # news: other items of the same story (shown, not repeated)


class DocIndex:
    def __init__(self, rows: list[sqlite3.Row], vectors: VectorStore | None = None):
        self.rows = [dict(r) for r in rows]
        self.by_id = {r["chunk_id"]: r for r in self.rows}
        self.vectors = vectors
        self._lock = threading.Lock()        # agents search in parallel; one search at a time is plenty here
        self.story_members: dict[str, list[str]] = {}
        for r in self.rows:
            if r["story_id"]:
                self.story_members.setdefault(r["story_id"], []).append(r["doc_id"])

    @classmethod
    def load(cls, conn: sqlite3.Connection | None = None, with_vectors: bool = True) -> "DocIndex":
        conn = conn or db.connect(readonly=True)
        rows = conn.execute(
            """SELECT c.chunk_id, c.doc_id, c.client_id, c.page, c.text, c.context, c.restricted,
                      d.type AS doc_type, d.date, d.story_id
               FROM chunks c JOIN documents d ON d.doc_id = c.doc_id
               WHERE d.duplicate_of IS NULL"""
        ).fetchall()
        return cls(rows, VectorStore.from_sqlite(conn) if with_vectors else None)

    # ---------------------------------------------------------------- retrievers
    def _allowed(self, r, client_id, allow_restricted, doc_types, include_general) -> bool:
        return ((allow_restricted or not r["restricted"])
                and (doc_types is None or r["doc_type"] in doc_types)
                and (client_id is None or r["client_id"] == client_id or (include_general and r["client_id"] is None)))

    def _bm25(self, query, k, **filters) -> list[tuple[dict, float]]:
        pool = [r for r in self.rows if self._allowed(r, **filters)]
        q = tokenize(query)
        if not pool or not q:
            return []
        scores = BM25Okapi([tokenize(r["context"]) for r in pool]).get_scores(q)
        ranked = sorted(zip(pool, scores), key=lambda p: p[1], reverse=True)
        return [(r, float(s)) for r, s in ranked[:k] if s > 0]

    def _vector(self, query, k, **filters) -> list[tuple[dict, float]]:
        if self.vectors is None:
            return []
        hits = self.vectors.search(query, k=k, **filters)
        return [(self.by_id[p["chunk_id"]], s) for p, s in hits if p["chunk_id"] in self.by_id]

    # ---------------------------------------------------------------- public API
    def search(
        self,
        query: str,
        client_id: str | None = None,
        allow_restricted: bool = False,
        doc_types: set[str] | None = None,
        include_general: bool = False,
        k: int = 5,
        mode: str = "hybrid",
        rerank: bool | None = None,
    ) -> list[Hit]:
        """Rank chunks for `query` among those the caller is allowed to see.

        client_id:        only chunks about this client (plus general docs if include_general)
        allow_restricted: False for analysts; restricted chunks are excluded before scoring
        doc_types:        e.g. {"email"} or {"note", "briefing"}
        rerank:           reorder the top candidates with the cross-encoder (default: config.RERANK_ENABLED)
        """
        rerank = config.RERANK_ENABLED if rerank is None else rerank
        filters = dict(client_id=client_id, allow_restricted=allow_restricted,
                       doc_types=doc_types, include_general=include_general)
        depth = max(k * 3, 10, config.RERANK_CANDIDATES if rerank else 0)  # look deeper in each list before fusing
        with self._lock:
            bm25 = self._bm25(query, depth, **filters) if mode in ("hybrid", "bm25") else []
            vec = self._vector(query, depth, **filters) if mode in ("hybrid", "vector") else []

        bm25_rank = {r["chunk_id"]: i + 1 for i, (r, _) in enumerate(bm25)}
        vec_rank = {r["chunk_id"]: i + 1 for i, (r, _) in enumerate(vec)}

        if mode == "bm25":
            scored = [(r, s) for r, s in bm25]
        elif mode == "vector":
            scored = [(r, s) for r, s in vec]
        else:
            fused: dict[str, float] = {}
            for ranks in (bm25_rank, vec_rank):
                for cid, rank in ranks.items():
                    fused[cid] = fused.get(cid, 0.0) + 1.0 / (RRF_K + rank)
            scored = sorted(((self.by_id[c], s) for c, s in fused.items()), key=lambda p: p[1], reverse=True)

        # Second stage: the cross-encoder reads the question with each candidate and reorders them.
        if rerank and scored:
            candidates = scored[: config.RERANK_CANDIDATES]
            with self._lock:
                scores = rerank_scores(query, [r["context"] for r, _ in candidates])
            scored = sorted(((r, s) for (r, _), s in zip(candidates, scores)), key=lambda p: p[1], reverse=True)

        # One result per news story: keep the best-ranked outlet, list the others.
        hits, seen_stories = [], set()
        for r, s in scored:
            sid = r["story_id"]
            others = None
            if sid and len(self.story_members.get(sid, [])) > 1:
                if sid in seen_stories:
                    continue
                seen_stories.add(sid)
                others = [d for d in self.story_members[sid] if d != r["doc_id"]]
            hits.append(Hit(r["chunk_id"], r["doc_id"], r["client_id"], r["doc_type"], r["date"], r["page"],
                            r["text"], round(s, 4), bm25_rank.get(r["chunk_id"]), vec_rank.get(r["chunk_id"]), others))
            if len(hits) == k:
                break
        return hits
