"""Ingestion: load the mock source systems into the clean SQLite warehouse.

Run:  uv run python -m app.ingest.run

Steps
  1. Read every source table and document through its connector.
  2. Entity resolution builds the client master + crosswalk (client_xref).
  3. Every source row is re-keyed from its system ID to client_id (rows whose account is unresolved
     keep client_id NULL and stay out of briefings).
  4. Contacts are de-duplicated by email; documents by content hash.
  5. Documents without an account ID are matched by sender email domain.
  6. Documents are split into page chunks for the search index; injection attempts are flagged.
  7. Each chunk is embedded (local model) and stored for the vector database.
  8. News items telling the same story from different outlets are grouped; differing figures are flagged.

The warehouse is rebuilt from scratch on every run, so re-running is idempotent.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from app import config
from app.ingest.chunking import chunk_document
from app.ingest.loaders import content_hash, read_docs, read_table, sender_domain
from app.ingest.news import group_news_stories
from app.resolution.resolve import resolve_accounts
from app.security.injection import find_injection
from app.stores import db
from app.stores.embeddings import embed_passages
from app.stores.embeddings import model_name as embedding_model_name


def build_warehouse(db_path: Path | None = None, raw_dir: Path | None = None, docs_dir: Path | None = None) -> dict:
    db_path = Path(db_path or config.DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    conn = db.connect(db_path)
    db.create_schema(conn)

    t = lambda name: read_table(name, raw_dir)  # noqa: E731

    # ---- 1-2. client master
    clients, xref = resolve_accounts(t("crm_accounts"), t("billing_accounts"))
    conn.executemany(
        "INSERT INTO clients VALUES (?,?,?,?,?,?,?,?)",
        [(c.client_id, c.legal_name, sorted(c.domains)[0] if c.domains else None,
          c.attrs["industry"], c.attrs["region"], c.attrs["segment"], c.attrs["tier"], c.attrs["client_since"])
         for c in clients],
    )
    conn.executemany(
        "INSERT INTO client_xref VALUES (?,?,?,?,?,?,?,?,?,?)",
        [(x.source_system, x.source_id, x.source_name, x.source_domain, x.client_id, x.candidate_client_id,
          x.match_method, x.confidence, x.status, x.reason) for x in xref],
    )
    crm_to_client = {x.source_id: x.client_id for x in xref if x.source_system == "crm"}
    billing_to_client = {x.source_id: x.client_id for x in xref if x.source_system == "billing"}
    domain_to_client = {d: c.client_id for c in clients for d in c.domains}

    def cid(account_id: str) -> str:
        return crm_to_client[account_id]

    # ---- 3. re-key structured tables
    conn.executemany("INSERT INTO users VALUES (?,?,?,?)",
                     [(r["user_id"], r["name"], r["team"], r["clearance"]) for r in t("users")])
    conn.executemany("INSERT INTO products VALUES (?,?,?)",
                     [(r["product_code"], r["name"], r["family"]) for r in t("products")])
    conn.executemany("INSERT INTO coverage VALUES (?,?,?,?,?)",
                     [(cid(r["account_id"]), r["user_id"], r["role"], r["start_date"], f"crm:{r['account_id']}")
                      for r in t("coverage")])
    conn.executemany("INSERT INTO holdings VALUES (?,?,?,?,?,?)",
                     [(cid(r["account_id"]), r["product_code"], r["status"], r["opened_on"],
                       int(r["utilization_pct"]), f"crm:{r['account_id']}") for r in t("holdings")])
    conn.executemany("INSERT INTO revenue_monthly VALUES (?,?,?,?,?)",
                     [(billing_to_client.get(r["billing_id"]), r["month"], r["product_code"], int(r["revenue"]),
                       f"billing:{r['billing_id']}") for r in t("revenue_monthly")])
    conn.executemany("INSERT INTO performance_monthly VALUES (?,?,?,?,?)",
                     [(cid(r["account_id"]), r["month"], r["metric"], float(r["value"]), f"ops:{r['account_id']}")
                      for r in t("performance_monthly")])
    conn.executemany("INSERT INTO relationship_metrics VALUES (?,?,?,?,?,?)",
                     [(cid(r["account_id"]), r["as_of"], int(r["wallet_share_pct"]), float(r["satisfaction_score"]),
                       int(r["primary_bank"]), f"rel:{r['account_id']}") for r in t("relationship_metrics")])
    conn.executemany("INSERT INTO pipeline VALUES (?,?,?,?,?,?,?,?,?)",
                     [(r["opp_id"], cid(r["account_id"]), r["product_code"], r["stage"], int(r["value"]),
                       r["expected_close"], r["updated_at"], int(r["restricted"]), f"crm:{r['account_id']}")
                      for r in t("pipeline")])
    conn.executemany("INSERT INTO service_issues VALUES (?,?,?,?,?,?,?,?)",
                     [(r["issue_id"], cid(r["account_id"]), r["opened_at"], r["closed_at"] or None,
                       int(r["severity"]), r["status"], r["summary"], f"crm:{r['account_id']}")
                      for r in t("service_issues")])
    conn.executemany("INSERT INTO open_actions VALUES (?,?,?,?,?,?,?,?)",
                     [(r["action_id"], cid(r["account_id"]), r["owner_user"], r["description"], r["due_date"],
                       r["status"], r["source_ref"], f"crm:{r['account_id']}") for r in t("open_actions")])
    conn.executemany("INSERT INTO interactions VALUES (?,?,?,?,?,?)",
                     [(r["interaction_id"], cid(r["account_id"]), r["date"], r["type"], r["summary_doc_id"] or None,
                       f"crm:{r['account_id']}") for r in t("interactions")])
    conn.executemany("INSERT INTO meetings VALUES (?,?,?,?,?,?)",
                     [(r["meeting_id"], cid(r["account_id"]), r["start_time"], r["title"], r["attendees"],
                       f"calendar:{r['meeting_id']}") for r in t("meetings")])

    # ---- 4a. contacts: same person = same email (case-insensitive) within one client.
    # Keep the record from the client's founding CRM account; otherwise the most recently updated.
    contacts = t("contacts")
    founding = {x.client_id: x.source_id for x in xref if x.status == "master"}
    groups: dict[tuple, list[dict]] = {}
    for r in contacts:
        groups.setdefault((cid(r["account_id"]), r["email"].strip().lower()), []).append(r)
    contact_rows, dup_contacts = [], 0
    for (client_id, _), rows in groups.items():
        rows.sort(key=lambda r: (r["account_id"] != founding[client_id], -int(r["updated_at"].replace("-", ""))))
        keep = rows[0]
        for r in rows:
            dup_of = None if r is keep else keep["contact_id"]
            dup_contacts += dup_of is not None
            contact_rows.append((r["contact_id"], client_id, r["name"], r["email"], r["title"], r["role"],
                                 r["updated_at"], dup_of, f"crm:{r['account_id']}"))
    # Insert originals before duplicates so the self-reference resolves.
    contact_rows.sort(key=lambda r: r[7] is not None)
    conn.executemany("INSERT INTO contacts VALUES (?,?,?,?,?,?,?,?,?)", contact_rows)

    # ---- 4b-6. documents
    client_names = {c.client_id: c.legal_name for c in clients}
    seen_hash: dict[str, str] = {}
    seen_messages: dict[str, str] = {}
    stats = {"docs": 0, "duplicate_docs": 0, "duplicate_messages": 0, "matched_by_domain": 0,
             "unassigned_docs": 0, "injection_flags": 0, "chunks": 0, "restricted_docs": 0}
    injection_log = []
    for meta, body in read_docs(docs_dir):
        doc_id = meta["id"]
        account_id = meta.get("account_id", "")
        if account_id:
            client_id, method, conf = cid(account_id), "account_id", 1.0
        elif (dom := sender_domain(meta.get("from", ""))) and dom in domain_to_client:
            client_id, method, conf = domain_to_client[dom], "email_domain", 0.90
            stats["matched_by_domain"] += 1
        else:
            client_id, method, conf = None, "none", None
            stats["unassigned_docs"] += 1

        h = content_hash(meta, body)
        dup_of = seen_hash.get(h)
        if dup_of:
            stats["duplicate_docs"] += 1
        else:
            seen_hash[h] = doc_id

        restricted = int(meta.get("sensitivity") == "restricted")
        hits = find_injection(body)
        if hits:
            stats["injection_flags"] += 1
            injection_log.append({"doc_id": doc_id, "phrases": hits})

        conn.execute(
            "INSERT INTO documents VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (doc_id, meta["type"], meta.get("date"), client_id, method, conf, meta.get("from"), meta.get("to"),
             meta.get("subject") or meta.get("title"), meta.get("source"), restricted, h, dup_of, int(bool(hits)),
             body, f"docs:{doc_id}", None),
        )
        stats["docs"] += 1
        stats["restricted_docs"] += restricted
        if dup_of:
            continue  # a duplicate is recorded but not indexed, so it is never cited twice
        for ch in chunk_document(meta, body, client_names.get(client_id)):
            if ch.dedupe_key:
                if ch.dedupe_key in seen_messages:
                    stats["duplicate_messages"] += 1   # same email already indexed (standalone or earlier thread)
                    continue
                seen_messages[ch.dedupe_key] = f"{doc_id}#p{ch.page}"
            conn.execute("INSERT INTO chunks VALUES (?,?,?,?,?,?,?,?,?)",
                         (ch.chunk_id(doc_id), doc_id, client_id, ch.page, ch.part, ch.section or None,
                          ch.text, ch.context, restricted))
            stats["chunks"] += 1

    # ---- 7. embeddings for the vector database (computed locally)
    chunk_rows = conn.execute("SELECT chunk_id, context FROM chunks ORDER BY chunk_id").fetchall()
    vectors = embed_passages([r["context"] for r in chunk_rows])
    conn.executemany(
        "INSERT INTO chunk_vectors VALUES (?,?,?,?)",
        [(r["chunk_id"], embedding_model_name(), len(v), v.tobytes()) for r, v in zip(chunk_rows, vectors)],
    )
    stats["embedded_chunks"] = len(vectors)

    # ---- 8. group the same news story from different outlets, and flag figures that disagree
    vec_by_chunk = {r["chunk_id"]: v for r, v in zip(chunk_rows, vectors)}
    stories = group_news_stories(conn, vec_by_chunk)
    stats["news_stories_grouped"] = len(stories)
    stats["news_conflicts"] = sum(1 for s in stories if s["conflict"])

    summary = {
        "clients": len(clients),
        "xref": {s: sum(1 for x in xref if x.status == s) for s in ("master", "merged", "review", "unmatched")},
        "contacts": len(contacts),
        "duplicate_contacts": dup_contacts,
        "unresolved_revenue_rows": conn.execute("SELECT COUNT(*) FROM revenue_monthly WHERE client_id IS NULL").fetchone()[0],
        **stats,
        "injection_log": injection_log,
    }
    conn.execute("INSERT INTO ingest_runs VALUES (?,?)",
                 (datetime.now(timezone.utc).isoformat(timespec="seconds"), json.dumps(summary)))
    conn.commit()
    conn.close()
    return summary


if __name__ == "__main__":
    print(json.dumps(build_warehouse(), indent=2))
