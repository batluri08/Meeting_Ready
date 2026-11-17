"""Phase 7: the evaluation suite itself must pass (offline), so any regression shows up in the test run."""
from eval.run import evaluate


def test_offline_evaluation_passes_every_check_and_trap(warehouse_path, tmp_path):
    # retrieval is measured in its own (faster) test below
    r = evaluate("offline", db_path=warehouse_path, audit_dir=tmp_path, write=False, verbose=False, with_retrieval=False)
    failed = [f"{c['test']}: {c['result']} ({c['detail'][:200]})" for c in r["checks"] if not c["passed"]]
    assert not failed, failed
    assert all(t["passed"] for t in r["traps"]), [t["trap_id"] for t in r["traps"] if not t["passed"]]
    assert len(r["traps"]) == 16


def test_retrieval_quality_holds(warehouse):
    """Hybrid search (what the agents use) must keep finding a right document in the top 5."""
    from eval.retrieval import CONFIGS, evaluate_retrieval
    hybrid = [c for c in CONFIGS if c[2] == "used by the briefing agents"]
    row = evaluate_retrieval(warehouse, configs=hybrid)["rows"][0]
    assert row["hit@5"] >= 0.95 and row["recall@5"] >= 0.95, row


def test_masker_does_not_match_names_inside_identifiers(warehouse):
    from app.gateway.pii import PiiMasker
    m = PiiMasker.from_db(warehouse)
    assert m.mask("user U-ANA and U-ANA2") == "user U-ANA and U-ANA2"
    assert m.mask("Ana Duarte said") .startswith("[PERSON_")
