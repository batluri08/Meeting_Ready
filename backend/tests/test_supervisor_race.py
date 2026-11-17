"""Regression test for a race found in Phase 5: when the failing task finishes LAST, its dependent task is
marked unavailable on the final scheduling pass and the loop used to exit before writing that section.

We force the ordering by making every other task finish first, so the race happens on every run.
"""
import time

from app.agents import supervisor


def test_section_written_when_dependency_fails_last(warehouse_path, index, tmp_path, monkeypatch):
    original = supervisor.run_email_agent

    def slow_failing_email_agent(*args, **kwargs):
        time.sleep(0.5)                       # finish after every other task
        raise RuntimeError("forced slow failure")

    monkeypatch.setattr(supervisor, "run_email_agent", slow_failing_email_agent)
    try:
        b = supervisor.build_briefing("U-ANA", meeting_id="MTG-3", idx=index, db_path=warehouse_path, mode="offline",
                                      audit_dir=tmp_path)
    finally:
        monkeypatch.setattr(supervisor, "run_email_agent", original)
    ids = [s["id"] for s in b["sections"]]
    assert "commitments" in ids, ids
    assert next(s for s in b["sections"] if s["id"] == "commitments")["status"] == "unavailable"
    assert set(b["unavailable"]) == {"email_extract", "commitments"}
