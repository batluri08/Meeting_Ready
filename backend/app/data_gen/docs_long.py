"""Long, realistic documents: email threads, meeting transcripts, and the same news from several outlets.

Every fact here matches the core documents and tables (docs/DATA.md stays true). What they add is the mess
real data has: quoted replies, signatures and disclaimers, long speaker-by-speaker transcripts, and
syndicated news that is worded differently and sometimes disagrees on figures.
"""

BANK_DISCLAIMER = (
    "This email and any attachments are confidential and intended solely for the addressee. If you have "
    "received it in error, please notify the sender and delete it. Northgate Bank plc is authorised and "
    "regulated in the United Kingdom."
)


def _bank_sig(name: str, title: str) -> str:
    return f"{name}\n{title}\nNorthgate Bank plc | Coverage East\n\n{BANK_DISCLAIMER}"


LONG_DOCS = [
    # ======================================================== EMAIL THREADS
    {
        "id": "TH-2001", "type": "email", "date": "2026-11-12", "account_id": "CRM-1002",
        "subject": "Payroll rejections (thread)", "sensitivity": "normal",
        "from": "Maria Lopes <maria.lopes@haldenmedical.com>", "to": "Daniel Okafor",
        # TRAP thread duplicate: message 1 is EM-2001 again; quoted text repeats earlier messages.
        "body": f"""=== Message 1 ===
From: Maria Lopes <maria.lopes@haldenmedical.com>
To: Daniel Okafor
Date: 2026-10-28
Subject: Payroll rejections

Daniel,

Our payroll file was rejected twice this month and some staff were paid late. This is not acceptable.
Please send a root-cause report by 20 November. I will want to discuss this at our next meeting.

Maria

=== Message 2 ===
From: Daniel Okafor <daniel.okafor@northgatebank.example>
To: Maria Lopes; Owen Pratt
Date: 2026-10-29
Subject: RE: Payroll rejections

Dear Maria,

I am sorry for the disruption to your staff. Our payments operations team is investigating both rejections as
a priority. Until we have the root cause, we will release Halden payroll files manually on the day they arrive so
no further payments are delayed. You will have the written root-cause report by 20 November as you asked.

Kind regards,
{_bank_sig("Daniel Okafor", "Relationship Director")}

On 2026-10-28, Maria Lopes wrote:
> Our payroll file was rejected twice this month and some staff were paid late. This is not acceptable.
> Please send a root-cause report by 20 November.

=== Message 3 ===
From: Owen Pratt <o.pratt@haldenmedical.com>
To: Daniel Okafor
Cc: Maria Lopes
Date: 2026-11-04
Subject: RE: Payroll rejections

Hi Daniel,

The November file went through with the manual release, thank you. Our payroll provider tells us the rejection
message mentioned an unexpected field in the file header. They did not change their format, so we assume
something changed on your side in early October.

Regards,
Owen

On 2026-10-29, Daniel Okafor wrote:
> Until we have the root cause, we will release Halden payroll files manually on the day they arrive so
> no further payments are delayed.

=== Message 4 ===
From: Daniel Okafor <daniel.okafor@northgatebank.example>
To: Maria Lopes; Owen Pratt
Date: 2026-11-11
Subject: RE: Payroll rejections

Dear Maria, dear Owen,

We have found the cause. A file validation change in our 7 October release rejected an optional header field
that your payroll provider has always sent. The fix was deployed on 10 November and tested with your last two
files. The full written report remains on track for 20 November.

Kind regards,
{_bank_sig("Daniel Okafor", "Relationship Director")}

=== Message 5 ===
From: Maria Lopes <maria.lopes@haldenmedical.com>
To: Daniel Okafor
Date: 2026-11-12
Subject: RE: Payroll rejections

Daniel,

Thank you for the update. I still want the written report by 20 November. I also want to discuss compensation
for the staff who were paid late, as some of them were charged overdraft fees by their own banks.

Maria

On 2026-11-11, Daniel Okafor wrote:
> We have found the cause. A file validation change in our 7 October release rejected an optional header field.
""",
    },
    {
        "id": "TH-1001", "type": "email", "date": "2026-11-03", "account_id": "CRM-1001",
        "subject": "FX pricing follow-up (thread)", "sensitivity": "normal",
        "from": "Tom Reyes <t.reyes@kestrelfoods.com>", "to": "Daniel Okafor",
        "body": """=== Message 1 ===
From: Tom Reyes <t.reyes@kestrelfoods.com>
To: Daniel Okafor
Date: 2026-10-16
Subject: FX pricing follow-up

Hi Daniel,

Thanks for Wednesday. As discussed, please send the revised FX hedging pricing by 1 November so we can take
it to our board on 12 November. A 12-month rolling programme on EUR receivables is what we have in mind.

Best,
Tom

=== Message 2 ===
From: Ana Duarte <a.duarte@kestrelfoods.com>
To: Priya Shah
Date: 2026-10-28
Subject: RE: FX pricing follow-up

Hi Priya,

Just checking the FX pricing is still on track for 1 November. Our board pack closes on 5 November.

Thanks,
Ana

=== Message 3 ===
From: Tom Reyes <t.reyes@kestrelfoods.com>
To: Daniel Okafor
Cc: Ana Duarte
Date: 2026-11-03
Subject: RE: FX pricing follow-up

Daniel,

We have not received the pricing, and our board meets on 12 November. If we cannot include it, we will either
postpone the decision or go with the other bank that has already sent us terms.

Tom

On 2026-10-16, Tom Reyes wrote:
> please send the revised FX hedging pricing by 1 November so we can take it to our board on 12 November.
""",
    },
    {
        "id": "TH-3001", "type": "email", "date": "2026-11-09", "account_id": "CRM-1003",
        "subject": "Corporate card review (thread)", "sensitivity": "normal",
        "from": "Marek Nowak <m.nowak@corvanlogistics.com>", "to": "Priya Shah",
        "body": f"""=== Message 1 ===
From: Priya Shah <priya.shah@northgatebank.example>
To: Ruth Adeyemi; Marek Nowak
Date: 2026-08-21
Subject: Corporate card review

Dear Ruth, dear Marek,

Following our call, we will run a review of the corporate card programme with your fleet team by the end of
October, covering card controls, limits and how drivers claim fuel today.

Kind regards,
{_bank_sig("Priya Shah", "Analyst")}

=== Message 2 ===
From: Marek Nowak <m.nowak@corvanlogistics.com>
To: Priya Shah
Date: 2026-10-02
Subject: RE: Corporate card review

Hi Priya,

Do you have a date for the card review? Drivers keep asking whether they can stop paying for fuel themselves.

Marek

=== Message 3 ===
From: Marek Nowak <m.nowak@corvanlogistics.com>
To: Priya Shah
Date: 2026-11-09
Subject: Fuel cards for new depots

Hi Priya,

We are opening two new depots in January and will add about 60 drivers. Can we talk about getting cards
to all drivers? We still have not had the card review you mentioned.

Marek

On 2026-10-02, Marek Nowak wrote:
> Do you have a date for the card review?
""",
    },

    # ======================================================== MEETING TRANSCRIPTS
    {
        "id": "TR-1001", "type": "transcript", "date": "2026-10-14", "account_id": "CRM-1001",
        "title": "Transcript: Kestrel Foods treasury review", "sensitivity": "normal",
        "body": """[00:00] Daniel Okafor: Thanks for making the time, everyone. Priya is joining from our side as well. I thought we could start with how the year has gone, then look at currency, and finish with anything coming up next year.
[00:21] Tom Reyes: Sounds good. Overall it has been a strong year for volume. We added two supermarket groups in Germany and our Dutch business is up again. The problem is margin, not sales.
[00:38] Daniel Okafor: Tell me more about the margin side.
[00:42] Tom Reyes: About 40 percent of our sales are now export, and most of that is invoiced in euros. Eighteen months ago it was under 15 percent, so we never set anything up for currency. When the pound moved in the summer, our gross margin dropped by two to three points in a single quarter. The board noticed.
[01:10] Ana Duarte: And we had no protection at all. Everything was converted at whatever the spot rate was on the day the money arrived.
[01:19] Daniel Okafor: So none of the euro receivables are hedged today?
[01:23] Ana Duarte: None. We looked at it once in 2025 but exports were still small then, so we parked it.
[01:31] Priya Shah: Do you have a forecast for the euro receivables over the next twelve months?
[01:36] Ana Duarte: Roughly. We can share a monthly forecast by customer. It is not perfect, but it is good enough to plan around.
[01:45] Tom Reyes: I will be honest with you. Another bank has already offered us FX terms, and we moved some of our euro collections to them over the summer because their rate was better. I would rather keep it simple and have it all with you, but I need a proposal.
[02:08] Daniel Okafor: Understood, and thank you for saying it directly. What would a good proposal look like for you?
[02:14] Tom Reyes: A 12-month rolling programme on the euro receivables. Something that smooths the rate we get, without locking us into one price for the whole year. And I need it in time for the board.
[02:27] Daniel Okafor: When does the board meet?
[02:30] Tom Reyes: Twelfth of November. The pack closes about a week before.
[02:35] Daniel Okafor: Then we will send you revised pricing by the first of November. Priya and I will work with our FX desk on it, and we can start by covering around half of the forecast receivables, which is what most clients your size begin with.
[02:52] Tom Reyes: First of November works. Please do not let that slip.
[02:56] Daniel Okafor: It will not. Ana, anything on the operational side?
[03:01] Ana Duarte: Two things. First, we are opening a new warehouse in Rotterdam next year to serve the Benelux and German customers. That means more imports of stock and more letters of credit, so we may need larger trade finance limits from around March.
[03:20] Priya Shah: Do you have a sense of the size?
[03:23] Ana Duarte: Not yet. I will come back to you once the building contract is signed. It could be a couple of million euros extra.
[03:31] Daniel Okafor: That is helpful to know early. We have a trade finance proposal in progress already, so we can extend it once you have the numbers.
[03:40] Ana Duarte: Second, card fees. Before the banking agreement renews, we would like to review what we pay on the corporate card programme. Usage has gone up, so we think the fee structure should reflect that.
[03:55] Daniel Okafor: Fair point. We can bring a fee comparison to the next meeting.
[04:01] Tom Reyes: One more thing from me. Service has been fine this year, no complaints there. The reason we are talking to other banks is purely pricing on FX.
[04:12] Daniel Okafor: That is good to hear. So to recap: FX hedging pricing for a 12-month rolling programme by 1 November, trade finance limits once the Rotterdam numbers are clear, and a card fee comparison for the next meeting.
[04:28] Ana Duarte: And I will send the euro receivables forecast this week.
[04:32] Tom Reyes: Good. Thanks, both.
[04:35] Daniel Okafor: Thank you. Speak soon.
""",
    },
    {
        "id": "TR-2001", "type": "transcript", "date": "2026-09-30", "account_id": "CRM-1002",
        "title": "Transcript: Halden Medical treasury check-in", "sensitivity": "normal",
        "body": """[00:00] Daniel Okafor: Good afternoon, Maria, Owen. Thank you for having us. We sent the updated cash management fee schedule last week; I hope it arrived.
[00:09] Maria Lopes: It did, thank you. I want to use today to talk about the bigger picture.
[00:15] Maria Lopes: Halden currently banks with three providers. That made sense when the group was smaller, but it now costs us time and money. My plan is to consolidate our cash management onto one bank by the middle of 2027.
[00:33] Daniel Okafor: That is a significant decision. How will you choose?
[00:37] Maria Lopes: We will run a review in the first quarter of next year. Pricing matters, but honestly, service matters more. When payments go wrong in a hospital group, it is nurses and doctors who feel it.
[00:52] Owen Pratt: On that point, I should mention payroll. At month end the payroll files have occasionally been slow to process. Nothing has failed outright yet, but staff notice when pay lands late in the day.
[01:06] Daniel Okafor: Thank you for raising it. Is it every month, or occasionally?
[01:10] Owen Pratt: Two or three times this year, always at month end when volumes peak.
[01:15] Priya Shah: I will ask our payments operations team to look at month-end processing for your files specifically.
[01:21] Maria Lopes: Please do. I will be blunt: if payroll goes wrong during the review period, it will weigh heavily in the decision.
[01:29] Daniel Okafor: Understood. What would help you most in the review?
[01:33] Maria Lopes: A clear proposal for running all of our cash management with one bank: account structure, cash pooling across the hospitals, and a realistic migration plan. And evidence of service quality.
[01:48] Owen Pratt: Cash pooling would be valuable. Today we move money between hospital accounts by hand at the end of each week.
[01:55] Daniel Okafor: We can put together a cash pooling design for the review. Owen, could you share the current account list across all three banks?
[02:02] Owen Pratt: Yes, I will send it next week.
[02:05] Maria Lopes: Anything else from your side?
[02:08] Daniel Okafor: Only that we value the relationship and want to earn the consolidation. We will come back with the proposal well before the review starts.
[02:16] Maria Lopes: Good. Thank you both.
""",
    },

    # ======================================================== SYNDICATED NEWS (same story, several outlets)
    {
        "id": "NW-1003", "type": "news", "date": "2026-11-03", "account_id": "CRM-1001",
        "title": "Kestrel Foods to open Rotterdam hub", "source": "Approved feed: Food Logistics Weekly",
        "sensitivity": "normal",
        # TRAP news cluster: same story as NW-1001, different wording.
        "body": "Food distributor Kestrel Foods will open a 40,000 square metre distribution hub in Rotterdam in the second "
                "quarter of 2027, creating around 120 jobs and serving supermarket customers in the Benelux and Germany.",
    },
    {
        "id": "NW-1004", "type": "news", "date": "2026-11-04", "account_id": "CRM-1001",
        "title": "UK distributor Kestrel Foods picks Rotterdam for new centre", "source": "Approved feed: Benelux Business Wire",
        "sensitivity": "normal",
        # TRAP news conflict: says 45,000 square metres where the other outlets say 40,000.
        "body": "Kestrel Foods has chosen Rotterdam for a new 45,000 square metre distribution centre due to open in "
                "spring 2027, its first site outside the UK, to supply supermarkets in the Netherlands, Belgium and Germany.",
    },
    {
        "id": "NW-2002", "type": "news", "date": "2026-11-11", "account_id": "CRM-1002",
        "title": "New diagnostic imaging centre opens in Leeds", "source": "Approved feed: Regional Health News",
        "sensitivity": "normal",
        # Same story as NW-2001; figures agree (no conflict).
        "body": "Halden Medical Group has opened a diagnostic imaging centre in Leeds, its 31st clinic, with about 60 staff "
                "offering MRI and CT scans to NHS and private patients.",
    },
]
