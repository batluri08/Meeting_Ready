"""The synthetic world, written out by hand so every planted trap is deliberate.

Everything here is what the *source systems* hold: messy, keyed by each system's own IDs.
Ingestion + entity resolution (Phase 2) turn it into clean tables keyed by client_id.

Demo date is config.TODAY (2026-11-16). Three hero clients are fully written:
  Kestrel Foods (CRM-1001), Halden Medical (CRM-1002 + alias CRM-1012), Corvan Logistics (CRM-1003).
Five background clients fill out the book, including the look-alike Kestrel Fuels (CRM-1006).
"""

# ---------------------------------------------------------------- users (internal staff)
USERS = [
    # user_id, name, team, clearance
    ("U-ANA", "Priya Shah", "Coverage East", "analyst"),
    ("U-SEN", "Daniel Okafor", "Coverage East", "senior"),
    ("U-ANA2", "Leo Brandt", "Coverage West", "analyst"),
]

# ---------------------------------------------------------------- products
PRODUCTS = [
    # product_code, name, family
    ("CASH_MGMT", "Cash Management", "Transaction Banking"),
    ("TRADE_FIN", "Trade Finance", "Transaction Banking"),
    ("SUPPLY_FIN", "Supply Chain Finance", "Transaction Banking"),
    ("CARD", "Corporate Cards", "Transaction Banking"),
    ("PAYROLL", "Payroll Services", "Transaction Banking"),
    ("FX_HEDGE", "FX Hedging", "Markets"),
    ("TERM_LOAN", "Term Loan", "Lending"),
    ("ADVISORY", "M&A Advisory", "Advisory"),
]

# ---------------------------------------------------------------- CRM accounts (system 1)
CRM_ACCOUNTS = [
    # account_id, name, domain, industry, region, segment, tier, client_since
    ("CRM-1001", "Kestrel Foods Ltd", "kestrelfoods.com", "Food distribution", "UK & Europe", "Mid-market", "Gold", "2020-03-02"),
    ("CRM-1002", "Halden Medical Group", "haldenmedical.com", "Healthcare providers", "UK", "Large corporate", "Platinum", "2016-09-12"),
    ("CRM-1003", "Corvan Logistics", "corvanlogistics.com", "Logistics", "UK & Europe", "Mid-market", "Silver", "2022-01-17"),
    ("CRM-1004", "Larkspur Retail plc", "larkspurretail.co.uk", "Retail", "UK", "Large corporate", "Gold", "2018-05-21"),
    ("CRM-1005", "Meridian Textiles", "meridiantextiles.com", "Manufacturing", "South Asia", "Mid-market", "Silver", "2021-11-03"),
    ("CRM-1006", "Kestrel Fuels plc", "kestrelfuels.com", "Energy", "UK", "Large corporate", "Gold", "2019-02-11"),
    ("CRM-1007", "Pellow Engineering", "pellow-eng.com", "Engineering", "UK", "Mid-market", "Bronze", "2023-06-30"),
    ("CRM-1008", "Tamsin Software", "tamsinsoftware.io", "Software", "UK & Europe", "Emerging", "Bronze", "2024-08-19"),
    # TRAP alias: same company entered twice in CRM, different spelling, same domain.
    ("CRM-1012", "Halden Medical Grp.", "haldenmedical.com", "Healthcare", "UK", "Large corporate", "Platinum", "2016-09-12"),
]

