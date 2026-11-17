"""Evidence items: the only things a briefing statement may be based on.

Every agent returns Evidence. Each item gets a short id (E1, E2, ...) that statements must cite, and a
`source` that the evidence drawer shows: the SQL query + rows, or the document, page/message/time and quote.
"""
import re
import threading
from dataclasses import asdict, dataclass, field

NUMBER = re.compile(r"(?<![\w.])-?\d[\d,]*(?:\.\d+)?")
ISO_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
MONTH = ["", "January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
         "November", "December"]


def statement_text(st: dict) -> str:
    """A briefing statement as one string: its short bold label (if any) and its text. Everything that checks
    or exports statements uses this, so a number in a label is verified like any other."""
    label = (st.get("label") or "").strip()
    return f"{label}: {st.get('text', '')}" if label else st.get("text", "")


def numbers_in(text: str) -> set[float]:
    """All numbers in a text as floats: '397,320' -> 397320.0, '12.0%' -> 12.0, '-12' -> 12.0 (sign ignored)."""
    out = set()
    for m in NUMBER.findall(text or ""):
        try:
            out.add(abs(float(m.replace(",", ""))))
        except ValueError:
            pass
    return out


def date_words(text: str) -> str:
    """'2026-11-01' -> adds '1 November 2026' so a writer may say the date in words."""
    return " ".join(f"{int(d)} {MONTH[int(m)]} {y}" for y, m, d in ISO_DATE.findall(text or ""))


@dataclass
class Evidence:
    id: str
    kind: str            # profile | signal | change | action | deal | holding | doc | claim | news | opportunity
    title: str           # short label for the drawer, e.g. "Revenue Q3 vs Q2"
    text: str            # the fact in words; statements may only use numbers that appear here
    source: dict         # {"type": "sql", query, params, rows, refs} | {"type": "doc", doc_id, chunk_id, ...}
    restricted: bool = False

    def allowed_numbers(self) -> set[float]:
        """Numbers a statement citing this evidence may contain: those in the fact itself, its dates (also in
        words), and the identifiers of its source (e.g. 'TR-1001', a page number), which are part of the citation."""
        cite = " ".join(str(self.source.get(k, "")) for k in ("date", "doc_id", "chunk_id", "page", "record_id"))
        return numbers_in(self.text) | numbers_in(date_words(self.text)) | numbers_in(cite) | numbers_in(date_words(cite))

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class EvidenceStore:
    items: dict[str, Evidence] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def add(self, kind: str, title: str, text: str, source: dict, restricted: bool = False) -> Evidence:
        with self._lock:
            ev = Evidence(f"E{len(self.items) + 1}", kind, title, text, source, restricted)
            self.items[ev.id] = ev
            return ev

    def get(self, eid: str) -> Evidence | None:
        return self.items.get(eid)

    def for_prompt(self, ids: list[str]) -> str:
        """Evidence listed for the model: one line per item, id first."""
        lines = []
        for eid in ids:
            ev = self.items[eid]
            where = ev.source.get("doc_id") or ", ".join(ev.source.get("refs", [])) or ev.kind
            when = ev.source.get("date", "")
            body = f"<untrusted_document>{ev.text}</untrusted_document>" if ev.source.get("type") == "doc" else ev.text
            lines.append(f"[{eid}] ({ev.kind}; {where}{'; ' + when if when else ''}) {body}")
        return "\n".join(lines)


def sql_source(sql_ev) -> dict:
    """Turn a metrics.evidence.SqlEvidence into an Evidence.source."""
    return {"type": "sql", "query": sql_ev.query, "params": list(sql_ev.params), "rows": sql_ev.rows,
            "refs": sql_ev.source_refs}


def doc_source(row: dict) -> dict:
    """A chunk row (chunk_id, doc_id, page, section, date, text, ...) -> Evidence.source."""
    return {"type": "doc", "doc_id": row["doc_id"], "chunk_id": row["chunk_id"], "page": row.get("page"),
            "section": row.get("section"), "date": row.get("date"), "doc_type": row.get("doc_type"),
            "title": row.get("title"), "quote": row["text"]}
