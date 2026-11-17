"""Connectors for the mock source systems. Each returns plain dicts, the same shape a real API adapter would."""
import csv
import hashlib
import re
from pathlib import Path

from app import config


def read_table(name: str, raw_dir: Path | None = None) -> list[dict]:
    """Table connector: one CSV export per source table."""
    path = Path(raw_dir or config.RAW_DIR) / f"{name}.csv"
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def parse_doc(text: str) -> tuple[dict, str]:
    """Split a markdown doc into (header fields, body)."""
    _, header, body = text.split("---", 2)
    meta = {}
    for line in header.strip().splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    return meta, body.strip()


def read_docs(docs_dir: Path | None = None) -> list[tuple[dict, str]]:
    """Document connector: scan the docs folder. Sorted by ID so the original wins over a later copy."""
    paths = sorted(Path(docs_dir or config.DOCS_DIR).glob("*.md"), key=lambda p: p.stem)
    return [parse_doc(p.read_text(encoding="utf-8")) for p in paths]


def content_hash(meta: dict, body: str) -> str:
    """Fingerprint of what a document *says* (type, date, sender, body), ignoring its file name / ID,
    so the same email exported twice gets the same hash."""
    norm_body = re.sub(r"\s+", " ", body).strip().lower()
    key = "|".join([meta.get("type", ""), meta.get("date", ""), meta.get("from", "").lower(), norm_body])
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def sender_domain(sender: str) -> str:
    """'Sam Whitlow <procurement@kestrelfoods.com>' -> 'kestrelfoods.com'."""
    m = re.search(r"@([A-Za-z0-9.-]+)", sender or "")
    return m.group(1).lower() if m else ""