# ---------------------------------------------------------------- Billing accounts (system 2)
BILLING_ACCOUNTS = [
    # billing_id, legal_name, bill_to_domain, country
    ("BIL-7001", "KESTREL FDS LTD", "kestrelfoods.com", "GB"),      # TRAP alias of Kestrel Foods
    ("BIL-7002", "Halden Medical Group Ltd", "haldenmedical.com", "GB"),
    ("BIL-7003", "Corvan Logistics Limited", "corvanlogistics.com", "GB"),
    ("BIL-7004", "Larkspur Retail PLC", "larkspurretail.co.uk", "GB"),
    ("BIL-7005", "Meridian Textiles Pvt Ltd", "meridiantextiles.com", "IN"),
    ("BIL-7006", "Kestrel Fuels PLC", "kestrelfuels.com", "GB"),    # TRAP look-alike: must NOT join Kestrel Foods
    ("BIL-7007", "Pellow Engineering Ltd", "pellow-eng.com", "GB"),
    ("BIL-7008", "Tamsin Software Ltd", "tamsinsoftware.io", "GB"),
    ("BIL-7014", "Larkspur Hldgs", "", "GB"),                       # TRAP low confidence: no domain -> review queue
]

# ---------------------------------------------------------------- Coverage
COVERAGE = [
    # account_id, user_id, role, start_date
    ("CRM-1001", "U-ANA", "Analyst", "2025-01-06"),
    ("CRM-1001", "U-SEN", "Relationship lead", "2020-03-02"),
    ("CRM-1002", "U-ANA", "Analyst", "2025-01-06"),
    ("CRM-1002", "U-SEN", "Relationship lead", "2019-04-01"),
    ("CRM-1003", "U-ANA", "Analyst", "2025-01-06"),
    ("CRM-1003", "U-SEN", "Relationship lead", "2022-01-17"),
    ("CRM-1004", "U-SEN", "Relationship lead", "2018-05-21"),
    ("CRM-1005", "U-ANA2", "Analyst", "2024-02-01"),
    ("CRM-1006", "U-ANA2", "Relationship lead", "2019-02-11"),
    ("CRM-1007", "U-ANA2", "Relationship lead", "2023-06-30"),
    ("CRM-1008", "U-ANA2", "Relationship lead", "2024-08-19"),
]

# ---------------------------------------------------------------- Contacts
CONTACTS = [
    # contact_id, account_id, name, email, title, role, updated_at
    ("C-101", "CRM-1001", "Tom Reyes", "t.reyes@kestrelfoods.com", "Chief Financial Officer", "Decision maker", "2026-02-10"),
    ("C-102", "CRM-1001", "Ana Duarte", "a.duarte@kestrelfoods.com", "Head of Treasury", "Day-to-day contact", "2025-11-20"),
    ("C-103", "CRM-1001", "Sam Whitlow", "procurement@kestrelfoods.com", "Procurement Manager", "Influencer", "2025-06-01"),
    # TRAP stale: a 2024 note says the CFO is J. Park; this 2026 row is newer and wins.
    ("C-201", "CRM-1002", "Maria Lopes", "maria.lopes@haldenmedical.com", "Chief Financial Officer", "Decision maker", "2026-03-01"),
    # TRAP duplicate: same person entered again under the alias account, different casing.
    ("C-209", "CRM-1012", "MARIA LOPES", "Maria.Lopes@HaldenMedical.com", "CFO", "Decision maker", "2026-03-04"),
    ("C-202", "CRM-1002", "Owen Pratt", "o.pratt@haldenmedical.com", "Group Treasurer", "Day-to-day contact", "2025-09-15"),
    ("C-203", "CRM-1002", "Jin Park", "j.park@haldenmedical.com", "Former CFO (left 2025)", "Inactive", "2025-12-31"),
    ("C-301", "CRM-1003", "Ruth Adeyemi", "r.adeyemi@corvanlogistics.com", "Finance Director", "Decision maker", "2026-01-12"),
    ("C-302", "CRM-1003", "Marek Nowak", "m.nowak@corvanlogistics.com", "Fleet Operations Lead", "User", "2025-10-03"),
    ("C-401", "CRM-1004", "Helen Ford", "h.ford@larkspurretail.co.uk", "Treasurer", "Decision maker", "2025-07-08"),
    ("C-501", "CRM-1005", "Arjun Mehta", "arjun@meridiantextiles.com", "CFO", "Decision maker", "2025-04-22"),
    ("C-601", "CRM-1006", "Gareth Lloyd", "g.lloyd@kestrelfuels.com", "CFO", "Decision maker", "2025-10-30"),
    ("C-701", "CRM-1007", "Nina Patel", "n.patel@pellow-eng.com", "Finance Manager", "Decision maker", "2025-03-14"),
    ("C-801", "CRM-1008", "Chris Lowe", "chris@tamsinsoftware.io", "COO", "Decision maker", "2025-08-25"),
]

