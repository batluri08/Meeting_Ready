"""SQL guard: the checkpoint every AI-written (Text-to-SQL) query must pass before it runs.

Checks (any failure = the query is refused, with a reason):
  1. Exactly one statement, and it is a read-only SELECT (or UNION of SELECTs). No INSERT/UPDATE/DELETE,
     DROP, CREATE, ATTACH, PRAGMA, multiple statements, or dangerous functions.
  2. Only allow-listed tables. Documents, chunks, users, system tables etc. are not queryable.
  3. Only allow-listed columns (e.g. contact email addresses are personal data and never selectable).

Then the query is REWRITTEN so it cannot see more than the user may:
  - every table becomes a filtered view: only the current client's rows, and for analysts no
    restricted rows. "SELECT * FROM revenue_monthly" therefore returns this client's revenue only,
    even if the AI was tricked into asking for "every client".
  - a row limit is added; a time limit stops runaway queries.

It runs on a read-only database connection, and the original query, the rewritten query and the
outcome are all returned for the audit log.
"""
import re
import sqlite3
import time
from dataclasses import asdict, dataclass, field

import sqlglot
from sqlglot import exp

MAX_ROWS = 200
TIME_LIMIT_SECONDS = 2.0

ALLOWED_TABLES = {
    "clients", "client_xref", "contacts", "coverage", "products", "holdings", "revenue_monthly",
    "performance_monthly", "relationship_metrics", "pipeline", "service_issues", "open_actions",
    "interactions", "meetings",
}
DENIED_COLUMNS = {"email"}                      # personal data: never selectable through Text-to-SQL
BLOCKED_FUNCTIONS = {"load_extension", "readfile", "writefile", "edit", "fts3_tokenizer"}
WRITE_NODES = tuple(getattr(exp, n) for n in
                    ("Insert", "Update", "Delete", "Drop", "Create", "Alter", "AlterTable", "Command",
                     "Pragma", "Attach", "Detach", "Merge", "TruncateTable") if hasattr(exp, n))
READ_ROOTS = tuple(getattr(exp, n) for n in ("Select", "SetOperation", "Union") if hasattr(exp, n))
CLIENT_ID = re.compile(r"^CLT-\d{3}$")


@dataclass
class GuardResult:
    ok: bool
    reason: str
    original_sql: str
    rewritten_sql: str | None = None
    rows: list[dict] = field(default_factory=list)
    row_count: int = 0
    truncated: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


class SqlGuard:
    def __init__(self, conn: sqlite3.Connection):
        """`conn` should be read-only (db.connect(readonly=True))."""
        self.conn = conn
        self.columns = {
            t: [r[1] for r in conn.execute(f"PRAGMA table_info({t})") if r[1] not in DENIED_COLUMNS]
            for t in ALLOWED_TABLES
        }

    # ------------------------------------------------------------------ validation
    def check(self, sql: str) -> tuple[exp.Expression | None, str]:
        try:
            statements = [s for s in sqlglot.parse(sql, read="sqlite") if s is not None]
        except sqlglot.errors.ParseError as e:
            return None, f"Could not parse the query: {str(e).splitlines()[0]}"
        if len(statements) != 1:
            return None, "Exactly one statement is allowed"
        tree = statements[0]
        if not isinstance(tree, READ_ROOTS) or any(isinstance(n, WRITE_NODES) for n in tree.walk()):
            return None, "Only read-only SELECT queries are allowed"
        cte_names = {c.alias_or_name.lower() for c in tree.find_all(exp.CTE)}
        for table in tree.find_all(exp.Table):
            name = table.name.lower()
            if table.args.get("db") or table.args.get("catalog"):
                return None, f"Schema-qualified table '{table.sql()}' is not allowed"
            if name not in ALLOWED_TABLES and name not in cte_names:
                return None, f"Table '{table.name}' is not allowed"
        for col in tree.find_all(exp.Column):
            if col.name.lower() in DENIED_COLUMNS:
                return None, f"Column '{col.name}' contains personal data and is not allowed"
        for fn in tree.find_all(exp.Anonymous, exp.Func):
            name = (fn.name if isinstance(fn, exp.Anonymous) else fn.sql_name()).lower()
            if name in BLOCKED_FUNCTIONS:
                return None, f"Function '{name}' is not allowed"
        return tree, "ok"

    # ------------------------------------------------------------------ rewrite
    def rewrite(self, tree: exp.Expression, client_id: str, allow_restricted: bool) -> exp.Expression:
        if not CLIENT_ID.match(client_id):
            raise ValueError("Invalid client id")
        cte_names = {c.alias_or_name.lower() for c in tree.find_all(exp.CTE)}
        for table in list(tree.find_all(exp.Table)):
            name = table.name.lower()
            if name in cte_names:
                continue
            cols = self.columns[name]
            conditions = []
            if "client_id" in cols:
                conditions.append(f"client_id = '{client_id}'")
            if "restricted" in cols and not allow_restricted:
                conditions.append("restricted = 0")
            where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
            alias = table.alias_or_name
            view = sqlglot.parse_one(f"SELECT {', '.join(cols)} FROM {name}{where}", read="sqlite")
            table.replace(view.subquery(alias))
        limit = tree.args.get("limit")
        current = None
        if limit is not None:
            try:
                current = int(limit.expression.name)
            except (AttributeError, ValueError):
                current = None
        if current is None or current > MAX_ROWS:
            tree = tree.limit(MAX_ROWS)
        return tree

    # ------------------------------------------------------------------ run
    def run(self, sql: str, client_id: str, allow_restricted: bool) -> GuardResult:
        tree, reason = self.check(sql)
        if tree is None:
            return GuardResult(False, reason, sql)
        try:
            safe = self.rewrite(tree, client_id, allow_restricted).sql(dialect="sqlite")
        except ValueError as e:
            return GuardResult(False, str(e), sql)

        deadline = time.monotonic() + TIME_LIMIT_SECONDS
        self.conn.set_progress_handler(lambda: int(time.monotonic() > deadline), 10_000)
        try:
            rows = [dict(r) for r in self.conn.execute(safe).fetchall()]
        except sqlite3.OperationalError as e:
            msg = "Query took too long" if "interrupted" in str(e) else f"Query failed: {e}"
            return GuardResult(False, msg, sql, safe)
        finally:
            self.conn.set_progress_handler(None, 0)
        return GuardResult(True, "ok", sql, safe, rows, len(rows), len(rows) >= MAX_ROWS)
