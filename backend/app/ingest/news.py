"""Group the same news story reported by different outlets, and flag figures that disagree.

Exact fingerprints miss syndicated news: each outlet words the story differently. Two news items are
treated as the same story when they are about the same client, published within NEWS_STORY_WINDOW_DAYS
of each other, and their embeddings are very similar (cosine >= NEWS_SAME_STORY_SIM).

Within a story, figures with a unit (square metres, jobs, staff, %) are compared across outlets. If the
outlets give different values for the same unit, the story is flagged as conflicting, so the briefing
shows the disagreement instead of picking one number.
"""
import re
import sqlite3
from datetime import date

import numpy as np

from app import config

UNITS = {
    "square metre": "m2", "square metres": "m2", "square meter": "m2", "square meters": "m2",
    "sq m": "m2", "m²": "m2", "jobs": "jobs", "staff": "staff", "employees": "staff", "%": "%", "percent": "%",
}
FIGURE = re.compile(
    r"(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(square metres?|square meters?|sq m|m²|jobs|staff|employees|%|percent)",
    re.IGNORECASE,
)


def figures(text: str) -> dict[str, set[str]]:
    """'a 40,000 square metre hub, 120 jobs' -> {'m2': {'40000'}, 'jobs': {'120'}}"""
    out: dict[str, set[str]] = {}
    for num, unit in FIGURE.findall(text):
        out.setdefault(UNITS[unit.lower()], set()).add(num.replace(",", ""))
    return out


def _cos(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def group_news_stories(conn: sqlite3.Connection, vec_by_chunk: dict[str, np.ndarray]) -> list[dict]:
    rows = conn.execute(
        """SELECT d.doc_id, d.client_id, d.date, d.source, d.body, c.chunk_id
           FROM documents d JOIN chunks c ON c.doc_id = d.doc_id
           WHERE d.type = 'news' AND d.duplicate_of IS NULL AND c.page = 1 AND c.part = 1
           ORDER BY d.date, d.doc_id"""
    ).fetchall()

    story_of: dict[str, str] = {}
    members: dict[str, list] = {}
    for r in rows:
        best = None
        for sid, group in members.items():
            lead = group[0]
            same_client = lead["client_id"] == r["client_id"]
            days = abs((date.fromisoformat(r["date"]) - date.fromisoformat(lead["date"])).days)
            sim = _cos(vec_by_chunk[r["chunk_id"]], vec_by_chunk[lead["chunk_id"]])
            if same_client and days <= config.NEWS_STORY_WINDOW_DAYS and sim >= config.NEWS_SAME_STORY_SIM:
                if best is None or sim > best[1]:
                    best = (sid, sim)
        sid = best[0] if best else r["doc_id"]
        members.setdefault(sid, []).append(r)
        story_of[r["doc_id"]] = sid

    stories = []
    for sid, group in members.items():
        if len(group) < 2:
            continue
        per_unit: dict[str, dict[str, list[str]]] = {}
        for r in group:
            for unit, values in figures(r["body"]).items():
                for v in values:
                    per_unit.setdefault(unit, {}).setdefault(v, []).append(r["doc_id"])
        disagreements = [
            f"{unit}: " + " vs ".join(f"{v} ({', '.join(ids)})" for v, ids in sorted(vals.items()))
            for unit, vals in per_unit.items() if len(vals) > 1
        ]
        story = {
            "story_id": sid,
            "client_id": group[0]["client_id"],
            "doc_ids": [r["doc_id"] for r in group],
            "sources": [r["source"] for r in group],
            "conflict": "; ".join(disagreements) or None,
        }
        stories.append(story)
        conn.execute("INSERT INTO news_stories VALUES (?,?,?,?,?)",
                     (sid, story["client_id"], ",".join(story["doc_ids"]), " | ".join(story["sources"]), story["conflict"]))

    conn.executemany("UPDATE documents SET story_id = ? WHERE doc_id = ?", [(s, d) for d, s in story_of.items()])
    return stories