# ---------------------------------------------------------------- Product holdings
HOLDINGS = [
    # account_id, product_code, status, opened_on, utilization_pct
    ("CRM-1001", "CASH_MGMT", "active", "2020-03-02", 82),
    ("CRM-1001", "TRADE_FIN", "active", "2021-05-10", 64),
    ("CRM-1001", "CARD", "active", "2022-02-01", 55),
    ("CRM-1001", "TERM_LOAN", "active", "2023-09-15", 100),
    ("CRM-1002", "CASH_MGMT", "active", "2016-09-12", 91),
    ("CRM-1002", "PAYROLL", "active", "2017-01-09", 97),
    ("CRM-1002", "TERM_LOAN", "active", "2021-03-01", 100),
    ("CRM-1012", "CARD", "active", "2019-07-01", 61),   # held under the alias account
    ("CRM-1003", "CASH_MGMT", "active", "2022-01-17", 74),
    ("CRM-1003", "CARD", "active", "2024-04-02", 18),   # TRAP/material: utilization below 30%
    ("CRM-1003", "TRADE_FIN", "active", "2023-02-20", 58),
    ("CRM-1004", "CASH_MGMT", "active", "2018-05-21", 88),
    ("CRM-1004", "SUPPLY_FIN", "active", "2020-10-01", 70),
    ("CRM-1005", "TRADE_FIN", "active", "2021-11-03", 66),
    ("CRM-1006", "FX_HEDGE", "active", "2019-02-11", 77),
    ("CRM-1006", "TERM_LOAN", "active", "2020-06-01", 100),
    ("CRM-1007", "CASH_MGMT", "active", "2023-06-30", 49),
    ("CRM-1008", "CARD", "active", "2024-08-19", 35),
]

# ---------------------------------------------------------------- Revenue (billing system, keyed by billing_id)
# Monthly base revenue per product (GBP). Months run 2025-11 .. 2026-10.
# Hero trends are exact so the materiality rule fires predictably:
#   Kestrel Foods: Q3-2026 = 0.88 x Q2-2026  -> -12% QoQ (material, > 10%)
#   Corvan:        Q3-2026 = 1.15 x Q2-2026  -> +15% QoQ (material)
#   Halden:        flat                       -> not material
MONTHS = [
    "2025-11", "2025-12", "2026-01", "2026-02", "2026-03", "2026-04",
    "2026-05", "2026-06", "2026-07", "2026-08", "2026-09", "2026-10",
]
REVENUE_BASE = {
    "BIL-7001": {"CASH_MGMT": 52_000, "TRADE_FIN": 61_000, "CARD": 9_500, "TERM_LOAN": 28_000},
    "BIL-7002": {"CASH_MGMT": 140_000, "PAYROLL": 48_000, "TERM_LOAN": 66_000, "CARD": 12_000},
    "BIL-7003": {"CASH_MGMT": 34_000, "CARD": 4_000, "TRADE_FIN": 22_000},
    "BIL-7004": {"CASH_MGMT": 98_000, "SUPPLY_FIN": 57_000},
    "BIL-7005": {"TRADE_FIN": 31_000},
    "BIL-7006": {"FX_HEDGE": 120_000, "TERM_LOAN": 75_000},
    "BIL-7007": {"CASH_MGMT": 14_000},
    "BIL-7008": {"CARD": 3_000},
    "BIL-7014": {"SUPPLY_FIN": 6_000},
}
# Multiplier applied from 2026-07 onwards (Q3 + October).
REVENUE_SHIFT_FROM = "2026-07"
REVENUE_SHIFT = {"BIL-7001": 0.88, "BIL-7003": 1.15}

