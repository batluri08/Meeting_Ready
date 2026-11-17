"""Checks that the generated data pack really contains the planted traps and exact hero trends."""
import csv
import json

import pytest

from app import config
from app.data_gen.generate import generate


@pytest.fixture(scope="module", autouse=True)
def pack():
    return generate()


def _rows(name):
    with (config.RAW_DIR / f"{name}.csv").open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _quarter_total(billing_id, months):
    return sum(int(r["revenue"]) for r in _rows("revenue_monthly") if r["billing_id"] == billing_id and r["month"] in months)


Q2 = {"2026-04", "2026-05", "2026-06"}
Q3 = {"2026-07", "2026-08", "2026-09"}


def test_counts(pack):
    assert pack["raw_tables"] == 15
    assert pack["docs"] == 54
    assert pack["traps"] == 16


def test_extra_docs_add_no_new_risky_content():
    """Distractor docs must not plant unplanned injection or restricted content."""
    from app.data_gen.docs_extra import EXTRA_DOCS
    from app.security.injection import find_injection
    assert all(not find_injection(d["body"]) for d in EXTRA_DOCS)
    assert all(d["sensitivity"] == "normal" for d in EXTRA_DOCS)


def test_halden_stp_drop():
    rows = [r for r in _rows("performance_monthly")
            if r["account_id"] == "CRM-1002" and r["metric"] == "stp_rate_pct"]
    by_month = {r["month"]: float(r["value"]) for r in rows}
    assert by_month["2026-10"] == 91.2 and by_month["2026-09"] == 98.9


def test_relationship_signals_fire_only_for_planned_clients():
    rows = _rows("relationship_metrics")
    sat_drop, wallet_drop = set(), set()
    for acct in {r["account_id"] for r in rows}:
        series = sorted((r for r in rows if r["account_id"] == acct), key=lambda r: r["as_of"])
        prev, last = series[-2], series[-1]
        if float(prev["satisfaction_score"]) - float(last["satisfaction_score"]) >= 2:
            sat_drop.add(acct)
        if int(prev["wallet_share_pct"]) - int(last["wallet_share_pct"]) >= 5:
            wallet_drop.add(acct)
    assert sat_drop == {"CRM-1002"}
    assert wallet_drop == {"CRM-1001"}


def test_duplicate_doc_has_same_body():
    def body(doc_id):
        return (config.DOCS_DIR / f"{doc_id}.md").read_text(encoding="utf-8").split("---", 2)[2]
    assert body("EM-2001") == body("EM-2001-COPY")


def test_kestrel_revenue_down_12_percent():
    change = _quarter_total("BIL-7001", Q3) / _quarter_total("BIL-7001", Q2) - 1
    assert round(change * 100, 1) == -12.0


def test_corvan_revenue_up_15_percent():
    change = _quarter_total("BIL-7003", Q3) / _quarter_total("BIL-7003", Q2) - 1
    assert round(change * 100, 1) == 15.0


def test_every_trap_record_exists():
    ids = {
        "crm": {r["account_id"] for r in _rows("crm_accounts")},
        "billing": {r["billing_id"] for r in _rows("billing_accounts")},
        "contact": {r["contact_id"] for r in _rows("contacts")},
        "pipeline": {r["opp_id"] for r in _rows("pipeline")},
        "doc": {p.stem for p in config.DOCS_DIR.glob("*.md")},
    }
    manifest = json.loads((config.DATA_DIR / "trap_manifest.json").read_text(encoding="utf-8"))
    for trap in manifest["traps"]:
        for ref in trap["records"]:
            kind, rid = ref.split(":", 1)
            assert rid in ids[kind], f"{trap['trap_id']} points at missing {ref}"


def test_missing_id_emails_have_no_account():
    for doc_id in ("EM-1002", "EM-3001"):
        text = (config.DOCS_DIR / f"{doc_id}.md").read_text(encoding="utf-8")
        assert "account_id: \n" in text or "account_id:\n" in text


def test_injection_present_and_restricted_doc_marked():
    assert "IGNORE ALL PREVIOUS INSTRUCTIONS" in (config.DOCS_DIR / "EM-1003.md").read_text(encoding="utf-8")
    assert "sensitivity: restricted" in (config.DOCS_DIR / "NT-2003.md").read_text(encoding="utf-8")
