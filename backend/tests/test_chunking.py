"""Chunking rules per document type, plus retrieval quality with the larger, noisier corpus."""
import pytest

from app import config
from app.data_gen.generate import generate
from app.ingest.chunking import chunk_document, clean_email, split_by_size
from app.ingest.run import build_warehouse
from app.stores import db
from app.stores.doc_index import DocIndex


# ---------------------------------------------------------------- unit rules
def test_email_greeting_and_signoff_removed():
    body = "Hi Priya,\n\nPlease send the pricing by Friday.\n\nThanks,\nAna"
    assert clean_email(body) == "Please send the pricing by Friday."


def test_size_split_respects_limit_and_overlaps():
    text = " ".join(f"Sentence number {i} has some words in it." for i in range(60))
    parts = split_by_size(text, max_words=50)
    assert len(parts) > 1
    assert all(len(p.split()) <= 50 for p in parts)
    assert parts[0].split(". ")[-1].rstrip(".") in parts[1]  # last sentence carried into the next part


def test_context_header_carries_client_name():
    meta = {"type": "note", "date": "2026-10-14", "title": "Meeting notes"}
    chunks = chunk_document(meta, "## Page 1\nAlpha.\n\n## Page 2\nTom asked for FX pricing.", "Kestrel Foods Ltd")
    page2 = [c for c in chunks if c.page == 2][0]
    assert "Kestrel Foods Ltd" in page2.context and "Kestrel" not in page2.text


def test_research_split_by_section():
    body = "## Page 1\n### Summary\nShort summary.\n\n### Rates\nRates text."
    chunks = chunk_document({"type": "research", "title": "R"}, body, None)
    assert [c.section for c in chunks] == ["Summary", "Rates"]
    assert len({c.chunk_id("RS-X") for c in chunks}) == 2  # ids stay unique


# ---------------------------------------------------------------- on the real data pack
@pytest.fixture(scope="module")
def conn(tmp_path_factory):
    generate()
    path = tmp_path_factory.mktemp("wh") / "test.db"
    build_warehouse(db_path=path)
    c = db.connect(path, readonly=True)
    yield c
    c.close()


@pytest.fixture(scope="module")
def idx(conn):
    return DocIndex.load(conn)


def test_no_chunk_exceeds_size_limit(conn):
    # transcripts are checked separately: their text also carries '[mm:ss] Speaker:' labels
    for (text,) in conn.execute("SELECT c.text FROM chunks c JOIN documents d USING(doc_id) WHERE d.type != 'transcript'"):
        assert len(text.split()) <= config.CHUNK_MAX_WORDS


def test_signoff_rule_keeps_sentences_that_start_with_thanks():
    assert clean_email("Daniel,\n\nThank you for the update. I still want the report.\n\nMaria") == \
        "Thank you for the update. I still want the report.\n\nMaria"
    assert clean_email("Hi Daniel,\n\nThanks for Wednesday. Please send pricing.\n\nBest,\nTom") == \
        "Thanks for Wednesday. Please send pricing."


def test_long_research_page_was_split(conn):
    parts = conn.execute("SELECT chunk_id FROM chunks WHERE doc_id='RS-9001' AND page=2").fetchall()
    assert len(parts) >= 2


def test_email_chunks_have_no_greeting(conn):
    for (text,) in conn.execute("SELECT c.text FROM chunks c JOIN documents d USING(doc_id) WHERE d.type='email'"):
        assert not text.lower().startswith(("hi ", "hello", "dear"))


def _client(conn, name):
    return conn.execute("SELECT client_id FROM clients WHERE legal_name=?", (name,)).fetchone()[0]


def test_renewal_still_found_among_more_documents(conn, idx):
    hits = idx.search("when does the banking agreement renew", client_id=_client(conn, "Kestrel Foods Ltd"), k=5)
    assert {"BR-1001", "EM-1002"} <= {h.doc_id for h in hits}


def test_lookalike_renewal_never_leaks(conn, idx):
    # Kestrel Fuels also mentions a March renewal (EM-6001); it must not reach a Kestrel Foods search.
    hits = idx.search("renewal in March", client_id=_client(conn, "Kestrel Foods Ltd"), k=20)
    assert "EM-6001" not in {h.doc_id for h in hits}


def test_unhappy_client_found_by_meaning(conn, idx):
    hits = idx.search("Is the client unhappy with us?", client_id=_client(conn, "Halden Medical Group"), k=3)
    assert "EM-2001" in {h.doc_id for h in hits}


