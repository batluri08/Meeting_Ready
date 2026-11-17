"""Evidence: every fact the system states carries a pointer to where it came from.

For structured data the pointer is the exact SQL query, its parameters and the rows it returned, so any
number in a briefing can be re-run and checked.
"""
import sqlite3
from dataclasses import asdict, dataclass, field


@dataclass
class SqlEvidence:
    query: str
    params: tuple
    rows: list[dict]
    source_refs: list[str] = field(default_factory=list)   # e.g. ['billing:BIL-7001']

    def to_dict(self) -> dict:
        return asdict(self)


def run(conn: sqlite3.Connection, query: str, params: tuple = ()) -> SqlEvidence:
    """Run a read query and keep it, with its result, as evidence."""
    rows = [dict(r) for r in conn.execute(query, params).fetchall()]
    refs = sorted({r["source_ref"] for r in rows if r.get("source_ref")})
    return SqlEvidence(" ".join(query.split()), tuple(params), rows, refs)
