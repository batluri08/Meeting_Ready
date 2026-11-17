"""Write the synthetic data pack to disk.

Run:  uv run python -m app.data_gen.generate

Outputs (all deterministic, safe to re-run):
  data/raw/*.csv            one file per source-system table (messy, source IDs)
  data/docs/*.md            emails, notes, briefings, research, news with a metadata header
  data/trap_manifest.json   planted traps + material signals (the answer key)
"""
import csv
import json
import random
import shutil

from app import config
from app.data_gen import world
from app.data_gen.docs import DOCS as CORE_DOCS
from app.data_gen.docs_extra import EXTRA_DOCS
from app.data_gen.docs_long import LONG_DOCS

DOCS = CORE_DOCS + EXTRA_DOCS + LONG_DOCS
from app.data_gen.traps import MATERIAL_SIGNALS, TRAPS

# Small month-to-month noise for background accounts only; hero trends stay exact.
NOISE_ACCOUNTS = {"BIL-7004", "BIL-7005", "BIL-7006", "BIL-7007", "BIL-7008", "BIL-7014"}
SEED = 20261116


def _write_csv(name: str, header: list[str], rows: list[tuple]) -> None:
    path = config.RAW_DIR / f"{name}.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def _revenue_rows() -> list[tuple]:
    rng = random.Random(SEED)
    rows = []
    for billing_id, products in world.REVENUE_BASE.items():
        shift = world.REVENUE_SHIFT.get(billing_id, 1.0)
        for month in world.MONTHS:
            for product, base in products.items():
                value = base * (shift if month >= world.REVENUE_SHIFT_FROM else 1.0)
                if billing_id in NOISE_ACCOUNTS:
                    value *= 1 + rng.uniform(-0.03, 0.03)
                rows.append((billing_id, month, product, round(value)))
    return rows


def _performance_rows() -> list[tuple]:
    rows = []
    metrics = ("payments_processed", "stp_rate_pct", "avg_balance_gbp")
    for account_id, base in world.PERFORMANCE_BASE.items():
        for month in world.PERFORMANCE_MONTHS:
            for metric, value in zip(metrics, base):
                if month >= world.REVENUE_SHIFT_FROM:
                    value = value * world.PERFORMANCE_SHIFT.get((account_id, metric), 1.0)
                value = world.PERFORMANCE_OVERRIDES.get((account_id, month, metric), value)
                rows.append((account_id, month, metric, round(value, 1) if metric == "stp_rate_pct" else round(value)))
    return rows


def _relationship_rows() -> list[tuple]:
    rows = []
    for account_id, (wallet, satisfaction, primary) in world.RELATIONSHIP_METRICS.items():
        for i, as_of in enumerate(world.RELATIONSHIP_DATES):
            rows.append((account_id, as_of, wallet[i], satisfaction[i], primary))
    return rows


def _doc_markdown(doc: dict) -> str:
    header_keys = ["id", "type", "date", "account_id", "from", "to", "subject", "title", "source", "sensitivity"]
    lines = ["---"]
    for key in header_keys:
        if key in doc:
            lines.append(f"{key}: {doc[key]}")
    lines.append("---")
    return "\n".join(lines) + "\n" + doc["body"].strip() + "\n"


def generate() -> dict:
    # Start clean so removed records do not linger.
    for d in (config.RAW_DIR, config.DOCS_DIR):
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)

    _write_csv("users", ["user_id", "name", "team", "clearance"], world.USERS)
    _write_csv("products", ["product_code", "name", "family"], world.PRODUCTS)
    _write_csv("crm_accounts", ["account_id", "name", "domain", "industry", "region", "segment", "tier", "client_since"], world.CRM_ACCOUNTS)
    _write_csv("billing_accounts", ["billing_id", "legal_name", "bill_to_domain", "country"], world.BILLING_ACCOUNTS)
    _write_csv("coverage", ["account_id", "user_id", "role", "start_date"], world.COVERAGE)
    _write_csv("contacts", ["contact_id", "account_id", "name", "email", "title", "role", "updated_at"], world.CONTACTS)
    _write_csv("holdings", ["account_id", "product_code", "status", "opened_on", "utilization_pct"], world.HOLDINGS)
    revenue = _revenue_rows()
    _write_csv("revenue_monthly", ["billing_id", "month", "product_code", "revenue"], revenue)
    _write_csv("performance_monthly", ["account_id", "month", "metric", "value"], _performance_rows())
    _write_csv("relationship_metrics", ["account_id", "as_of", "wallet_share_pct", "satisfaction_score", "primary_bank"], _relationship_rows())
    _write_csv("pipeline", ["opp_id", "account_id", "product_code", "stage", "value", "expected_close", "updated_at", "restricted"], world.PIPELINE)
    _write_csv("service_issues", ["issue_id", "account_id", "opened_at", "closed_at", "severity", "status", "summary"], world.SERVICE_ISSUES)
    _write_csv("open_actions", ["action_id", "account_id", "owner_user", "description", "due_date", "status", "source_ref"], world.OPEN_ACTIONS)
    _write_csv("interactions", ["interaction_id", "account_id", "date", "type", "summary_doc_id"], world.INTERACTIONS)
    _write_csv("meetings", ["meeting_id", "account_id", "start_time", "title", "attendees"], world.MEETINGS)

    for doc in DOCS:
        (config.DOCS_DIR / f"{doc['id']}.md").write_text(_doc_markdown(doc), encoding="utf-8")

    manifest = {"demo_date": config.TODAY.isoformat(), "traps": TRAPS, "material_signals": MATERIAL_SIGNALS}
    (config.DATA_DIR / "trap_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    return {
        "raw_tables": len(list(config.RAW_DIR.glob("*.csv"))),
        "revenue_rows": len(revenue),
        "docs": len(DOCS),
        "traps": len(TRAPS),
    }


if __name__ == "__main__":
    print(generate())
