"""Phase 3: materiality rules, date logic and 'what changed', checked against docs/DATA.md section 7."""
from datetime import date

from app.metrics.changes import changes_since_last_interaction
from app.metrics.periods import latest_complete_quarters, last_interaction
from app.metrics.rules import evaluate

KESTREL, HALDEN, CORVAN = "CLT-001", "CLT-002", "CLT-003"
BACKGROUND = ["CLT-004", "CLT-005", "CLT-006", "CLT-007", "CLT-008"]


def _rules(conn, cid, senior=True):
    return sorted((s.rule, s.record_id) for s in evaluate(conn, cid, allow_restricted=senior))


# ---------------------------------------------------------------- periods
def test_latest_complete_quarter():
    assert latest_complete_quarters(date(2026, 11, 16)) == ((2026, 3), (2026, 2))
    assert latest_complete_quarters(date(2027, 2, 1)) == ((2026, 4), (2026, 3))


def test_last_interaction_and_fallback(warehouse):
    assert last_interaction(warehouse, KESTREL)["date"] == "2026-10-14"
    assert last_interaction(warehouse, HALDEN)["date"] == "2026-09-30"
    meridian = last_interaction(warehouse, "CLT-005")          # no meetings logged
    assert meridian["fallback"] and meridian["date"] == "2026-08-18"


# ---------------------------------------------------------------- rules: exactly the planned signals
def test_kestrel_signals(warehouse):
    assert _rules(warehouse, KESTREL) == [("action_past_due", "ACT-1001"), ("revenue_qoq", None),
                                          ("wallet_share_drop", None)]


def test_halden_signals(warehouse):
    assert _rules(warehouse, HALDEN) == [("issue_aged", "ISS-2001"), ("pipeline_closing", "OPP-2001"),
                                         ("satisfaction_drop", None), ("stp_low", None)]


def test_corvan_signals(warehouse):
    assert _rules(warehouse, CORVAN) == [("action_past_due", "ACT-3001"), ("low_utilization", "CARD"),
                                         ("revenue_qoq", None)]


def test_background_clients_have_no_signals(warehouse):
    for cid in BACKGROUND:
        assert evaluate(warehouse, cid, allow_restricted=True) == []


def test_signal_numbers_match_their_evidence(warehouse):
    rev = [s for s in evaluate(warehouse, KESTREL) if s.rule == "revenue_qoq"][0]
    row = rev.evidence.rows[0]
    assert rev.value == round((row["current_q"] / row["previous_q"] - 1) * 100, 1) == -12.0
    assert "397,320" in rev.title and "451,500" in rev.title
    assert rev.evidence.source_refs == ["billing:BIL-7001"]       # revenue reached Kestrel via the alias match


def test_every_signal_carries_a_rerunnable_query(warehouse):
    for cid in (KESTREL, HALDEN, CORVAN):
        for s in evaluate(warehouse, cid):
            rows = [dict(r) for r in warehouse.execute(s.evidence.query, s.evidence.params)]
            assert rows and all(r in rows for r in s.evidence.rows)


# ---------------------------------------------------------------- what changed
def _change_refs(conn, cid, senior=False):
    return {c.ref for c in changes_since_last_interaction(conn, cid, allow_restricted=senior)["changes"]}


def test_kestrel_changes_since_14_october(warehouse):
    refs = _change_refs(warehouse, KESTREL)
    assert {"ISS-1001", "ISS-1002", "EM-1001", "EM-1002", "EM-1003", "TH-1001", "OPP-1001", "ACT-1001"} <= refs
    assert "EM-1004" not in refs                                     # September: before the last meeting


def test_news_story_listed_once_in_changes(warehouse):
    result = changes_since_last_interaction(warehouse, KESTREL)
    rotterdam = [c for c in result["changes"] if c.ref in {"NW-1001", "NW-1003", "NW-1004"}]
    assert len(rotterdam) == 1 and "2 other outlets" in rotterdam[0].summary


def test_restricted_changes_only_for_senior(warehouse):
    analyst, senior = _change_refs(warehouse, HALDEN), _change_refs(warehouse, HALDEN, senior=True)
    assert "NT-2003" not in analyst and "OPP-2002" not in analyst
    assert {"NT-2003", "OPP-2002"} <= senior
