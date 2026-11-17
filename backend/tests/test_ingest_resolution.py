"""Phase 2 checks: every entity-resolution and ingestion trap is handled as the trap manifest expects."""
import pytest

from app import config
from app.data_gen.generate import generate
from app.ingest.run import build_warehouse
from app.resolution.matcher import normalize_name, score
from app.stores import db
from app.stores.doc_index import DocIndex


@pytest.fixture(scope="module")
def conn(tmp_path_factory):
    generate()
    path = tmp_path_factory.mktemp("wh") / "test.db"
    build_warehouse(db_path=path)
    c = db.connect(path, readonly=True)
    yield c
    c.close()


def _client_of(conn, system, source_id):
    return conn.execute("SELECT client_id, status, confidence FROM client_xref WHERE source_system=? AND source_id=?",
                        (system, source_id)).fetchone()


def _client_id(conn, name):
    return conn.execute("SELECT client_id FROM clients WHERE legal_name=?", (name,)).fetchone()[0]


# ---------------------------------------------------------------- matcher unit tests
def test_normalize_expands_abbreviations_and_drops_legal_words():
    assert normalize_name("KESTREL FDS LTD") == "kestrel foods"
    assert normalize_name("Halden Medical Grp.") == "halden medical group"


def test_lookalike_names_with_different_domains_never_merge():
    m = score("Kestrel Fuels PLC", "kestrelfuels.com", "Kestrel Foods Ltd", {"kestrelfoods.com"})
    assert m.decision == "no_match" and m.method == "domain_conflict"


def test_name_alone_never_auto_merges():
    m = score("Kestrel Foods Ltd", "", "Kestrel Foods Ltd", {"kestrelfoods.com"})
    assert m.decision == "review"


# ---------------------------------------------------------------- warehouse checks (one per trap)
def test_eight_clients(conn):
    assert conn.execute("SELECT COUNT(*) FROM clients").fetchone()[0] == 8


def test_alias_billing_merged(conn):  # T-ALIAS-BILLING
    row = _client_of(conn, "billing", "BIL-7001")
    assert row["status"] == "merged" and row["client_id"] == _client_id(conn, "Kestrel Foods Ltd")
    assert row["confidence"] >= config.AUTO_MERGE_THRESHOLD


def test_alias_crm_merged(conn):  # T-ALIAS-CRM
    halden = _client_id(conn, "Halden Medical Group")
    assert _client_of(conn, "crm", "CRM-1012")["client_id"] == halden
    issue = conn.execute("SELECT client_id FROM service_issues WHERE issue_id='ISS-2001'").fetchone()[0]
    assert issue == halden
    cards = conn.execute("SELECT COUNT(*) FROM holdings WHERE client_id=? AND product_code='CARD'", (halden,)).fetchone()[0]
    assert cards == 1


def test_lookalike_kept_apart(conn):  # T-LOOKALIKE
    foods, fuels = _client_id(conn, "Kestrel Foods Ltd"), _client_id(conn, "Kestrel Fuels plc")
    assert foods != fuels
    assert _client_of(conn, "billing", "BIL-7006")["client_id"] == fuels
    assert conn.execute("SELECT client_id FROM documents WHERE doc_id='NW-1002'").fetchone()[0] == fuels


def test_low_confidence_goes_to_review(conn):  # T-LOW-CONF
    row = _client_of(conn, "billing", "BIL-7014")
    assert row["status"] == "review" and row["client_id"] is None
    assert config.REVIEW_THRESHOLD <= row["confidence"] < config.AUTO_MERGE_THRESHOLD
    # its revenue is held back rather than guessed into Larkspur
    assert conn.execute("SELECT COUNT(*) FROM revenue_monthly WHERE source_ref='billing:BIL-7014' AND client_id IS NULL").fetchone()[0] == 12


def test_duplicate_contact_counted_once(conn):  # T-DUPLICATE
    halden = _client_id(conn, "Halden Medical Group")
    cfos = conn.execute("""SELECT contact_id FROM contacts WHERE client_id=? AND duplicate_of IS NULL
                           AND lower(email)='maria.lopes@haldenmedical.com'""", (halden,)).fetchall()
    assert [r[0] for r in cfos] == ["C-201"]
    assert conn.execute("SELECT duplicate_of FROM contacts WHERE contact_id='C-209'").fetchone()[0] == "C-201"


def test_duplicate_doc_indexed_once(conn):  # T-DUPLICATE-DOC
    assert conn.execute("SELECT duplicate_of FROM documents WHERE doc_id='EM-2001-COPY'").fetchone()[0] == "EM-2001"
    assert conn.execute("SELECT COUNT(*) FROM chunks WHERE doc_id='EM-2001-COPY'").fetchone()[0] == 0


