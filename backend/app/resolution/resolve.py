"""Build the customer master: one client_id per real company, plus a crosswalk for every source account.

CRM accounts are processed first (oldest ID first). A CRM account that matches an existing client
is merged into it (this catches the same company entered twice); otherwise it founds a new client.
Billing accounts are then matched against that master: merged, sent to review, or left unmatched.
"""
from dataclasses import dataclass, field

from app.resolution.matcher import Match, normalize_domain, score


@dataclass
class Client:
    client_id: str
    legal_name: str
    domains: set[str]
    attrs: dict                       # industry, region, segment, tier, client_since (from the founding CRM row)
    source_ids: list[str] = field(default_factory=list)


@dataclass
class XrefRow:
    source_system: str
    source_id: str
    source_name: str
    source_domain: str
    client_id: str | None
    candidate_client_id: str | None
    match_method: str
    confidence: float
    status: str                       # master | merged | review | unmatched
    reason: str


def _best(name: str, domain: str, clients: list[Client]) -> tuple[Client | None, Match | None]:
    best_c, best_m = None, None
    for c in clients:
        m = score(name, domain, c.legal_name, c.domains)
        if best_m is None or m.confidence > best_m.confidence:
            best_c, best_m = c, m
    return best_c, best_m


def resolve_accounts(crm_rows: list[dict], billing_rows: list[dict]) -> tuple[list[Client], list[XrefRow]]:
    clients: list[Client] = []
    xref: list[XrefRow] = []

    for row in sorted(crm_rows, key=lambda r: r["account_id"]):
        name, domain = row["name"], normalize_domain(row["domain"])
        cand, m = _best(name, domain, clients)
        if cand and m.decision == "merge":
            cand.source_ids.append(row["account_id"])
            if domain:
                cand.domains.add(domain)
            xref.append(XrefRow("crm", row["account_id"], name, domain, cand.client_id, cand.client_id,
                                m.method, m.confidence, "merged", m.reason))
            continue
        client = Client(
            client_id=f"CLT-{len(clients) + 1:03d}",
            legal_name=name,
            domains={domain} if domain else set(),
            attrs={k: row[k] for k in ("industry", "region", "segment", "tier", "client_since")},
            source_ids=[row["account_id"]],
        )
        clients.append(client)
        reason = "First CRM record for this company; founds the client."
        if cand and m.decision == "review":
            reason += f" Possible match to {cand.client_id} ({m.reason})"
        xref.append(XrefRow("crm", row["account_id"], name, domain, client.client_id, None,
                            "master", 1.0, "master", reason))

    for row in sorted(billing_rows, key=lambda r: r["billing_id"]):
        name, domain = row["legal_name"], normalize_domain(row["bill_to_domain"])
        cand, m = _best(name, domain, clients)
        if cand is None:
            xref.append(XrefRow("billing", row["billing_id"], name, domain, None, None,
                                "none", 0.0, "unmatched", "No clients to match against."))
            continue
        status = {"merge": "merged", "review": "review", "no_match": "unmatched"}[m.decision]
        client_id = cand.client_id if status == "merged" else None
        if status == "merged":
            cand.source_ids.append(row["billing_id"])
        xref.append(XrefRow("billing", row["billing_id"], name, domain, client_id, cand.client_id,
                            m.method, m.confidence, status, m.reason))

    return clients, xref
