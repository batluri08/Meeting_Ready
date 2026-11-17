"""Vector database (Qdrant) for meaning-based search over document chunks.

Prototype: Qdrant runs in-process (in memory) and is loaded at startup from the embeddings that
ingestion saved in SQLite (`chunk_vectors`). Production: set QDRANT_URL to a Qdrant server; the
same code then talks to it over the network.

Permission and client filters are part of the Qdrant query itself (payload filter), so restricted
or other-client chunks are excluded before ranking, never removed afterwards.
"""
import sqlite3
import uuid

import numpy as np
from qdrant_client import QdrantClient, models

from app import config
from app.stores.embeddings import embed_query

COLLECTION = "doc_chunks"


def _point_id(chunk_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"chunk:{chunk_id}"))


class VectorStore:
    def __init__(self, client: QdrantClient):
        self.client = client

    @classmethod
    def from_sqlite(cls, conn: sqlite3.Connection) -> "VectorStore":
        client = QdrantClient(url=config.QDRANT_URL) if config.QDRANT_URL else QdrantClient(location=":memory:")
        rows = conn.execute(
            """SELECT v.chunk_id, v.vector, c.doc_id, c.client_id, c.page, c.text, c.restricted, d.type, d.date
               FROM chunk_vectors v
               JOIN chunks c ON c.chunk_id = v.chunk_id
               JOIN documents d ON d.doc_id = c.doc_id
               WHERE d.duplicate_of IS NULL"""
        ).fetchall()
        # Vector size comes from the stored embeddings, so switching provider needs no code change.
        dim = conn.execute("SELECT MAX(dim) FROM chunk_vectors").fetchone()[0] or 384
        if client.collection_exists(COLLECTION):
            client.delete_collection(COLLECTION)
        client.create_collection(
            COLLECTION, vectors_config=models.VectorParams(size=dim, distance=models.Distance.COSINE),
        )
        client.upsert(
            COLLECTION,
            points=[
                models.PointStruct(
                    id=_point_id(r["chunk_id"]),
                    vector=np.frombuffer(r["vector"], dtype=np.float32).tolist(),
                    payload={
                        "chunk_id": r["chunk_id"], "doc_id": r["doc_id"],
                        "client_id": r["client_id"] or "",          # "" = general document (no client)
                        "page": r["page"], "text": r["text"], "restricted": int(r["restricted"]),
                        "doc_type": r["type"], "date": r["date"],
                    },
                )
                for r in rows
            ],
        )
        return cls(client)

    def search(
        self,
        query: str,
        client_id: str | None = None,
        allow_restricted: bool = False,
        doc_types: set[str] | None = None,
        include_general: bool = False,
        k: int = 5,
    ) -> list[tuple[dict, float]]:
        must = []
        if not allow_restricted:
            must.append(models.FieldCondition(key="restricted", match=models.MatchValue(value=0)))
        if doc_types:
            must.append(models.FieldCondition(key="doc_type", match=models.MatchAny(any=sorted(doc_types))))
        if client_id is not None:
            allowed = [client_id, ""] if include_general else [client_id]
            must.append(models.FieldCondition(key="client_id", match=models.MatchAny(any=allowed)))
        result = self.client.query_points(
            COLLECTION,
            query=embed_query(query).tolist(),
            query_filter=models.Filter(must=must) if must else None,
            limit=k,
            with_payload=True,
        )
        return [(p.payload, float(p.score)) for p in result.points]
