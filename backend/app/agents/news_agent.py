"""News agent: approved news only, one entry per story, with every outlet listed and conflicts flagged.

Market intelligence is untrusted input: it is only ever read from the approved feed (no open web search
in the prototype), and outbound queries would use public identifiers only.
"""
import sqlite3
from datetime import timedelta

from app import config
from app.agents.evidence import EvidenceStore

WINDOW_DAYS = 60


def run_news_agent(conn: sqlite3.Connection, client_id: str, store: EvidenceStore) -> dict:
    since = (config.TODAY - timedelta(days=WINDOW_DAYS)).isoformat()
    rows = conn.execute(
        """SELECT d.doc_id, d.date, d.title, d.source, d.body, d.story_id, c.chunk_id
           FROM documents d JOIN chunks c USING(doc_id)
           WHERE d.client_id = ? AND d.type = 'news' AND d.duplicate_of IS NULL AND d.restricted = 0 AND d.date >= ?
             AND (d.story_id IS NULL OR d.story_id = d.doc_id)
           ORDER BY d.date DESC""", (client_id, since)).fetchall()
    ids, conflicts = [], []
    for r in rows:
        story = conn.execute("SELECT doc_ids, sources, conflict FROM news_stories WHERE story_id = ?", (r["doc_id"],)).fetchone()
        sources = story["sources"].split(" | ") if story else [r["source"]]
        members = story["doc_ids"].split(",") if story else [r["doc_id"]]
        also = [s for s in sources if s != r["source"]]
        also_txt = f" Also reported by {len(also)} other outlet(s): {', '.join(also)}." if also else ""
        ev = store.add("news", r["title"],
                       f"{r['doc_id']} ({r['source']}, {r['date']}): {r['title']}. {r['body']}{also_txt}",
                       {"type": "doc", "doc_id": r["doc_id"], "chunk_id": r["chunk_id"], "date": r["date"],
                        "doc_type": "news", "title": r["title"], "quote": r["body"], "sources": sources,
                        "story_docs": members})
        ids.append(ev.id)
        if story and story["conflict"]:
            # cite every outlet involved, so each figure in the warning is backed by its own source
            member_ids = [ev.id]
            for doc_id in members:
                if doc_id == r["doc_id"]:
                    continue
                m = conn.execute("""SELECT d.doc_id, d.date, d.title, d.source, d.body, c.chunk_id FROM documents d
                                    JOIN chunks c USING(doc_id) WHERE d.doc_id = ?""", (doc_id,)).fetchone()
                member_ids.append(store.add("news", f"{m['title']} ({m['source']})",
                                            f"{m['doc_id']} ({m['source']}, {m['date']}): {m['body']}",
                                            {"type": "doc", "doc_id": m["doc_id"], "chunk_id": m["chunk_id"],
                                             "date": m["date"], "doc_type": "news", "title": m["title"],
                                             "quote": m["body"], "sources": [m["source"]]}).id)
            conflicts.append({"kind": "conflict", "topic": "news_figures", "evidence": member_ids,
                              "detail": f"Outlets disagree on '{r['title']}': {story['conflict']}"})
    return {"evidence": ids, "findings": conflicts}
