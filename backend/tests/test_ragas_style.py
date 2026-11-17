"""RAGAS-style metrics: scoring logic, with a stand-in judge (no API calls)."""
from app.gateway.audit import AuditLog
from app.gateway.pii import PiiMasker
from eval.ragas_style import answer_relevancy, faithfulness


class FakeJudge:
    """Behaves like Gateway.call for the 'judge' task, returning fixed verdicts."""
    def __init__(self, tmp_path, verdicts=None, relevancy=None):
        self.masker = PiiMasker(["Tom Reyes"])
        self.audit = AuditLog("test", tmp_path)
        self.verdicts, self.relevancy = verdicts, relevancy

    def call(self, task, version, system, content, schema, offline, restricted=False):
        assert task == "judge" and "Tom Reyes" not in self.masker.mask(content)
        return self.verdicts if "faithfulness" in version else self.relevancy


BRIEFING = {
    "sections": [{"id": "metrics", "status": "ok", "statements": [
        {"text": "Revenue fell 12.0% and the client is delighted.", "evidence_ids": ["E1"]},
        {"text": "Nothing on record.", "evidence_ids": [], "empty": True},
    ]}],
    "evidence": {"E1": {"text": "Q3 2026 revenue down 12.0% vs Q2 2026"}},
}


def test_faithfulness_counts_supported_claims(tmp_path):
    judge = FakeJudge(tmp_path, verdicts={"statements": [{"id": "S1", "claims": [
        {"claim": "Revenue fell 12.0%", "supported": True, "reason": "stated"},
        {"claim": "The client is delighted", "supported": False, "reason": "not in evidence"}]}]})
    r = faithfulness(BRIEFING, judge)
    assert r == {"supported": 1, "claims": 2, "score": 0.5, "unsupported": [
        {"section": "metrics", "statement": "Revenue fell 12.0% and the client is delighted.",
         "claim": "The client is delighted", "reason": "not in evidence"}]}


def test_answer_relevancy_rewards_on_topic_and_zeroes_noncommittal(tmp_path):
    on_topic = FakeJudge(tmp_path, relevancy={"questions": ["Why is revenue flagged?", "Why did revenue fall?",
                                                           "What is flagged about revenue?"], "noncommittal": False})
    off_topic = FakeJudge(tmp_path, relevancy={"questions": ["What is the weather in Leeds?"] * 3, "noncommittal": False})
    evasive = FakeJudge(tmp_path, relevancy={"questions": ["Why is revenue flagged?"] * 3, "noncommittal": True})
    q = "Why is revenue flagged?"
    good, bad = answer_relevancy(q, ["x"], on_topic)["score"], answer_relevancy(q, ["x"], off_topic)["score"]
    assert good > 0.85 and bad < good
    assert answer_relevancy(q, ["x"], evasive)["score"] == 0.0