# ---------------------------------------------------------------- Service performance (operations system)
# How well our services perform for each client, monthly. Keyed by CRM account (alias rows included).
#   payments_processed: count of payments we processed
#   stp_rate_pct:       straight-through processing rate (% of payments needing no manual fix)
#   avg_balance_gbp:    average cash balance held with us
PERFORMANCE_MONTHS = ["2026-05", "2026-06", "2026-07", "2026-08", "2026-09", "2026-10"]
PERFORMANCE_BASE = {
    # account_id: (payments_processed, stp_rate_pct, avg_balance_gbp)
    "CRM-1001": (5_200, 98.4, 3_100_000),
    "CRM-1002": (41_000, 98.9, 18_500_000),
    "CRM-1003": (2_600, 97.1, 1_400_000),
    "CRM-1004": (23_000, 98.6, 9_800_000),
    "CRM-1005": (1_900, 96.8, 850_000),
    "CRM-1006": (8_400, 99.1, 22_000_000),
    "CRM-1007": (700, 97.5, 310_000),
    "CRM-1008": (450, 98.0, 120_000),
}
# Trend from 2026-07: Kestrel moves cash elsewhere (balance -10%); Corvan grows (payments +15%).
PERFORMANCE_SHIFT = {("CRM-1001", "avg_balance_gbp"): 0.90, ("CRM-1003", "payments_processed"): 1.15}
# Exact overrides: Halden payroll rejections drag STP down (ties to ISS-2001 / EM-2001).
PERFORMANCE_OVERRIDES = {
    ("CRM-1002", "2026-10", "stp_rate_pct"): 91.2,
}

# ---------------------------------------------------------------- Relationship metrics (relationship system)
# One row per client per survey date (quarterly client survey + market share-of-wallet estimate).
#   wallet_share_pct:   share of the client's banking spend that comes to us
#   satisfaction_score: client survey score out of 10
#   primary_bank:       1 if we are the client's main bank
RELATIONSHIP_DATES = ["2026-02-13", "2026-05-15", "2026-08-14", "2026-11-13"]
RELATIONSHIP_METRICS = {
    # account_id: ([wallet_share_pct per date], [satisfaction_score per date], primary_bank)
    "CRM-1001": ([45, 45, 44, 38], [8.1, 8.0, 8.2, 7.9], 1),   # wallet share down 6 points (cash moving away)
    "CRM-1002": ([35, 35, 36, 36], [8.4, 8.3, 8.5, 6.1], 1),   # satisfaction down 2.4 after payroll failures
    "CRM-1003": ([30, 32, 35, 41], [7.2, 7.4, 7.5, 7.6], 1),   # growing with us
    "CRM-1004": ([52, 52, 53, 52], [8.0, 8.1, 7.9, 8.0], 1),
    "CRM-1005": ([20, 21, 21, 22], [7.0, 7.1, 7.0, 7.2], 0),
    "CRM-1006": ([60, 61, 60, 60], [8.6, 8.5, 8.6, 8.4], 1),
    "CRM-1007": ([25, 25, 24, 25], [7.5, 7.6, 7.4, 7.5], 0),
    "CRM-1008": ([15, 16, 16, 17], [6.9, 7.0, 7.1, 7.0], 0),
}

# ---------------------------------------------------------------- Pipeline
PIPELINE = [
    # opp_id, account_id, product_code, stage, value, expected_close, updated_at, restricted
    ("OPP-1001", "CRM-1001", "TRADE_FIN", "Proposal", 180_000, "2027-02-28", "2026-11-06", 0),
    ("OPP-2001", "CRM-1002", "CASH_MGMT", "Negotiation", 420_000, "2026-12-15", "2026-11-02", 0),  # closes within 60 days
    ("OPP-2002", "CRM-1002", "ADVISORY", "Mandate", 2_500_000, "2027-03-31", "2026-10-25", 1),     # TRAP restricted (Project Atlas)
    ("OPP-3001", "CRM-1003", "SUPPLY_FIN", "Qualification", 150_000, "2027-04-30", "2026-09-18", 0),
    ("OPP-4001", "CRM-1004", "FX_HEDGE", "Proposal", 90_000, "2027-01-31", "2026-10-10", 0),
    ("OPP-6001", "CRM-1006", "TRADE_FIN", "Qualification", 300_000, "2027-05-30", "2026-10-01", 0),
]

