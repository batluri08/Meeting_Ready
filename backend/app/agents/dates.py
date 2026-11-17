"""Date questions in chat ("what happened on the 13th of November?").

Search cannot answer these: "13th of November" never matches "2026-11-13" in a record, and a query written
by the model may miss a table. So dates are handled by code:
  1. parse_dates() reads the dates or period in the question (no model involved);
  2. on_record() lists everything dated in that period for this client, from every dated table, with one
     fixed query that respects the user's access (restricted deals and documents only for senior users).
The answer is then told to stick to that period and to say plainly when nothing is on record.
"""
import calendar
import re
from datetime import date, timedelta

from app.metrics.evidence import SqlEvidence, run

MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}
MONTHS.update({m.lower(): i for i, m in enumerate(calendar.month_abbr) if m})
MONTHS["sept"] = 9
_MON = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
_DAY = r"(\d{1,2})(?:st|nd|rd|th)?"
_YEAR = r"(?:,?\s+(\d{4}))?"
DAY_MONTH = re.compile(rf"\b{_DAY}\s+(?:of\s+)?{_MON}\b{_YEAR}", re.I)          # 13th of November (2026)
MONTH_DAY = re.compile(rf"\b{_MON}\s+{_DAY}\b{_YEAR}", re.I)                      # November 13th, 2026
ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
MONTH_ONLY = re.compile(rf"\b(?:in|during|for|of|over)\s+{_MON}\b{_YEAR}", re.I)  # in October


def _year_for(month: int, day: int, year: str | None, today: date) -> int:
    """No year given: the most recent such date (a question about 'December' asked in November means last year)."""
    if year:
        return int(year)
    return today.year if (month, day) <= (today.month, today.day) else today.year - 1


def parse_dates(question: str, today: date) -> list[tuple[date, date]]:
    """Date ranges (start, end inclusive) named in the question, in order. Empty if it names none."""
    q = question.lower()
    out: list[tuple[date, date]] = []

    def add(d1: date, d2: date | None = None):
        if (d1, d2 or d1) not in out:
            out.append((d1, d2 or d1))

    for m in ISO.finditer(q):
        try:
            add(date(int(m[1]), int(m[2]), int(m[3])))
        except ValueError:
            pass
    for rx, day_i, mon_i in ((DAY_MONTH, 1, 2), (MONTH_DAY, 2, 1)):
        for m in rx.finditer(q):
            month, day = MONTHS[m[mon_i].lower()[:4] if m[mon_i].lower()[:4] == "sept" else m[mon_i].lower()[:3]], int(m[day_i])
            try:
                add(date(_year_for(month, day, m[3], today), month, day))
            except ValueError:
                pass
    if "yesterday" in q:
        add(today - timedelta(days=1))
    if re.search(r"\btoday\b", q):
        add(today)
    if re.search(r"\blast week\b", q):
        add(today - timedelta(days=7), today - timedelta(days=1))
    if not out:                                             # whole month only if no specific day was named
        for m in MONTH_ONLY.finditer(q):
            month = MONTHS[m[1].lower()[:3]]
            year = int(m[2]) if m[2] else (today.year if month <= today.month else today.year - 1)
            add(date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1]))
    return out


def describe(start: date, end: date) -> str:
    """'13 November 2026', or '1 October 2026 to 31 October 2026'."""
    f = lambda d: f"{d.day} {calendar.month_name[d.month]} {d.year}"   # noqa: E731
    return f(start) if start == end else f"{f(start)} to {f(end)}"


# Every dated record for one client in a period, in one fixed, read-only query (no model involved).
# Restricted deals and documents only when the user may see them (the last parameter, 0 or 1).
_PARTS = [
    ("relationship_metrics", "as_of", "'client survey'",
     "'satisfaction ' || satisfaction_score || '/10, share of wallet ' || wallet_share_pct || '%'", ""),
    ("interactions", "date", "type", "'interaction ' || interaction_id || COALESCE(' (notes ' || summary_doc_id || ')', '')", ""),
    ("meetings", "substr(start_time, 1, 10)", "'meeting scheduled'", "title || ' at ' || substr(start_time, 12, 5)", ""),
    ("service_issues", "opened_at", "'service issue opened'", "'Sev-' || severity || ' ' || issue_id || ': ' || summary", ""),
    ("service_issues", "closed_at", "'service issue closed'", "'Sev-' || severity || ' ' || issue_id || ': ' || summary", ""),
    ("open_actions", "due_date", "'action due'", "action_id || ' (' || status || '): ' || description", ""),
    ("pipeline", "updated_at", "'deal updated'", "opp_id || ' ' || product_code || ', ' || stage || ', GBP ' || value",
     " AND (restricted = 0 OR ?)"),
    ("pipeline", "expected_close", "'deal expected to close'", "opp_id || ' ' || product_code || ', ' || stage || ', GBP ' || value",
     " AND (restricted = 0 OR ?)"),
    ("documents", "date", "type", "doc_id || ': ' || title", " AND duplicate_of IS NULL AND (restricted = 0 OR ?)"),
    ("contacts", "updated_at", "'contact record updated'", "name || ', ' || title", " AND duplicate_of IS NULL"),
]


def on_record(conn, client_id: str, start: date, end: date, allow_restricted: bool) -> SqlEvidence:
    parts, params = [], []
    for table, col, kind, detail, extra in _PARTS:
        parts.append(f"SELECT {col} AS date, {kind} AS kind, {detail} AS detail, source_ref FROM {table} "
                     f"WHERE client_id = ? AND {col} BETWEEN ? AND ?{extra}")
        params += [client_id, start.isoformat(), end.isoformat()] + ([int(allow_restricted)] if "?" in extra else [])
    return run(conn, " UNION ALL ".join(parts) + " ORDER BY date, kind", tuple(params))


def evidence_text(ev: SqlEvidence, start: date, end: date) -> str:
    period = describe(start, end)
    if not ev.rows:
        return f"No records dated {period} ({start.isoformat()}" + ("" if start == end else f" to {end.isoformat()}") + \
               ") for this client in any system: no surveys, calls, meetings, issues, actions, deals, emails, notes or news."
    return f"Records dated {period}: " + "; ".join(f"{r['date']}: {r['kind']}: {r['detail']}" for r in ev.rows)
