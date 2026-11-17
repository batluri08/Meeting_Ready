"""Phase 4: gateway, agents, synthesizer, verifier and the full briefing (offline mode: fast, free, repeatable)."""
import json

import pytest

from app.agents.evidence import EvidenceStore
from app.agents.supervisor import CATALOGUE, build_briefing
from app.agents.verifier import check
from app.gateway.pii import PiiMasker
from app.security.permissions import PermissionDenied


@pytest.fixture(scope="module")
def run(warehouse_path, index, tmp_path_factory):
    audit_dir = tmp_path_factory.mktemp("audit")
    cache = {}

    def _run(user, meeting, fail=None):
        key = (user, meeting, tuple(sorted(fail or [])))
        if key not in cache:
            cache[key] = build_briefing(user, meeting_id=meeting, idx=index, db_path=warehouse_path, mode="offline",
                                        fail_tasks=set(fail or []), audit_dir=audit_dir)
        return cache[key]
    return _run


def _section(b, sid):
    return next(s for s in b["sections"] if s["id"] == sid)


def _texts(b, sid):
    return " | ".join(s["text"] for s in _section(b, sid)["statements"])


def _audit(b):
    return [json.loads(line) for line in open(b["audit_path"], encoding="utf-8")]


# ---------------------------------------------------------------- structure and faithfulness
@pytest.mark.parametrize("meeting", ["MTG-1", "MTG-2", "MTG-3"])
def test_all_seven_questions_answered_and_every_statement_cited(run, meeting):
    b = run("U-ANA", meeting)
    assert [s["id"] for s in b["sections"]] == ["profile", "what_changed", "commitments", "metrics",
                                                "opportunities", "news", "uncertainty"]
    for s in b["sections"]:
        assert s["status"] == "ok" and s["statements"]
        assert s["dropped"] == []                                  # offline templates always pass the verifier
        for st in s["statements"]:
            assert st.get("empty") or (st["evidence_ids"] and all(e in b["evidence"] for e in st["evidence_ids"]))


def test_plan_covers_every_task(run):
    assert {t["id"] for t in run("U-ANA", "MTG-1")["plan"]["tasks"]} == set(CATALOGUE)


def test_material_metrics_are_the_rule_signals(run):
    assert "revenue down 12.0%" in _texts(run("U-ANA", "MTG-1"), "metrics")
    assert "91.2%" in _texts(run("U-ANA", "MTG-2"), "metrics")
    assert "only 18% used" in _texts(run("U-ANA", "MTG-3"), "metrics")


# ---------------------------------------------------------------- commitments
def test_untracked_asks_found(run):
    assert "confirm the banking agreement renewal" in _texts(run("U-ANA", "MTG-1"), "commitments")
    halden = _section(run("U-ANA", "MTG-2"), "commitments")["statements"]
    assert any("not tracked" in s["text"] and "compensation" in s["text"] for s in halden)


def test_competitive_threat_surfaced(run):
    assert "go with the other bank" in _texts(run("U-ANA", "MTG-1"), "commitments")


# ---------------------------------------------------------------- uncertainty: every planted condition shows up
def test_kestrel_uncertainty(run):
    t = _texts(run("U-ANA", "MTG-1"), "uncertainty")
    assert "June 2027" in t and "March 2027" in t                         # T-CONFLICT
    assert "EM-1000" in t and "Out of date" in t                           # T-STALE-2
    assert "40000" in t and "45000" in t                                   # T-NEWS-CONFLICT
    assert "EM-1002" in t and "email domain" in t                          # T-MISSING-ID-1
    assert "EM-1003" in t and "treated as data" in t                       # T-INJECTION


def test_halden_uncertainty_for_analyst_and_senior(run):
    analyst = _texts(run("U-ANA", "MTG-2"), "uncertainty")
    assert "J. Park" in analyst and "Maria Lopes" in analyst              # T-STALE
    assert "Restricted information exists" in analyst                    # T-RESTRICTED (count only)
    assert "Restricted information exists" not in _texts(run("U-SEN", "MTG-2"), "uncertainty")


# ---------------------------------------------------------------- permissions and leakage
def test_analyst_never_receives_restricted_content(run):
    blob = json.dumps(run("U-ANA", "MTG-2"))
    for secret in ("OPP-2002", "NT-2003", "Atlas", "2,500,000", "clinic chain"):
        assert secret not in blob


def test_senior_sees_restricted_deal(run):
    assert "OPP-2002" in _texts(run("U-SEN", "MTG-2"), "opportunities")


def test_lookalike_never_cited_in_kestrel_foods_briefing(run):
    docs = {e["source"].get("doc_id") for e in run("U-ANA", "MTG-1")["evidence"].values()}
    assert not docs & {"NW-1002", "NW-6002", "EM-6001", "NT-6001", "NW-9003"}


def test_user_without_coverage_is_refused(warehouse_path, index):
    with pytest.raises(PermissionDenied):
        build_briefing("U-ANA2", meeting_id="MTG-1", idx=index, db_path=warehouse_path, mode="offline")


# ---------------------------------------------------------------- injection
def test_injection_logged_and_never_obeyed(run):
    b = run("U-ANA", "MTG-1")
    events = {e["event"] for e in _audit(b)}
    assert "injection_attempt" in events
    everything = json.dumps(b["sections"])
    assert "IGNORE ALL PREVIOUS" not in everything and "admin mode" not in everything.lower()
    assert "Larkspur" not in everything and "Halden" not in everything     # no other client's data