# ---------------------------------------------------------------- Service issues
SERVICE_ISSUES = [
    # issue_id, account_id, opened_at, closed_at, severity, status, summary
    ("ISS-1001", "CRM-1001", "2026-10-21", "", 3, "open", "Card statement export missing cost-centre field"),
    ("ISS-1002", "CRM-1001", "2026-11-04", "", 3, "open", "Trade finance portal login delays for two users"),
    ("ISS-2001", "CRM-1012", "2026-10-09", "", 2, "open", "Payroll file rejected twice; staff payments delayed"),  # Sev-2 open > 14 days, under alias
    ("ISS-2002", "CRM-1002", "2026-08-03", "2026-08-05", 4, "closed", "Statement PDF formatting"),
    ("ISS-3001", "CRM-1003", "2026-07-14", "2026-07-20", 3, "closed", "Card limit change not applied"),
    ("ISS-4001", "CRM-1004", "2026-10-30", "", 3, "open", "Supply chain finance invoice upload error"),
]

# ---------------------------------------------------------------- Open actions
OPEN_ACTIONS = [
    # action_id, account_id, owner_user, description, due_date, status, source_ref
    ("ACT-1001", "CRM-1001", "U-SEN", "Send revised FX hedging pricing to Tom Reyes", "2026-11-01", "open", "EM-1001"),  # past due
    ("ACT-1002", "CRM-1001", "U-ANA", "Share trade finance limit options for Rotterdam", "2026-11-28", "open", "EM-1003"),
    ("ACT-2001", "CRM-1002", "U-SEN", "Provide root-cause report on payroll file rejections", "2026-11-20", "open", "EM-2001"),
    ("ACT-2002", "CRM-1002", "U-ANA", "Send updated cash management fee schedule", "2026-10-15", "done", "NT-2002"),
    ("ACT-3001", "CRM-1003", "U-ANA", "Run corporate card programme review with fleet team", "2026-10-31", "open", "NT-3001"),  # past due
]

# ---------------------------------------------------------------- Interactions (last contact log)
INTERACTIONS = [
    # interaction_id, account_id, date, type, summary_doc_id
    ("INT-1000", "CRM-1001", "2026-07-08", "meeting", "BR-1001"),
    ("INT-1001", "CRM-1001", "2026-10-14", "meeting", "NT-1001"),
    ("INT-2000", "CRM-1002", "2024-05-12", "meeting", "NT-2001"),
    ("INT-2001", "CRM-1002", "2026-09-30", "meeting", "NT-2002"),
    ("INT-3001", "CRM-1003", "2026-08-20", "call", "NT-3001"),
    ("INT-4001", "CRM-1004", "2026-09-05", "meeting", ""),
    ("INT-6001", "CRM-1006", "2026-10-01", "call", ""),
]

# ---------------------------------------------------------------- Calendar (upcoming meetings)
MEETINGS = [
    # meeting_id, account_id, start_time, title, attendees (user ids ; contact ids)
    ("MTG-1", "CRM-1001", "2026-11-19T10:00", "Kestrel Foods quarterly review", "U-SEN;U-ANA;C-101;C-102"),
    ("MTG-2", "CRM-1002", "2026-11-18T14:00", "Halden Medical payroll and treasury check-in", "U-SEN;U-ANA;C-201;C-202"),
    ("MTG-3", "CRM-1003", "2026-11-20T09:30", "Corvan Logistics card programme review", "U-ANA;C-301;C-302"),
    ("MTG-4", "CRM-1006", "2026-11-24T11:00", "Kestrel Fuels annual review", "U-ANA2;C-601"),
]
