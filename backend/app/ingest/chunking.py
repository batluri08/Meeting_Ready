"""Chunking: how each kind of document is cut into searchable pieces.

Rules per document type
  email     quoted replies, greeting, sign-off, signature and legal disclaimer removed; one chunk
  thread    an email thread is split into its messages, each cleaned as above; a message already
            indexed elsewhere (e.g. the same email stored on its own) is skipped
  transcript speaker turns grouped into ~CHUNK_MAX_WORDS windows, overlapping by one turn;
            each chunk keeps its time range and speakers ('00:42–02:35 · Tom Reyes, Ana Duarte')
  news      one chunk (short, self-contained); the same story from several outlets is grouped later
  note      split by '## Page N'; long pages split further
  briefing  split by '## Page N'; long pages split further
  research  split by '## Page N', then by '### Section'; long sections split further

Every chunk also gets a short context header (type | client | date | title) that is embedded and
keyword-indexed with it, so a chunk like "Tom asked for FX pricing" still carries "Kestrel Foods".
The header is not shown as the quote; `text` stays the original words for citation.

Long pieces are split at sentence boundaries to at most CHUNK_MAX_WORDS words, repeating the last
sentence of one part at the start of the next (overlap) so a fact on the boundary is not lost.

Structured tables are never chunked: numbers are read with SQL, not by similarity search.
"""
import re
from dataclasses import dataclass

from app import config

# Greeting: "Hi Priya," / "Dear Maria, dear Owen," / a bare name line such as "Daniel,"
GREETING = re.compile(r"^((hi|hello|dear|hey|good (morning|afternoon))\b[^\n]*|[A-Z][a-z]+( [A-Z][a-z]+)?),\s*$",
                      re.IGNORECASE)
# Sign-off: only a short line on its own ("Thanks,", "Kind regards,"), never a sentence like
# "Thank you for the update. I still want the report..." which carries content.
SIGNOFF = re.compile(r"^(thanks|thank you|best|regards|kind regards|best regards|cheers|many thanks)"
                     r"( again| so much)?[,.!]?\s*$", re.IGNORECASE)


QUOTE_INTRO = re.compile(r"^On .{4,80} wrote:\s*$")
DISCLAIMER = re.compile(r"this email and any attachments are confidential", re.IGNORECASE)
MESSAGE_SPLIT = re.compile(r"^=== Message (\d+) ===\s*$", re.MULTILINE)
TURN = re.compile(r"^\[(\d{2}:\d{2})\]\s*([^:]+):\s*(.+)$")


@dataclass
class Chunk:
    page: int          # page; message number (threads); segment number (transcripts)
    part: int          # 1 unless a long page/section was split
    section: str       # research heading, 'Message 2 · Daniel Okafor · 2026-10-29', or '00:00–02:08 · speakers'
    text: str          # original words (what citations quote)
    context: str       # header + text (what is embedded and keyword-indexed)
    dedupe_key: str = ""   # emails only: fingerprint of the cleaned message, so a message is indexed once

    def chunk_id(self, doc_id: str) -> str:
        return f"{doc_id}#p{self.page}" + (f".{self.part}" if self.part > 1 else "")