@pytest.mark.parametrize("doc_id,client", [("EM-1002", "Kestrel Foods Ltd"), ("EM-3001", "Corvan Logistics")])
def test_missing_id_matched_by_domain(conn, doc_id, client):  # T-MISSING-ID-1/2
    row = conn.execute("SELECT client_id, match_method FROM documents WHERE doc_id=?", (doc_id,)).fetchone()
    assert row["client_id"] == _client_id(conn, client) and row["match_method"] == "email_domain"


def test_restricted_flags_carried(conn):  # T-RESTRICTED (data side; access control is Phase 3)
    assert conn.execute("SELECT restricted FROM pipeline WHERE opp_id='OPP-2002'").fetchone()[0] == 1
    assert conn.execute("SELECT restricted FROM documents WHERE doc_id='NT-2003'").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM chunks WHERE doc_id='NT-2003' AND restricted=0").fetchone()[0] == 0


def test_injection_flagged_but_kept_as_data(conn):  # T-INJECTION (detection side)
    row = conn.execute("SELECT injection_flag, body FROM documents WHERE doc_id='EM-1003'").fetchone()
    assert row["injection_flag"] == 1 and "Rotterdam" in row["body"]
    assert conn.execute("SELECT COUNT(*) FROM documents WHERE injection_flag=1").fetchone()[0] == 1


def test_revenue_joins_through_billing_alias(conn):
    kestrel = _client_id(conn, "Kestrel Foods Ltd")
    q = lambda a, b: conn.execute(  # noqa: E731
        "SELECT SUM(revenue) FROM revenue_monthly WHERE client_id=? AND month BETWEEN ? AND ?", (kestrel, a, b)).fetchone()[0]
    assert round((q("2026-07", "2026-09") / q("2026-04", "2026-06") - 1) * 100, 1) == -12.0


# ---------------------------------------------------------------- search index
def test_search_finds_the_right_chunk(conn):
    idx = DocIndex.load(conn)
    kestrel = _client_id(conn, "Kestrel Foods Ltd")
    hits = idx.search("renewal of the banking agreement", client_id=kestrel)
    assert {h.doc_id for h in hits} >= {"BR-1001", "EM-1002"}


def test_search_never_returns_restricted_to_analyst(conn):
    idx = DocIndex.load(conn)
    halden = _client_id(conn, "Halden Medical Group")
    analyst = idx.search("acquisition clinic chain Atlas mandate", client_id=halden, allow_restricted=False, k=20)
    senior = idx.search("acquisition clinic chain Atlas mandate", client_id=halden, allow_restricted=True, k=20)
    assert all(h.doc_id != "NT-2003" for h in analyst)
    assert any(h.doc_id == "NT-2003" for h in senior)


def test_search_scoped_to_client(conn):
    idx = DocIndex.load(conn)
    foods = _client_id(conn, "Kestrel Foods Ltd")
    hits = idx.search("Kestrel margins", client_id=foods, k=20)
    assert all(h.doc_id != "NW-1002" for h in hits)  # Kestrel Fuels news never leaks in


# ---------------------------------------------------------------- vector database (Qdrant)
def test_every_chunk_embedded(conn):
    n_chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    n_vecs = conn.execute("SELECT COUNT(*) FROM chunk_vectors WHERE dim = 384").fetchone()[0]
    assert n_chunks == n_vecs > 0


def test_vector_search_finds_meaning_not_just_words(conn):
    """'unhappy' never appears in the email; the CFO wrote 'This is not acceptable'."""
    idx = DocIndex.load(conn)
    halden = _client_id(conn, "Halden Medical Group")
    vec = idx.search("Is the client unhappy or complaining about us?", client_id=halden, mode="vector", k=3)
    assert "EM-2001" in {h.doc_id for h in vec}


def test_vector_search_respects_restriction(conn):
    idx = DocIndex.load(conn)
    halden = _client_id(conn, "Halden Medical Group")
    analyst = idx.search("confidential acquisition deal", client_id=halden, mode="vector", k=20)
    senior = idx.search("confidential acquisition deal", client_id=halden, mode="vector", k=20, allow_restricted=True)
    assert all(h.doc_id != "NT-2003" for h in analyst)
    assert senior[0].doc_id == "NT-2003"


def test_vector_search_never_returns_duplicate_doc(conn):
    idx = DocIndex.load(conn)
    halden = _client_id(conn, "Halden Medical Group")
    hits = idx.search("payroll file rejected", client_id=halden, k=20)
    assert "EM-2001-COPY" not in {h.doc_id for h in hits}


def test_hybrid_reports_both_ranks(conn):
    idx = DocIndex.load(conn)
    kestrel = _client_id(conn, "Kestrel Foods Ltd")
    top = idx.search("trade finance limits for Rotterdam", client_id=kestrel, k=3)[0]
    assert top.doc_id in {"EM-1003", "NT-1001"}
    assert top.bm25_rank is not None and top.vector_rank is not None
