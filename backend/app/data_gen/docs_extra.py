"""Extra documents: realistic volume and distractors so retrieval is actually tested.

Rules for these docs (so docs/DATA.md's facts and traps stay true):
  - consistent with the tables (contacts, products, issues, deals, interactions)
  - no new open actions, conflicts, restricted records or injection text
  - hero distractors are on-topic but routine, or older statements that newer ones supersede
"""

EXTRA_DOCS = [
    # ======================================================== HERO DISTRACTORS
    {
        "id": "EM-1000", "type": "email", "date": "2025-06-10", "account_id": "CRM-1001",
        "from": "Tom Reyes <t.reyes@kestrelfoods.com>", "to": "Daniel Okafor",
        "subject": "Re: FX risk discussion", "sensitivity": "normal",
        # TRAP stale (2): superseded by the October 2026 meeting note, where Tom asks for hedging pricing.
        "body": """Hi Daniel,

Thanks for the FX overview. Exports are still under 15% of sales, so we are not looking at hedging this year.
Happy to revisit if our European business grows.

Best,
Tom
""",
    },
    {
        "id": "EM-1004", "type": "email", "date": "2026-09-03", "account_id": "CRM-1001",
        "from": "Ana Duarte <a.duarte@kestrelfoods.com>", "to": "Priya Shah",
        "subject": "Authorised signatories update", "sensitivity": "normal",
        "body": """Hi Priya,

Please update our authorised signatory list: add our new financial controller, Lena Hoff, and remove our former
treasury manager.
The signed board resolution is attached.

Thanks,
Ana
""",
    },
    {
        "id": "NT-1000", "type": "note", "date": "2026-04-14", "account_id": "CRM-1001",
        "title": "Call notes: Kestrel Foods Q1 check-in", "sensitivity": "normal",
        "body": """## Page 1
Routine quarterly call with Ana Duarte. Cash management and card programme running smoothly.
Ana mentioned the European customer base is growing faster than planned. No requests raised.
""",
    },
    {
        "id": "NT-2000", "type": "note", "date": "2025-11-20", "account_id": "CRM-1002",
        "title": "Meeting notes: Halden Medical annual review 2025", "sensitivity": "normal",
        "body": """## Page 1
Jin Park confirmed he will step down as CFO at the end of 2025. Maria Lopes joins as CFO in March 2026.
Owen Pratt remains Group Treasurer and day-to-day contact.

## Page 2
Payroll and cash management performance were good this year. Halden plans to review its banking panel in 2026.
""",
    },
    {
        "id": "EM-2002", "type": "email", "date": "2026-09-12", "account_id": "CRM-1002",
        "from": "Owen Pratt <o.pratt@haldenmedical.com>", "to": "Priya Shah",
        "subject": "Statement format", "sensitivity": "normal",
        "body": """Hello Priya,

Could you send the September account statements in CSV as well as PDF? Our finance team imports them into the ledger.

Kind regards,
Owen
""",
    },
    {
        "id": "EM-2003", "type": "email", "date": "2026-11-02", "account_id": "CRM-1002",
        "from": "Owen Pratt <o.pratt@haldenmedical.com>", "to": "Daniel Okafor",
        "subject": "Agenda for our next meeting", "sensitivity": "normal",
        "body": """Hi Daniel,

For our next meeting Maria would like to cover two things: the payroll root cause, and the timeline for moving
cash management onto one bank. Please come with a proposed plan for the second item.

Regards,
Owen
""",
    },
    {
        "id": "EM-3000", "type": "email", "date": "2026-06-05", "account_id": "CRM-1003",
        "from": "Ruth Adeyemi <r.adeyemi@corvanlogistics.com>", "to": "Priya Shah",
        "subject": "Quarterly cash forecast", "sensitivity": "normal",
        "body": """Hi Priya,

Sharing our cash forecast for the next quarter. Volumes are rising and we expect higher balances from August.

Best regards,
Ruth
""",
    },

    # ======================================================== LARKSPUR RETAIL (CRM-1004)
    {
        "id": "NT-4001", "type": "note", "date": "2026-09-05", "account_id": "CRM-1004",
        "title": "Meeting notes: Larkspur Retail treasury review", "sensitivity": "normal",
        "body": """## Page 1
Attendees: Helen Ford (Treasurer), Daniel Okafor.
About a third of Larkspur's stock is bought in US dollars. Helen wants to hedge part of next year's purchases.

## Page 2
Supply chain finance is working well; around 120 suppliers are on the programme.
""",
    },
    {
        "id": "EM-4001", "type": "email", "date": "2026-10-31", "account_id": "CRM-1004",
        "from": "Helen Ford <h.ford@larkspurretail.co.uk>", "to": "Daniel Okafor",
        "subject": "Invoice upload error", "sensitivity": "normal",
        "body": """Hi Daniel,

Since yesterday our supply chain finance invoice uploads are failing with a format error. Suppliers are asking
when they will be paid. Can someone look at this urgently?

Thanks,
Helen
""",
    },
    {
        "id": "EM-4002", "type": "email", "date": "2026-10-12", "account_id": "CRM-1004",
        "from": "Helen Ford <h.ford@larkspurretail.co.uk>", "to": "Daniel Okafor",
        "subject": "USD hedging proposal", "sensitivity": "normal",
        "body": """Daniel,

Thanks for the hedging proposal. The board will review it in January. We would like to compare a 6-month and a
12-month programme.

Regards,
Helen
""",
    },
    {
        "id": "NW-4001", "type": "news", "date": "2026-11-06", "account_id": "CRM-1004",
        "title": "Larkspur Retail reports 3% like-for-like sales growth", "source": "Approved feed: Retail Week Digest",
        "sensitivity": "normal",
        "body": "Larkspur Retail plc reported like-for-like sales up 3% in the third quarter, led by online grocery.",
    },

    # ======================================================== MERIDIAN TEXTILES (CRM-1005)
    {
        "id": "NT-5001", "type": "note", "date": "2026-07-15", "account_id": "CRM-1005",
        "title": "Call notes: Meridian Textiles", "sensitivity": "normal",
        "body": """## Page 1
Arjun Mehta said export orders to Europe are steady. Letters of credit are taking too long to issue in peak season.
""",
    },
    {
        "id": "EM-5001", "type": "email", "date": "2026-09-22", "account_id": "CRM-1005",
        "from": "Arjun Mehta <arjun@meridiantextiles.com>", "to": "Leo Brandt",
        "subject": "Letter of credit timing", "sensitivity": "normal",
        "body": """Hello Leo,

Our last two letters of credit took six working days to issue. Can we agree a faster turnaround before the
winter shipping season?

Regards,
Arjun
""",
    },
    {
        "id": "NW-5001", "type": "news", "date": "2026-10-19", "account_id": "CRM-1005",
        "title": "Meridian Textiles to open new weaving plant", "source": "Approved feed: Textile Times",
        "sensitivity": "normal",
        "body": "Meridian Textiles announced a new weaving plant in Tamil Nadu, expected to raise capacity by 25% in 2027.",
    },

    # ======================================================== KESTREL FUELS (CRM-1006), look-alike distractors
    {
        "id": "NT-6001", "type": "note", "date": "2026-10-01", "account_id": "CRM-1006",
        "title": "Call notes: Kestrel Fuels", "sensitivity": "normal",
        "body": """## Page 1
Gareth Lloyd (CFO) wants trade finance for crude imports next year. FX hedging programme is fully used.
""",
    },
    {
        "id": "EM-6001", "type": "email", "date": "2026-10-03", "account_id": "CRM-1006",
        "from": "Gareth Lloyd <g.lloyd@kestrelfuels.com>", "to": "Leo Brandt",
        "subject": "Trade finance for crude imports", "sensitivity": "normal",
        "body": """Leo,

Following our call, please send indicative trade finance terms for about GBP 300k of crude imports a quarter.
Our renewal with the current provider is in March.

Gareth
""",
    },
    {
        "id": "NW-6002", "type": "news", "date": "2026-11-02", "account_id": "CRM-1006",
        "title": "Kestrel Fuels appoints new chief executive", "source": "Approved feed: Energy Wire",
        "sensitivity": "normal",
        "body": "Kestrel Fuels plc named a new chief executive, effective January 2027, after a strategy review.",
    },

    # ======================================================== PELLOW ENGINEERING (CRM-1007)
    {
        "id": "EM-7001", "type": "email", "date": "2026-08-28", "account_id": "CRM-1007",
        "from": "Nina Patel <n.patel@pellow-eng.com>", "to": "Leo Brandt",
        "subject": "Cash sweep question", "sensitivity": "normal",
        "body": """Hi Leo,

Can we set up an automatic sweep from our three operating accounts into the main account each evening?

Thanks,
Nina
""",
    },
    {
        "id": "NW-7001", "type": "news", "date": "2026-09-30", "account_id": "CRM-1007",
        "title": "Pellow Engineering wins rail maintenance contract", "source": "Approved feed: Construction News",
        "sensitivity": "normal",
        "body": "Pellow Engineering won a three-year rail signalling maintenance contract in the Midlands.",
    },

    # ======================================================== TAMSIN SOFTWARE (CRM-1008)
    {
        "id": "EM-8001", "type": "email", "date": "2026-10-21", "account_id": "CRM-1008",
        "from": "Chris Lowe <chris@tamsinsoftware.io>", "to": "Leo Brandt",
        "subject": "Card limits for conference travel", "sensitivity": "normal",
        "body": """Hi Leo,

Our sales team travels to three conferences next month. Can we raise card limits temporarily for six people?

Cheers,
Chris
""",
    },
    {
        "id": "NW-8001", "type": "news", "date": "2026-10-08", "account_id": "CRM-1008",
        "title": "Tamsin Software raises Series B funding", "source": "Approved feed: Tech Funding Daily",
        "sensitivity": "normal",
        "body": "Tamsin Software raised GBP 18m in Series B funding to expand in Germany and the Netherlands.",
    },

    # ======================================================== GENERAL (no client)
    {
        "id": "NW-9001", "type": "news", "date": "2026-10-15", "account_id": "",
        "title": "UK haulage costs rise 6% in 2026", "source": "Approved feed: Logistics Today",
        "sensitivity": "normal",
        "body": "Road haulage operating costs in the UK rose 6% this year, driven by driver wages and fuel.",
    },
    {
        "id": "NW-9002", "type": "news", "date": "2026-11-06", "account_id": "",
        "title": "Bank of England holds interest rates", "source": "Approved feed: Markets Brief",
        "sensitivity": "normal",
        "body": "The Bank of England held its base rate at 3.75% and signalled one cut is possible in early 2027.",
    },
    {
        "id": "NW-9003", "type": "news", "date": "2026-10-22", "account_id": "",
        "title": "Kestrel Logistics fined over late deliveries", "source": "Approved feed: Logistics Today",
        "sensitivity": "normal",
        # Distractor: a third 'Kestrel' company that is not a client at all.
        "body": "Kestrel Logistics, a Scottish courier firm, was fined by the regulator over repeated late deliveries.",
    },
    {
        "id": "RS-9002", "type": "research", "date": "2026-08-20", "account_id": "",
        "title": "Product update: corporate card controls for fleets", "sensitivity": "normal",
        "body": """## Page 1
Corporate Cards now support fuel-only merchant controls and per-vehicle limits.
Fleet operators using these controls report cutting expense claims processing time by about 70%.
""",
    },
    {
        "id": "RS-9001", "type": "research", "date": "2026-10-28", "account_id": "",
        "title": "Research: UK mid-market corporate banking outlook, Q4 2026", "sensitivity": "normal",
        "body": """## Page 1
### Summary
Mid-market companies enter 2027 with stronger order books but tighter margins. Three themes stand out for
relationship teams: currency risk from growing export sales, pressure to consolidate banking relationships,
and demand for faster supplier payments.

### Interest rates
With the base rate held at 3.75%, borrowing costs remain above their ten-year average. Treasurers are keeping
more cash in operating accounts and asking for better returns on balances.

## Page 2
### Currency risk
Export growth has been strongest among food, textile and engineering firms selling into the eurozone. Many of
these firms grew exports quickly and never set up a hedging programme, because exports used to be a small part
of sales. When sterling moved sharply in the summer of 2026, firms without hedges saw gross margins fall by two
to four points within a quarter. Firms that hedged half or more of their forecast receivables kept margins
within one point of plan. Relationship teams should look for clients whose export share has risen above a fifth
of sales in the last two years, check whether they hedge, and ask how a currency move would affect their
margins. A rolling twelve-month forward programme is usually the simplest starting point: it smooths the rate
the client receives without locking in a single price for the whole year. Clients often prefer to begin by
covering about half of forecast receivables and increase cover once they are comfortable with the process.
Treasury teams at smaller firms may need help building the receivables forecast itself, which is a good reason
to involve the product specialist early. Firms that sell in several currencies may want separate programmes per
currency, reviewed every quarter alongside the sales forecast. Pricing should be shown both as a forward rate
and as the margin impact it protects, because finance directors relate more easily to the second figure. A
short worked example using the client's own last quarter usually lands better than a general presentation.

## Page 3
### Banking consolidation
Large corporates and healthcare groups are cutting the number of banks they use, often from three or four to
one or two. The bank that keeps the business is usually the one with the best service record in the year
before the review. Service failures in payroll and payments are the most damaging, because they affect staff
directly.

### Supplier payments
Logistics and retail firms are under pressure to pay small suppliers faster. Supply chain finance lets them do
this without shortening their own payment terms, and adoption grew by about a fifth in 2026.

## Page 4
### What to watch in 2027
Expect more requests for trade finance as firms open new sites in Europe, more scrutiny of banking fees during
consolidation reviews, and continued interest in card controls that cut expense processing.
""",
    },
]