def message_key(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def clean_email(body: str) -> str:
    """Drop quoted replies, the greeting line, and everything from the sign-off down (signature, disclaimer)."""
    lines = []
    for line in body.strip().splitlines():
        s = line.strip()
        if s.startswith(">") or QUOTE_INTRO.match(s):
            continue                      # quoted earlier message: it is indexed where it was first sent
        if DISCLAIMER.search(s):
            break                         # legal footer: nothing useful below it
        lines.append(line)
    while lines and not lines[0].strip():
        lines.pop(0)
    if lines and GREETING.match(lines[0].strip()):
        lines = lines[1:]
    for i, line in enumerate(lines):
        if SIGNOFF.match(line.strip()):
            lines = lines[:i]
            break
    return "\n".join(lines).strip()


def split_thread(body: str) -> list[dict]:
    """Split an email thread into its messages: [{n, from, date, text}]."""
    parts = MESSAGE_SPLIT.split(body)
    messages = []
    for i in range(1, len(parts), 2):
        block = parts[i + 1].strip()
        head, _, text = block.partition("\n\n")
        fields = dict(line.split(":", 1) for line in head.splitlines() if ":" in line)
        sender = re.sub(r"\s*<.*?>", "", fields.get("From", "")).strip()
        messages.append({"n": int(parts[i]), "from": sender, "date": fields.get("Date", "").strip(), "text": text})
    return messages


def split_transcript(body: str, max_words: int | None = None) -> list[tuple[str, str]]:
    """Group speaker turns into ~max_words windows, repeating the last turn of one window at the start of the
    next (overlap). Returns [(section label, text)]; text keeps '[mm:ss] Speaker: ...' lines."""
    max_words = max_words or config.CHUNK_MAX_WORDS
    turns = [m.groups() for line in body.strip().splitlines() if (m := TURN.match(line.strip()))]
    windows, current = [], []

    def words(ts):
        return sum(len(t[2].split()) for t in ts)

    for turn in turns:
        if current and words(current + [turn]) > max_words:
            windows.append(current)
            current = [current[-1]]       # overlap: carry the last turn forward
        current.append(turn)
    if current:
        windows.append(current)

    out = []
    for w in windows:
        speakers = ", ".join(dict.fromkeys(t[1] for t in w))
        label = f"{w[0][0]}–{w[-1][0]} · {speakers}"
        out.append((label, "\n".join(f"[{t[0]}] {t[1]}: {t[2]}" for t in w)))
    return out


def _pages(body: str) -> list[tuple[int, str]]:
    parts = re.split(r"^## Page (\d+)\s*$", body, flags=re.MULTILINE)
    if len(parts) == 1:
        return [(1, body.strip())]
    return [(int(parts[i]), parts[i + 1].strip()) for i in range(1, len(parts), 2) if parts[i + 1].strip()]


def _sections(text: str) -> list[tuple[str, str]]:
    parts = re.split(r"^### (.+?)\s*$", text, flags=re.MULTILINE)
    out = []
    if parts[0].strip():
        out.append(("", parts[0].strip()))
    for i in range(1, len(parts), 2):
        if parts[i + 1].strip():
            out.append((parts[i].strip(), parts[i + 1].strip()))
    return out


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", text).strip()) if s]


def split_by_size(text: str, max_words: int | None = None) -> list[str]:
    """Split at sentence boundaries into parts of <= max_words, with a one-sentence overlap."""
    max_words = max_words or config.CHUNK_MAX_WORDS
    if len(text.split()) <= max_words:
        return [text]
    parts, current = [], []
    for sent in _sentences(text):
        if current and len(" ".join(current + [sent]).split()) > max_words:
            parts.append(" ".join(current))
            current = [current[-1]]          # overlap: carry the last sentence forward
        current.append(sent)
    if current:
        parts.append(" ".join(current))
    return parts


def chunk_document(meta: dict, body: str, client_name: str | None) -> list[Chunk]:
    doc_type = meta.get("type", "")
    title = meta.get("subject") or meta.get("title") or ""
    header = f"[{doc_type} | {client_name or 'general'} | {meta.get('date', '')} | {title}]"

    if doc_type == "email" and MESSAGE_SPLIT.search(body):
        chunks = []
        for m in split_thread(body):
            text = clean_email(m["text"])
            if not text:
                continue
            section = f"Message {m['n']} · {m['from']} · {m['date']}"
            chunks.append(Chunk(m["n"], 1, section, text, f"{header} {section}. {text}", message_key(text)))
        return chunks
    if doc_type == "email":
        text = clean_email(body)
        return [Chunk(1, 1, "", text, f"{header} {text}", message_key(text))]
    if doc_type == "transcript":
        return [Chunk(i, 1, label, text, f"{header} {label}. {text}")
                for i, (label, text) in enumerate(split_transcript(body), start=1)]
    if doc_type == "news":
        pieces = [(1, "", body.strip())]
    elif doc_type == "research":
        pieces = [(page, sec, txt) for page, ptxt in _pages(body) for sec, txt in _sections(ptxt)]
    else:  # note, briefing
        pieces = [(page, "", txt) for page, txt in _pages(body)]

    chunks: list[Chunk] = []
    for page, section, text in pieces:
        # number parts within a page, so a split section keeps a stable id
        start = 1 + sum(1 for c in chunks if c.page == page)
        for n, part in enumerate(split_by_size(text), start=start):
            sec_txt = f" {section}." if section else ""
            chunks.append(Chunk(page, n, section, part, f"{header}{sec_txt} {part}"))
    return chunks
