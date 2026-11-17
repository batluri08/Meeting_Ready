"""Who can see what. Enforced in code before any data is fetched, so no prompt can talk around it.

Two rules:
  1. Client access: a user sees only clients they cover (the `coverage` table).
  2. Restricted records: only 'senior' clearance sees rows/documents with restricted = 1.
     Everyone else learns only that restricted data exists (a count), never what it says.
"""
import sqlite3
from dataclasses import dataclass


class PermissionDenied(Exception):
    pass


@dataclass(frozen=True)
class UserContext:
    user_id: str
    name: str
    clearance: str                 # analyst | senior
    client_ids: frozenset[str]

    @property
    def allow_restricted(self) -> bool:
        return self.clearance == "senior"


def load_user(conn: sqlite3.Connection, user_id: str) -> UserContext:
    row = conn.execute("SELECT user_id, name, clearance FROM users WHERE user_id = ?", (user_id,)).fetchone()
    if row is None:
        raise PermissionDenied(f"Unknown user {user_id}")
    clients = frozenset(r[0] for r in conn.execute("SELECT DISTINCT client_id FROM coverage WHERE user_id = ?", (user_id,)))
    return UserContext(row["user_id"], row["name"], row["clearance"], clients)


def can_view_client(user: UserContext, client_id: str) -> bool:
    return client_id in user.client_ids


def require_client(user: UserContext, client_id: str) -> None:
    if not can_view_client(user, client_id):
        raise PermissionDenied(f"{user.name} does not cover client {client_id}")


def restricted_summary(conn: sqlite3.Connection, client_id: str) -> dict:
    """What an analyst is told instead of the restricted content: counts only, no details."""
    deals = conn.execute("SELECT COUNT(*) FROM pipeline WHERE client_id = ? AND restricted = 1", (client_id,)).fetchone()[0]
    docs = conn.execute("SELECT COUNT(*) FROM documents WHERE client_id = ? AND restricted = 1", (client_id,)).fetchone()[0]
    return {"restricted_deals": deals, "restricted_documents": docs, "exists": bool(deals or docs)}
