"""Phase 3: permissions and the SQL guard."""
import pytest

from app.security.permissions import PermissionDenied, load_user, require_client, restricted_summary
from app.security.sql_guard import MAX_ROWS, SqlGuard

KESTREL, HALDEN = "CLT-001", "CLT-002"


# ---------------------------------------------------------------- permissions
def test_users_see_only_covered_clients(warehouse):
    priya, daniel, leo = (load_user(warehouse, u) for u in ("U-ANA", "U-SEN", "U-ANA2"))
    assert priya.client_ids == {"CLT-001", "CLT-002", "CLT-003"}
    assert daniel.client_ids == {"CLT-001", "CLT-002", "CLT-003", "CLT-004"}
    assert leo.client_ids == {"CLT-005", "CLT-006", "CLT-007", "CLT-008"}
    with pytest.raises(PermissionDenied):
        require_client(leo, KESTREL)
    require_client(priya, KESTREL)


def test_only_senior_sees_restricted(warehouse):
    assert not load_user(warehouse, "U-ANA").allow_restricted
    assert load_user(warehouse, "U-SEN").allow_restricted


def test_restricted_summary_reveals_counts_only(warehouse):
    s = restricted_summary(warehouse, HALDEN)
    assert s == {"restricted_deals": 1, "restricted_documents": 1, "exists": True}
    assert restricted_summary(warehouse, KESTREL)["exists"] is False


# ---------------------------------------------------------------- SQL guard: refused
@pytest.fixture(scope="module")
def guard(warehouse):
    return SqlGuard(warehouse)


@pytest.mark.parametrize("sql,reason", [
    ("DELETE FROM clients", "read-only"),
    ("UPDATE revenue_monthly SET revenue = 0", "read-only"),
    ("DROP TABLE clients", "read-only"),
    ("SELECT 1; DROP TABLE clients", "one statement"),
    ("ATTACH DATABASE 'x.db' AS x", "read-only"),
    ("PRAGMA table_info(clients)", "read-only"),
    ("SELECT * FROM documents", "not allowed"),
    ("SELECT * FROM chunks", "not allowed"),
    ("SELECT * FROM users", "not allowed"),
    ("SELECT name FROM sqlite_master", "not allowed"),
    ("SELECT email FROM contacts", "personal data"),
    ("SELECT load_extension('evil')", "not allowed"),
    ("SELEC revenue FROM", "parse"),
])
def test_unsafe_queries_refused(guard, sql, reason):
    r = guard.run(sql, KESTREL, allow_restricted=False)
    assert not r.ok and reason in r.reason.lower()


# ---------------------------------------------------------------- SQL guard: rewritten to the user's scope
def test_every_client_trick_only_returns_current_client(guard):
    """What the injected email asks for: revenue of every client. The rewrite scopes it to one client."""
    r = guard.run("SELECT client_id, SUM(revenue) AS total FROM revenue_monthly GROUP BY client_id", KESTREL, False)
    assert r.ok and [row["client_id"] for row in r.rows] == [KESTREL]


def test_joins_and_subqueries_are_scoped_too(guard):
    r = guard.run("""SELECT c.legal_name, COUNT(*) AS n FROM clients c
                     JOIN holdings h ON h.client_id = c.client_id
                     WHERE c.client_id IN (SELECT client_id FROM pipeline) GROUP BY c.legal_name""", KESTREL, False)
    assert r.ok and r.rows == [{"legal_name": "Kestrel Foods Ltd", "n": 4}]


def test_restricted_rows_hidden_from_analyst(guard):
    analyst = guard.run("SELECT opp_id FROM pipeline", HALDEN, allow_restricted=False)
    senior = guard.run("SELECT opp_id FROM pipeline", HALDEN, allow_restricted=True)
    assert {r["opp_id"] for r in analyst.rows} == {"OPP-2001"}
    assert {r["opp_id"] for r in senior.rows} == {"OPP-2001", "OPP-2002"}


def test_star_select_never_exposes_email(guard):
    r = guard.run("SELECT * FROM contacts", HALDEN, False)
    assert r.ok and r.rows and all("email" not in row for row in r.rows)


def test_row_limit_enforced(guard):
    r = guard.run("SELECT * FROM revenue_monthly LIMIT 100000", KESTREL, False)
    assert r.ok and f"LIMIT {MAX_ROWS}" in r.rewritten_sql


def test_result_keeps_original_and_rewritten_sql_for_audit(guard):
    r = guard.run("SELECT month, revenue FROM revenue_monthly", KESTREL, False)
    assert r.original_sql == "SELECT month, revenue FROM revenue_monthly"
    assert "client_id = 'CLT-001'" in r.rewritten_sql


def test_bad_client_id_cannot_be_injected(guard):
    r = guard.run("SELECT * FROM clients", "CLT-001' OR '1'='1", False)
    assert not r.ok