def test_long_docs_add_no_risky_content():
    from app.data_gen.docs_long import LONG_DOCS
    from app.security.injection import find_injection
    assert all(not find_injection(d["body"]) for d in LONG_DOCS)
    assert all(d["sensitivity"] == "normal" for d in LONG_DOCS)


# ---------------------------------------------------------------- email threads
def test_thread_split_into_messages_without_quotes_or_disclaimers(conn):
    rows = conn.execute("SELECT page, section, text FROM chunks WHERE doc_id='TH-2001' ORDER BY page").fetchall()
    assert [r["page"] for r in rows] == [2, 3, 4, 5]          # message 1 skipped: it is EM-2001 again
    assert rows[0]["section"].startswith("Message 2 · Daniel Okafor · 2026-10-29")
    for r in rows:
        assert "wrote:" not in r["text"] and not any(l.startswith(">") for l in r["text"].splitlines())
        assert "confidential and intended solely" not in r["text"]


def test_each_email_message_indexed_once(conn):
    # the payroll complaint exists in EM-2001, EM-2001-COPY and TH-2001 message 1: exactly one chunk
    n = conn.execute("SELECT COUNT(*) FROM chunks WHERE text LIKE '%Our payroll file was rejected twice%'").fetchone()[0]
    assert n == 1


def test_thread_only_ask_is_searchable(conn, idx):
    hits = idx.search("compensation for staff paid late", client_id=_client(conn, "Halden Medical Group"), k=3)
    assert hits[0].chunk_id == "TH-2001#p5"


# ---------------------------------------------------------------- transcripts
def test_transcript_chunked_by_speaker_turns_with_overlap(conn):
    rows = conn.execute("SELECT section, text FROM chunks WHERE doc_id='TR-1001' ORDER BY page").fetchall()
    assert len(rows) >= 3
    for r in rows:
        assert len(r["text"].split()) <= config.CHUNK_MAX_WORDS + 40   # word count includes '[mm:ss] Name:' labels
        assert r["text"].startswith("[")                           # starts on a turn boundary
    first_last_turn = rows[0]["text"].splitlines()[-1]
    assert rows[1]["text"].splitlines()[0] == first_last_turn       # one-turn overlap


def test_transcript_promise_found_with_speaker_and_time(conn, idx):
    # Either the moment of the promise (02:35) or Daniel's recap (04:12) is a correct, citable answer.
    hits = idx.search("when did we promise to send FX pricing", client_id=_client(conn, "Kestrel Foods Ltd"),
                      doc_types={"transcript"}, k=1)
    assert hits and ("[02:35] Daniel Okafor" in hits[0].text or "[04:12] Daniel Okafor" in hits[0].text)


# ---------------------------------------------------------------- syndicated news
def test_same_story_grouped_and_conflict_flagged(conn):
    kestrel = conn.execute("SELECT doc_ids, conflict FROM news_stories WHERE story_id='NW-1001'").fetchone()
    assert set(kestrel["doc_ids"].split(",")) == {"NW-1001", "NW-1003", "NW-1004"}
    assert "40000" in kestrel["conflict"] and "45000" in kestrel["conflict"]
    halden = conn.execute("SELECT doc_ids, conflict FROM news_stories WHERE story_id='NW-2001'").fetchone()
    assert set(halden["doc_ids"].split(",")) == {"NW-2001", "NW-2002"} and halden["conflict"] is None


def test_lookalike_news_not_grouped(conn):
    fuels = conn.execute("SELECT story_id FROM documents WHERE doc_id='NW-1002'").fetchone()[0]
    assert fuels == "NW-1002"   # its own story, not merged into Kestrel Foods' Rotterdam story


def test_search_returns_a_story_once_with_other_sources(conn, idx):
    hits = idx.search("Rotterdam distribution centre", client_id=_client(conn, "Kestrel Foods Ltd"),
                      doc_types={"news"}, k=5)
    rotterdam = [h for h in hits if h.doc_id in {"NW-1001", "NW-1003", "NW-1004"}]
    assert len(rotterdam) == 1 and len(rotterdam[0].also_reported_by) == 2


def test_general_research_reachable_when_asked(conn, idx):
    hits = idx.search("hedging programme for exporters", client_id=_client(conn, "Kestrel Foods Ltd"),
                      include_general=True, k=6)
    assert {"RS-1001", "RS-9001"} & {h.doc_id for h in hits}