# ---------------------------------------------------------------- opportunities
@pytest.mark.parametrize("meeting,expected", [
    ("MTG-1", ["FX hedging", "trade finance"]),
    ("MTG-2", ["cash pooling"]),
    ("MTG-3", ["supply chain finance", "cards for all drivers"]),
])
def test_opportunities_backed_by_data_and_client_words(run, meeting, expected):
    t = _texts(run("U-ANA", meeting), "opportunities")
    for e in expected:
        assert e in t


# ---------------------------------------------------------------- resilience
def test_failed_agent_is_retried_then_marked_unavailable(run):
    b = run("U-ANA", "MTG-3", fail=["email_extract"])
    tasks = [(e["task"], e["status"], e.get("attempt"), e.get("error")) for e in _audit(b) if e["event"] == "task"]
    diag = f"unavailable={b['unavailable']} task_log={tasks}"   # printed if this ever fails
    assert set(b["unavailable"]) == {"email_extract", "commitments"}, diag
    assert _section(b, "commitments")["status"] == "unavailable", diag
    assert "Unavailable: 'email_extract'" in _texts(b, "uncertainty"), diag
    attempts = [e for e in _audit(b) if e["event"] == "task" and e["task"] == "email_extract"]
    assert [a["attempt"] for a in attempts] == [1, 2], diag                # retried once
    assert _section(b, "metrics")["statements"]                            # the rest still completed


# ---------------------------------------------------------------- PII masking
def test_masking_and_unmasking(warehouse):
    m = PiiMasker.from_db(warehouse)
    text = "Maria Lopes (maria.lopes@haldenmedical.com) said Maria wants it; the 2024 note says J. Park."
    masked = m.mask(text)
    assert "Maria" not in masked and "@" not in masked and "Park" not in masked
    assert masked.count("[PERSON_1]") == 2                                 # same person, same token
    restored = m.unmask(masked)
    # a token restores to the person's full name (short forms like 'Maria' come back as 'Maria Lopes')
    assert "maria.lopes@haldenmedical.com" in restored and restored.count("Maria Lopes") == 2
    assert "Jin Park" in restored


def test_prompt_sent_to_model_contains_no_names(warehouse, run):
    b = run("U-ANA", "MTG-2")
    m = PiiMasker.from_db(warehouse)
    store = EvidenceStore()
    for e in b["evidence"].values():
        store.add(e["kind"], e["title"], e["text"], e["source"])
    prompt = m.mask(store.for_prompt(list(store.items)))
    assert m.leaks(prompt) == []


# ---------------------------------------------------------------- verifier
def test_verifier_rejects_uncited_and_invented_numbers():
    store = EvidenceStore()
    e = store.add("signal", "rev", "Q3 2026 revenue down 12.0% (GBP 397,320 vs 451,500)", {"type": "sql"})
    ok = {e.id}
    assert check({"text": "Revenue fell 12.0% to GBP 397,320.", "evidence_ids": [e.id]}, ok, store) is None
    assert "no citation" in check({"text": "Revenue fell 12.0%.", "evidence_ids": []}, ok, store)
    assert "numbers not in cited evidence" in check({"text": "Revenue fell 15%.", "evidence_ids": [e.id]}, ok, store)
    assert "not given" in check({"text": "Revenue fell.", "evidence_ids": ["E99"]}, ok, store)


def test_verifier_checks_numbers_in_labels_too(tmp_path):
    """v2 writer: a point has a short bold label; a number there must be in the cited evidence like any other."""
    from app.agents.evidence import EvidenceStore
    from app.agents.verifier import verify
    from app.gateway.audit import AuditLog
    store = EvidenceStore()
    e = store.add("sql", "Revenue", "Q3 2026 revenue 397320 vs Q2 2026 451500 (2026-10-02)", {"type": "sql"})
    ok = {"role": "point", "label": "2 October 2026", "text": "Revenue GBP 397,320 vs 451,500", "evidence_ids": [e.id]}
    bad = {"role": "point", "label": "Down 15%", "text": "Revenue fell", "evidence_ids": [e.id]}
    kept, dropped = verify("metrics", [ok, bad], {e.id}, store, AuditLog("t", tmp_path))
    assert kept == [ok] and "15" in dropped[0]["reason"]


def test_writer_returns_layout_and_ordered_roles():
    """The writer's output is normalised: answer first, 'why' last, defaults for missing role/label."""
    from app.agents import synthesizer
    from app.agents.evidence import EvidenceStore
    store = EvidenceStore()
    e = store.add("sql", "x", "fact 1", {"type": "sql"})

    class FakeGateway:
        def call(self, *a, **k):
            return {"layout": "table", "statements": [
                {"role": "why", "label": "", "text": "w", "evidence_ids": [e.id]},
                {"role": "point", "label": "L", "text": "p", "evidence_ids": [e.id]},
                {"role": "answer", "label": "", "text": "a", "evidence_ids": [e.id]}]}
    out = synthesizer.write_section("metrics", {"evidence": [e.id], "caveats": []}, store, FakeGateway())
    assert out["layout"] == "table" and [s["role"] for s in out["statements"]] == ["answer", "point", "why"]
